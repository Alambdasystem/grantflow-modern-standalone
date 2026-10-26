"""Tenant-scoped document ingestion, previews and source administration."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from db import database
from auth.jwt_handler import get_current_user_token
from routers.operations import scope
from models.models import IngestionDocument as Item, IngestionSource as Source, Document, DocumentChunk as Chunk, GrantApplication, Grant
from services import document_ingestion as service
from services.document_extract import MAX_BYTES
from services.ingestion_review import revision, freshness
from models.models import IngestionCorrection, AutomationJob, IngestionWorkerHeartbeat
from datetime import date, datetime
import difflib

router=APIRouter(prefix='/api/ingestion',tags=['document ingestion'])


@router.get('/legacy-documents')
async def legacy_documents(db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    # Request-local ownership filtering applies to Document, including historical
    # organization evidence that predates the ingestion worker/index.
    rows=(await db.execute(select(Document).where(~Document.id.in_(select(Item.document_id).where(Item.document_id.is_not(None))))
        .order_by(Document.id))).scalars().all()
    return [{'id':d.id,'name':d.original_filename or d.filename,'application_id':d.application_id,
        'document_type':d.document_type,'size':d.file_size,'extracted_text':d.extracted_text,
        'ai_summary':d.ai_summary,'created_at':d.created_at} for d in rows]


@router.get('/legacy-documents/{id}/original')
async def legacy_original(id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    from pathlib import Path
    from config import settings
    doc=await db.get(Document,id)
    if not doc or not doc.file_path: raise HTTPException(404,'Document not found')
    root=Path(settings.UPLOAD_DIR).resolve();path=Path(doc.file_path).resolve()
    if root not in path.parents or not path.is_file(): raise HTTPException(404,'Original unavailable')
    return FileResponse(path,filename=doc.original_filename or doc.filename,media_type='application/octet-stream',
        headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})


async def owned(db,token,id):
    user,org=await scope(db,token)
    item=(await db.execute(select(Item).where(Item.id==id,Item.organization_id==org.id))).scalar_one_or_none()
    if not item: raise HTTPException(404,'Document not found')
    doc=await db.get(Document,item.document_id) if item.document_id else None
    if doc is None: raise HTTPException(404,'Document not found')
    return user,org,item,doc


def output(item,doc):
    return {'id':item.id,'name':doc.original_filename,'status':item.status,'version':item.version,
        'current':item.current,'category':item.category,'sha256':item.sha256,'size':doc.file_size,
        'source_id':item.source_id,'grant_id':item.grant_id,'application_id':doc.application_id,
        'error':item.error,'attempts':item.attempts,'retry_at':item.retry_at,
        'created_at':item.created_at,'checked_at':item.checked_at,'reviewed_at':item.reviewed_at,
        'stale':freshness(item)['stale'],'freshness':freshness(item),'extraction_revision':revision(item),
        'warnings':item.extracted.get('warnings',[]),'ocr':item.extracted.get('ocr',False),
        'citation':f'[document {item.id} v{item.version}]',
        'url':f'/gfm-app/documents?document={item.id}'}


@router.get('/documents')
async def documents(db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,org=await scope(db,token)
    rows=(await db.execute(select(Item,Document).join(Document,Document.id==Item.document_id)
        .where(Item.organization_id==org.id).order_by(Item.id.desc()).limit(200))).all()
    return [output(i,d) for i,d in rows]


@router.post('/upload',status_code=202)
async def upload(file:UploadFile=File(...),category:str=Form('general'),application_id:int|None=Form(None),
                 grant_id:int|None=Form(None),db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    user,org=await scope(db,token)
    if application_id:
        app=await db.get(GrantApplication,application_id)
        if not app or app.organization_id!=org.id: raise HTTPException(404,'Application not found')
        if grant_id and grant_id!=app.grant_id: raise HTTPException(422,'Grant does not match the application')
        grant_id=app.grant_id
    if grant_id and await db.get(Grant,grant_id) is None: raise HTTPException(404,'Grant not found')
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise HTTPException(413,'Maximum upload size is 20 MB')
    item,duplicate=await service.receive(db,org.id,user.id,raw,file.filename or '',category,
                                       application_id=application_id,grant_id=grant_id)
    doc=await db.get(Document,item.document_id)
    return {**output(item,doc),'duplicate':duplicate}


@router.get('/documents/{id}')
async def detail(id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,_,item,doc=await owned(db,token,id)
    return {**output(item,doc),'extracted':item.extracted,'history':item.history}


@router.get('/documents/{id}/original')
async def original(id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,_,item,doc=await owned(db,token,id)
    if item.status=='deleted': raise HTTPException(410,'Document deleted')
    path=service.stored_path(doc)
    if not path.is_file(): raise HTTPException(404,'Original unavailable')
    return FileResponse(path,filename=doc.original_filename,media_type='application/octet-stream',
        headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})


@router.post('/documents/{id}/retry')
async def retry(id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    user,_,item,doc=await owned(db,token,id)
    if item.status=='deleted' or not item.current: raise HTTPException(409,'Removed or superseded document')
    if item.status in {'processing','queued'}: raise HTTPException(409,'Processing is already pending')
    if not service.stored_path(doc).is_file(): raise HTTPException(409,'Original missing; upload a new version')
    item.reviewed_at=None; item.reviewed_by=None; item.attempts=0
    doc.extracted_text=''; doc.ai_summary=None
    from sqlalchemy import delete
    await db.execute(delete(Chunk).where(Chunk.ingestion_id==id))
    await service.queue(db,item,user.id)
    await db.commit()
    return output(item,doc)


class Review(BaseModel):
    confirmed:bool
    sha256:str
    revision:str|None=None


@router.post('/documents/{id}/review')
async def review(id:int,payload:Review,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    if token['role'] not in {'admin','reviewer'}: raise HTTPException(403,'Reviewer or administrator required')
    user,_,item,doc=await owned(db,token,id)
    if not payload.confirmed or payload.sha256!=item.sha256 or item.status!='needs_review' or not item.current:
        raise HTTPException(409,'Confirm the current extraction against the original before approval')
    if (payload.revision is not None or item.extracted.get('corrected')) and payload.revision!=revision(item):
        raise HTTPException(409,'Extraction changed; reload and review the current revision')
    changed=await db.execute(update(Item).where(Item.id==id,Item.current==True,Item.status=='needs_review',
        Item.extracted==item.extracted).values(status='ready',reviewed_by=user.id,reviewed_at=service.now()))
    if not changed.rowcount: raise HTTPException(409,'Extraction changed; reload before approval')
    await db.refresh(item)
    service.event(item,'extraction_approved',actor=user.id,sha256=item.sha256)
    await service.index_item(db,item,doc)
    await db.commit()
    return output(item,doc)


class Correction(BaseModel):
    text:str=Field(min_length=1,max_length=500000)
    reason:str=Field(min_length=5,max_length=1000)
    revision:str=Field(min_length=64,max_length=64)


@router.post('/documents/{id}/corrections')
async def correct(id:int,payload:Correction,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    if token['role'] not in {'admin','reviewer'}: raise HTTPException(403,'Reviewer or administrator required')
    user,org,item,doc=await owned(db,token,id)
    if not item.current or item.status!='needs_review' or revision(item)!=payload.revision:
        raise HTTPException(409,'Reload the pending extraction before correcting it. Reprocess approved documents first.')
    if not payload.text.strip() or not payload.reason.strip(): raise HTTPException(422,'Text and correction reason are required')
    before=item.extracted
    if payload.text==before.get('text'): raise HTTPException(422,'No text changes to save')
    extracted={**before,'text':payload.text,'parts':[{'locator':'reviewer-corrected transcription','text':payload.text}],
        'tables':[],'corrected':True,'needs_review':True,
        'warnings':list(dict.fromkeys(before.get('warnings',[])+['Reviewer-corrected transcription; original file retained for verification.']))}
    changed=await db.execute(update(Item).where(Item.id==id,Item.current==True,Item.status=='needs_review',
        Item.extracted==before).values(extracted=extracted,reviewed_by=None,reviewed_at=None))
    if not changed.rowcount: raise HTTPException(409,'Extraction changed; reload before correcting')
    await db.refresh(item)
    db.add(IngestionCorrection(ingestion_id=id,organization_id=org.id,actor_id=user.id,reason=payload.reason,
        before_text=before.get('text',''),after_text=payload.text,before_revision=payload.revision,after_revision=revision(item)))
    service.event(item,'extraction_corrected',actor=user.id,reason=payload.reason,revision=revision(item))
    await service.index_item(db,item,doc)
    await db.commit()
    return output(item,doc)


@router.get('/documents/{id}/corrections')
async def correction_history(id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,org,_,_=await owned(db,token,id)
    rows=(await db.execute(select(IngestionCorrection).where(IngestionCorrection.ingestion_id==id,
        IngestionCorrection.organization_id==org.id).order_by(IngestionCorrection.id.desc()).limit(20))).scalars().all()
    result=[]
    for row in rows:
        # Full snapshots are retained in the audit table; bounded previews keep the UI responsive.
        diff='\n'.join(difflib.unified_diff(row.before_text[:20000].splitlines(),row.after_text[:20000].splitlines(),lineterm=''))
        result.append({'id':row.id,'actor':row.actor_id,'reason':row.reason,'at':row.created_at,
            'revision':row.after_revision,'diff':diff[:20000],'truncated':max(len(diff),len(row.before_text),len(row.after_text))>20000})
    return result


class FreshnessUpdate(BaseModel):
    as_of:date
    review_due:date


@router.put('/documents/{id}/freshness')
async def set_freshness(id:int,payload:FreshnessUpdate,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    if token['role'] not in {'admin','reviewer'}: raise HTTPException(403,'Reviewer or administrator required')
    user,_,item,doc=await owned(db,token,id)
    if not item.current or item.status=='deleted': raise HTTPException(409,'Use the current document')
    if payload.as_of>service.now().date() or payload.review_due<payload.as_of:
        raise HTTPException(422,'Evidence date cannot be in the future; review date must follow the evidence date')
    item.evidence_date=payload.as_of; item.review_due=payload.review_due
    service.event(item,'freshness_set',actor=user.id,as_of=payload.as_of.isoformat(),review_due=payload.review_due.isoformat())
    await db.commit()
    return output(item,doc)


@router.get('/monitor')
async def monitor(db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,org=await scope(db,token)
    from services import job_queue
    from datetime import timezone
    from config import settings
    import json
    from pathlib import Path
    rows=(await db.execute(select(Item,Document).join(Document,Document.id==Item.document_id)
        .where(Item.organization_id==org.id,Item.current==True,Item.status!='deleted'))).all()
    counts={}; stale=[]; pending=[]; failures=[]
    for item,doc in rows:
        counts[item.status]=counts.get(item.status,0)+1
        if freshness(item)['stale']: stale.append({'id':item.id,'name':doc.original_filename,**freshness(item)})
        if item.status=='failed': failures.append({'id':item.id,'name':doc.original_filename,'error':item.error,'retry_at':item.retry_at,'attempts':item.attempts})
    jobs=(await db.execute(select(AutomationJob).join(Item,AutomationJob.result['ingestion_id'].as_integer()==Item.id)
        .join(Document,Document.id==Item.document_id)
        .where(Item.organization_id==org.id,AutomationJob.job_type=='ingest',AutomationJob.status.in_(['queued','running'])))).scalars().all()
    for job in jobs:
        pending.append(max(0,int((service.now()-job.created_at.replace(tzinfo=None)).total_seconds())))
    poll=job_queue.last_poll_at
    age=(service.now().replace(tzinfo=timezone.utc)-datetime.fromisoformat(poll)).total_seconds() if poll else None
    workers=[]; registry_error=False
    if settings.INGESTION_WORKER_REGISTRY:
        try:
            registry=json.loads(Path(settings.INGESTION_WORKER_REGISTRY).read_text(encoding='utf-8-sig'))
            for worker in registry:
                if org.id not in worker['organization_ids'] or not worker.get('enabled'): continue
                pulse=await db.get(IngestionWorkerHeartbeat,worker['id'])
                recent=bool(pulse and (service.now()-pulse.seen_at).total_seconds()<360)
                workers.append({'id':worker['id'],'last_seen':pulse.seen_at if pulse else None,'status':'recently_seen' if recent else 'not_seen_recently'})
        except Exception: registry_error=True
    alerts=[]
    if failures: alerts.append(f'{len(failures)} document(s) failed processing.')
    if stale: alerts.append(f'{len(stale)} document(s) are due for evidence review.')
    if max(pending,default=0)>300: alerts.append('Ingestion work has waited over five minutes. Check worker connectivity and capacity.')
    if jobs and (age is None or age>90): alerts.append('Coordinator polling is not recent; check service health.')
    if registry_error: alerts.append('Worker registry is unavailable; contact the operator.')
    if any(w['status']=='not_seen_recently' for w in workers): alerts.append('An assigned extraction worker has not checked in recently.')
    sources=(await db.execute(select(Source).where(Source.organization_id==org.id,Source.enabled==True))).scalars().all()
    for source in sources:
        if source.error: alerts.append(f'Source {source.label}: {source.error}')
        elif source.last_poll and (service.now()-source.last_poll).total_seconds()>source.interval_seconds+120:
            alerts.append(f'Source {source.label} missed its scheduled pickup.')
    return {'counts':counts,'stale_documents':len(stale),'freshness_items':stale[:50],'failures':failures[:50],
        'oldest_pending_seconds':max(pending,default=0),'last_poll_at':poll,
        'coordinator_status':'recently_polling' if age is not None and age<90 else 'not_seen_recently',
        'local_extraction_enabled':settings.INGESTION_LOCAL_WORKER_ENABLED,'workers':workers,'alerts':alerts}


@router.delete('/documents/{id}')
async def delete_document(id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    if token['role']!='admin': raise HTTPException(403,'Administrator required to delete sources and derived content')
    user,org,item,_=await owned(db,token,id)
    async with database.AsyncSessionLocal() as cleanup:
        row=(await cleanup.execute(select(Item).where(Item.id==item.id,Item.organization_id==org.id))).scalar_one()
        await service.remove(cleanup,row,user.id)
    return {'deleted':id}


@router.get('/search')
async def search(q:str=Query('',max_length=200),db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,org=await scope(db,token)
    query=select(Chunk,Item,Document).join(Item,Item.id==Chunk.ingestion_id).join(Document,Document.id==Item.document_id).where(
        Chunk.organization_id==org.id,Item.organization_id==org.id,Item.current==True,Item.status=='ready')
    if q.strip(): query=query.where(Chunk.text.contains(q.strip(),autoescape=True))
    rows=(await db.execute(query.order_by(Chunk.id.desc()).limit(30))).all()
    return [{'text':c.text,'locator':c.locator,'document':output(i,d),
             'citation':f'[document {i.id} v{i.version}, {c.locator}]'} for c,i,d in rows]


@router.get('/sources')
async def sources(db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    _,org=await scope(db,token)
    rows=(await db.execute(select(Source).where(Source.organization_id==org.id))).scalars().all()
    return {'sources':[{'id':s.id,'label':s.label,'enabled':s.enabled,'interval_seconds':s.interval_seconds,
        'last_poll':s.last_poll,'last_success':s.last_success,'next_poll':s.next_poll,'error':s.error,'history':s.history} for s in rows],
        'notice':'Only operator-authorized folders configured for this organization can be monitored. Local folders, Google Drive and SharePoint are supported; cloud pickup requires a folder mapping and configured read credentials.'}


class SourceUpdate(BaseModel):
    enabled:bool
    interval_seconds:int=Field(ge=60,le=604800)


@router.put('/sources/{id}')
async def configure(id:int,payload:SourceUpdate,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    if token['role']!='admin': raise HTTPException(403,'Administrator required')
    user,org=await scope(db,token)
    source=(await db.execute(select(Source).where(Source.id==id,Source.organization_id==org.id))).scalar_one_or_none()
    if not source: raise HTTPException(404,'Source not found')
    source.enabled=payload.enabled; source.interval_seconds=payload.interval_seconds; source.next_poll=service.now()
    service.event(source,'schedule_changed',actor=user.id,**payload.model_dump())
    await db.commit()
    return {'saved':True}
