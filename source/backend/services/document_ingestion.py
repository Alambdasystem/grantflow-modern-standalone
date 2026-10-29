"""Private document storage, versioned indexing and the existing worker's ingestion lane."""
import asyncio
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
import uuid
import time
import os
from sqlalchemy import select, delete, update
from fastapi import HTTPException
from config import settings
from db import database
from models.models import (Document, IngestionDocument as Item, IngestionSource as Source,
    DocumentChunk as Chunk, DocumentUse, AutomationJob as Job, AutomationJobStatus as Status,
    User, AuditLog, OrganizationRecord, AIConversation, GrantApplication)
from services.document_extract import EXTENSIONS, MAX_BYTES, CATEGORIES

lock = asyncio.Lock()


def now(): return datetime.utcnow()


def extraction_env():
    """Bound native threading and keep unrelated service credentials out of parsers."""
    names=('PATH','PYTHONPATH','HOME','USERPROFILE','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL','TZ')
    env={key:os.environ[key]for key in names if key in os.environ}
    env.update({key:'1'for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
    limit=512 if settings.ENVIRONMENT=='render-standalone' else 0
    try:
        raw=Path('/sys/fs/cgroup/memory.max').read_text().strip()
        if raw.isdigit():limit=int(raw)//(1024*1024)
    except OSError:pass
    env['GFM_EXTRACTION_MEMORY_LIMIT_MB']=str(limit)
    return env


def event(row, action, **details):
    row.history = (row.history or [])[-199:] + [{'at':now().isoformat(), 'action':action, **details}]


def storage():
    root = Path(settings.INGESTION_STORAGE_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def stored_path(doc):
    path = Path(doc.file_path).resolve()
    if not path.is_relative_to(storage()):
        raise ValueError('Invalid document storage location.')
    return path


def manifest():
    if not settings.INGESTION_SOURCE_MANIFEST:
        return []
    data = json.loads(Path(settings.INGESTION_SOURCE_MANIFEST).read_text(encoding='utf-8-sig'))
    if not isinstance(data, list) or len(data)>100:
        raise ValueError('Source manifest must be a list with at most 100 sources.')
    return data


async def queue(db, item, actor):
    from routers.automation import enforce_capacity
    await enforce_capacity(db, actor)
    existing = (await db.execute(select(Job).where(Job.job_type=='ingest',
        Job.result['ingestion_id'].as_integer()==item.id,
        Job.status.in_([Status.queued,Status.running])))).scalars().first()
    if existing: return existing
    job = Job(created_by_id=actor, job_type='ingest', status=Status.queued,
              steps_log=[], screenshots=[], result={'managed_queue':True,'ingestion_id':item.id})
    db.add(job)
    item.status = 'queued'
    item.retry_at = None
    event(item, 'queued', actor=actor)
    await db.flush()
    return job


async def receive(db, org_id, actor, raw, name, category='general', source_id=None, application_id=None, grant_id=None, source_key=None):
    name = Path(name.replace('\\','/')).name[:255]
    if Path(name).suffix.lower() not in EXTENSIONS or not raw or len(raw)>MAX_BYTES:
        raise HTTPException(422, 'Use a nonempty PDF, PNG, DOCX, XLSX, CSV or text file under 20 MB.')
    if category not in CATEGORIES: raise HTTPException(422, 'Unsupported document category')
    key = hashlib.sha256(f'{source_id or "manual"}:{application_id}:{grant_id}:{source_key or name.lower()}'.encode()).hexdigest()
    digest = hashlib.sha256(raw).hexdigest()
    async with lock:
        versions = (await db.execute(select(Item).where(Item.organization_id==org_id,Item.logical_key==key)
            .order_by(Item.version.desc()))).scalars().all()
        latest = versions[0] if versions else None
        # Deletion tombstones prevent scheduled sources from silently resurrecting removed bytes.
        tombstone = next((v for v in versions if v.status=='deleted' and v.sha256==digest), None)
        if tombstone: return tombstone, True
        if latest and latest.sha256 == digest:
            latest.checked_at = now()
            event(latest,'duplicate_skipped')
            await db.commit()
            return latest, True
        path = storage() / str(org_id) / (uuid.uuid4().hex + Path(name).suffix.lower())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        try:
            doc = Document(organization_id=org_id,application_id=application_id,filename=path.name,
                original_filename=name,file_path=str(path),file_size=len(raw),document_type=category,extracted_text='')
            db.add(doc)
            await db.flush()
            item = Item(organization_id=org_id,created_by_id=actor,source_id=source_id,document_id=doc.id,
                grant_id=grant_id,logical_key=key,sha256=digest,version=(latest.version+1 if latest else 1),
                category=category,current=True,extracted={},history=[],attempts=0,checked_at=now())
            db.add(item)
            await db.flush()
            for old in versions:
                old.current=False
                previous = await db.get(Document,old.document_id) if old.document_id else None
                if previous: previous.extracted_text=''; previous.ai_summary=None
                await db.execute(delete(Chunk).where(Chunk.ingestion_id==old.id))
            await queue(db,item,actor)
            db.add(AuditLog(user_id=actor,action='document_received',resource_type='ingestion',resource_id=item.id,
                            details={'sha256':digest,'version':item.version,'source_id':source_id}))
            await db.commit()
            return item, False
        except Exception:
            await db.rollback()
            path.unlink(missing_ok=True)
            raise


async def index_item(db, item, doc):
    await db.execute(delete(Chunk).where(Chunk.ingestion_id==item.id))
    # Pending financial/OCR review is visible in previews but cannot silently become AI evidence.
    doc.extracted_text = ''
    if item.status != 'ready' or not item.current: return
    lines = []
    for part in item.extracted.get('parts', []):
        for offset in range(0,len(part['text']),2000):
            text = part['text'][offset:offset+2000]
            locator = part['locator'][:220] + (f' offset {offset}' if offset else '')
            citation = f'[document {item.id} v{item.version}, {locator}]'
            db.add(Chunk(ingestion_id=item.id,organization_id=item.organization_id,locator=locator,text=text))
            lines.append(citation+' '+text)
    doc.extracted_text = '\n'.join(lines)
    doc.document_type = item.category


async def process(job_id):
    async with database.AsyncSessionLocal() as db:
        claimed = await db.execute(update(Job).where(Job.id==job_id,Job.status==Status.queued)
            .values(status=Status.running,started_at=now(),current_step='Extracting document'))
        await db.commit()
        if not claimed.rowcount: return
        job = await db.get(Job,job_id)
        item_id=job.result['ingestion_id']
        item = await db.get(Item,item_id)
        if not item or item.status=='deleted' or not item.current:
            job.status=Status.paused; job.error_message='Document removed or superseded.'
            await db.commit(); return
        doc = await db.get(Document,item.document_id)
        item.status='processing'; item.attempts+=1
        event(item,'processing',attempt=item.attempts)
        await db.commit()
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name('document_extract.py')),
                str(stored_path(doc)), doc.original_filename, stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=extraction_env())
            stdout,_ = await asyncio.wait_for(proc.communicate(),timeout=180)
            result = json.loads(stdout)
            if proc.returncode or 'error' in result: raise ValueError(result.get('error','Extraction failed.'))
            await db.refresh(item)
            if item.status=='deleted' or not item.current:
                job.status=Status.paused; await db.commit(); return
            previous=item.extracted or {}
            if previous.get('text') and previous.get('text')!=result.get('text'):
                from models.models import IngestionCorrection
                from services.ingestion_review import revision
                before_revision=revision(item)
                # Keep a transcription snapshot when an extractor update recovers content.
                # This is automated reprocessing, never a reviewer approval.
                db.add(IngestionCorrection(ingestion_id=item.id,organization_id=item.organization_id,
                    actor_id=job.created_by_id,reason='Automated extractor reprocessing; source retained and human review still required.',
                    before_text=previous['text'],after_text=result['text'],before_revision=before_revision,
                    after_revision=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=True).encode()).hexdigest()))
            item.extracted=result
            if item.category=='general': item.category=result['category']
            if item.category=='financials' and not result['needs_review']:
                result['needs_review']=True
                result['warnings'].append('Financial source requires review of all values against the original.')
                item.extracted=dict(result)
            item.status='needs_review' if result['needs_review'] else 'ready'
            item.error=None; item.retry_at=None
            await index_item(db,item,doc)
            event(item,'extracted',status=item.status,ocr=result['ocr'])
            job.status=Status.completed; job.progress_pct=100; job.completed_at=now(); job.error_message=None
            job.current_step='Extracted; review required' if item.status=='needs_review' else 'Indexed'
            await db.commit()
            if settings.AI_ENABLED and settings.APPLICATION_SOURCE_AUTO_ANALYZE and doc.application_id:
                from services.application_sources import auto_enqueue
                try:await auto_enqueue(db,doc.application_id,item.created_by_id)
                except Exception:
                    # A full/unavailable AI queue must not turn successful extraction into a parser failure.
                    await db.rollback();item=await db.get(Item,item_id)
                    item.error='Extraction succeeded; automatic AI analysis could not be queued. Use Analyze selected sources after checking queue/provider readiness.'
                    event(item,'analysis_enqueue_failed',error=item.error)
                    await db.commit()
        except asyncio.CancelledError:
            await db.rollback()
            interrupted=await db.get(Item,item_id)
            if interrupted and interrupted.status=='processing':
                interrupted.status='failed'; interrupted.retry_at=None
                interrupted.error='Processing interrupted. Retry or allow service restart recovery.'
                event(interrupted,'interrupted')
                await db.commit()
            raise
        except Exception as exc:
            await db.rollback()
            item = await db.get(Item,item_id); job = await db.get(Job,job_id)
            if item.status!='deleted':
                item.status='failed'
                item.error=str(exc) if isinstance(exc,ValueError) else 'Extraction unavailable or timed out. Retry after checking the source.'
                item.retry_at=now()+timedelta(seconds=60*2**item.attempts) if item.attempts<3 else None
                event(item,'failed',error=item.error)
            job.status=Status.failed; job.error_message=item.error; job.completed_at=now()
            await db.commit()
        finally:
            if proc and proc.returncode is None:
                proc.kill(); await proc.wait()


async def schedule():
    config_error=None
    try:
        configs = manifest()
    except Exception:
        configs=[]
        config_error='Document source configuration is unavailable. Ask the operator to restore the authorized manifest.'
    async with database.AsyncSessionLocal() as db:
        known=(await db.execute(select(Source))).scalars().all()
        configured_keys={cfg['key'] for cfg in configs}
        for source in known:
            if source.key not in configured_keys:
                source.error=config_error or 'Source authorization is no longer configured; pickup is stopped.'
        await db.commit()
        # Finish disk deletion after a crash between the database tombstone and unlink.
        deleted=(await db.execute(select(Document).join(Item,Item.document_id==Document.id).where(
            Item.status=='deleted',Document.file_path.is_not(None)).limit(50))).scalars().all()
        for doc in deleted:
            try:
                stored_path(doc).unlink(missing_ok=True)
                doc.file_path=None
            except OSError:
                pass  # denied to readers immediately; retry cleanup on the next pass
        await db.commit()
        for cfg in configs:
            source = (await db.execute(select(Source).where(Source.key==cfg['key']))).scalar_one_or_none()
            owner = await db.get(User,int(cfg['created_by_id']))
            if not owner or owner.organization_id != int(cfg['organization_id']) or not owner.is_active: continue
            if source is None:
                source=Source(key=cfg['key'],label=cfg['label'],organization_id=owner.organization_id,
                    created_by_id=owner.id,interval_seconds=max(60,int(cfg.get('interval_seconds',3600))),
                    enabled=bool(cfg.get('enabled',False)),history=[])
                db.add(source); await db.commit()
            if source.organization_id!=owner.organization_id or source.created_by_id!=owner.id:
                continue  # manifest cannot reassign a source across organizations
            if not source.enabled or (source.next_poll and source.next_poll>now()): continue
            source.last_poll=now(); source.next_poll=now()+timedelta(seconds=source.interval_seconds)
            await db.commit()
            try:
                if cfg.get('provider') in {'google_drive', 'sharepoint'}:
                    from services.cloud_documents import documents
                    count = 0
                    async for remote_id, filename, raw in documents(cfg):
                        await receive(db, source.organization_id, source.created_by_id, raw, filename,
                            cfg.get('category', 'general'), source.id, source_key=remote_id)
                        count += 1
                    source.last_success=now(); source.error=None
                    event(source,'poll_succeeded',files_checked=count,provider=cfg['provider'])
                    await db.commit()
                    continue
                root=Path(cfg['path']).resolve(strict=True)
                if not root.is_dir(): raise ValueError('Source directory unavailable.')
                count=0
                # No recursion, links, junction traversal or executable files; bounded pickup per pass.
                entries=sorted(root.iterdir(),key=lambda p:p.name.lower())
                if len(entries)>1000: raise ValueError('Source exceeds 1,000 entries; split into smaller authorized folders.')
                for path in entries:
                    if path.suffix.lower() not in EXTENSIONS or not path.is_file() or path.is_symlink(): continue
                    resolved=path.resolve(strict=True)
                    if resolved.parent!=root: continue
                    before=path.stat()
                    if before.st_size>MAX_BYTES or (time.time()-before.st_mtime)<5: continue
                    def read_bounded():
                        with path.open('rb') as handle: return handle.read(MAX_BYTES+1)
                    raw=await asyncio.to_thread(read_bounded)
                    after=path.stat()
                    if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns: continue
                    await receive(db,source.organization_id,source.created_by_id,raw,path.name,
                        cfg.get('category','general'),source.id)
                    count+=1
                source.last_success=now(); source.error=None
                event(source,'poll_succeeded',files_checked=count)
            except Exception as exc:
                await db.rollback()
                source=(await db.execute(select(Source).where(Source.key==cfg['key']))).scalar_one()
                source.error='Source pickup failed. Check authorized folder access, file limits and queue capacity.'
                from services.cloud_documents import CloudSourceError
                if isinstance(exc, CloudSourceError): source.error=str(exc)
                event(source,'poll_failed',error=source.error)
            await db.commit()
    await retry_failed()


async def retry_failed():
    """Retry only retained local documents; never poll external sources here."""
    async with database.AsyncSessionLocal()as db:
        retry = (await db.execute(select(Item).where(Item.status=='failed',Item.current==True,
            Item.retry_at<=now(),Item.attempts<3).limit(20))).scalars().all()
        for item in retry:
            await queue(db,item,item.created_by_id)
        await db.commit()


async def record_use(db, ids, org_id, target_type, target_id, field):
    for id in set(ids):
        item=await db.get(Item,id)
        if not item or item.organization_id!=org_id or item.status!='ready' or not item.current:
            raise HTTPException(409,'A source changed during generation. Regenerate using current documents.')
        db.add(DocumentUse(ingestion_id=id,organization_id=org_id,target_type=target_type,target_id=target_id,field=field))


async def retrieval(db,org_id,query=''):
    """Bounded lexical chunk retrieval; authorization is applied before ranking."""
    import re
    from sqlalchemy import case
    terms=list(dict.fromkeys(re.findall(r'[\w]{3,}',query.lower())))[:20]
    statement=select(Chunk,Item,Document).join(Item,Item.id==Chunk.ingestion_id).join(Document,Document.id==Item.document_id).where(
        Chunk.organization_id==org_id,Item.organization_id==org_id,Item.current==True,Item.status=='ready')
    if terms:
        score=sum(case((Chunk.text.icontains(term,autoescape=True),1),else_=0) for term in terms)
        statement=statement.order_by(score.desc(),Item.id.desc(),Chunk.id)
    else: statement=statement.order_by(Item.id.desc(),Chunk.id)
    rows=(await db.execute(statement.limit(12))).all()
    from services.ingestion_review import freshness
    return [{'ingestion_id':i.id,'title':f'{d.original_filename} [document {i.id} v{i.version}, {c.locator}]',
        'excerpt':(f'[Evidence review overdue since {freshness(i)["review_due"]}; verify currency before relying on these figures.]\n' if freshness(i)['stale'] else '')+c.text,
        'freshness':freshness(i),'document_type':i.category,'source_url':f'/gfm-app/documents?document={i.id}'} for c,i,d in rows]


async def remove(db, item, actor):
    # Caller passes a tenant-scoped item. Redact persisted derivatives with recorded provenance.
    uses=(await db.execute(select(DocumentUse).where(DocumentUse.ingestion_id==item.id,
        DocumentUse.organization_id==item.organization_id))).scalars().all()
    for use in uses:
        if use.target_type=='record':
            row=await db.get(OrganizationRecord,use.target_id)
            if row and row.organization_id==item.organization_id:
                row.body='[Source document deleted. Regeneration and review required.]'
                row.data={'status':'review','source_deleted':item.id,'matches':[],'sources':[],'feedback':[],'at':now().isoformat()}; row.history=[]; row.revision+=1
        elif use.target_type=='conversation':
            row=await db.get(AIConversation,use.target_id)
            if row:
                row.messages=[]; row.context=''
        elif use.target_type=='application':
            row=await db.get(GrantApplication,use.target_id)
            if row and row.organization_id==item.organization_id and use.field in {'proposal_text','budget_narrative'}:
                setattr(row,use.field,'[Source document deleted. Regeneration and approval required.]')
    await db.execute(delete(DocumentUse).where(DocumentUse.ingestion_id==item.id))
    await db.execute(delete(Chunk).where(Chunk.ingestion_id==item.id))
    from models.models import IngestionCorrection
    await db.execute(update(IngestionCorrection).where(IngestionCorrection.ingestion_id==item.id,
        IngestionCorrection.organization_id==item.organization_id).values(
        before_text='[Document deleted]',after_text='[Document deleted]',reason='[Document deleted]'))
    doc=await db.get(Document,item.document_id) if item.document_id else None
    if doc:
        doc.extracted_text=''; doc.ai_summary=None
    item.status='deleted'; item.extracted={}; item.error=None; item.retry_at=None
    item.history=[{k:v for k,v in e.items() if k!='reason'} for e in item.history or []]
    event(item,'deleted',actor=actor,derivatives_redacted=len(uses))
    db.add(AuditLog(user_id=actor,action='document_deleted',resource_type='ingestion',resource_id=item.id,
        details={'derivatives_redacted':len(uses)}))
    await db.commit()
    if doc and doc.file_path:
        stored_path(doc).unlink(missing_ok=True)
        doc.file_path=None
        await db.commit()
