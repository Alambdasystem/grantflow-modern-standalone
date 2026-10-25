"""Organization-scoped extraction workers; the coordinator alone owns the database."""
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from config import settings
from db import database
from models.models import AutomationJob as Job, AutomationJobStatus as Status, IngestionDocument as Item, Document, IngestionWorkerHeartbeat
from services import document_ingestion as service
from services.document_extract import MAX_TEXT, CATEGORIES

router = APIRouter(prefix='/api/ingestion-workers', tags=['ingestion-workers'])
LEASE_SECONDS = 300


def identity(authorization: str = Header('')):
    try:
        scheme, secret = authorization.split(' ', 1)
        if scheme.lower() != 'bearer' or len(secret) < 32: raise ValueError()
        digest = hashlib.sha256(secret.encode()).hexdigest()
        registry = json.loads(Path(settings.INGESTION_WORKER_REGISTRY).read_text(encoding='utf-8-sig'))
        for entry in registry:
            if entry.get('enabled') and hmac.compare_digest(digest, entry['token_sha256']):
                return entry
    except Exception:
        pass
    raise HTTPException(401, 'Worker credential missing, revoked or invalid')


async def recover_expired():
    async with database.AsyncSessionLocal() as db:
        rows=(await db.execute(select(Job).where(Job.job_type=='ingest',Job.status==Status.running,
            Job.result['lease_expires'].as_float()<=time.time()))).scalars().all()
        for job in rows:
            changed=await db.execute(update(Job).where(Job.id==job.id,Job.status==Status.running,
                Job.result['lease_token'].as_string()==job.result['lease_token']).values(
                status=Status.queued,result={k:v for k,v in job.result.items() if not k.startswith('lease_')},
                current_step='Worker lease expired; queued for recovery'))
            if changed.rowcount:
                item=await db.get(Item,job.result['ingestion_id'])
                if item and item.current and item.status!='deleted':
                    item.status='queued'; service.event(item,'worker_lease_expired')
                    if item.attempts>=3:
                        item.status='failed'; item.retry_at=None
                        item.error='Worker lease expired three times. Check worker connectivity and retry manually.'
                        job.status=Status.failed; job.error_message=item.error
        await db.commit()


@router.post('/claim')
async def claim(worker=Depends(identity)):
    await recover_expired()
    async with database.AsyncSessionLocal() as db:
        pulse=await db.get(IngestionWorkerHeartbeat,worker['id'])
        if pulse: pulse.seen_at=service.now()
        else: db.add(IngestionWorkerHeartbeat(worker_id=worker['id'],seen_at=service.now()))
        await db.commit()
        rows=(await db.execute(select(Job,Item).join(Item,Job.result['ingestion_id'].as_integer()==Item.id).where(
            Job.job_type=='ingest',Job.status==Status.queued,Item.organization_id.in_(worker['organization_ids']),
            Item.current==True,Item.status!='deleted').order_by(Job.id).limit(20))).all()
        for job,item in rows:
            lease=secrets.token_urlsafe(32)
            result={**job.result,'lease_token':lease,'lease_worker':worker['id'],'lease_expires':time.time()+LEASE_SECONDS}
            changed=await db.execute(update(Job).where(Job.id==job.id,Job.status==Status.queued).values(
                status=Status.running,result=result,started_at=service.now(),current_step='Remote extraction'))
            if not changed.rowcount: continue
            item.status='processing'; item.attempts+=1
            service.event(item,'worker_claimed',worker=worker['id'],attempt=item.attempts)
            doc=await db.get(Document,item.document_id)
            await db.commit()
            return {'job_id':job.id,'lease_token':lease,'lease_seconds':LEASE_SECONDS,
                    'filename':doc.original_filename,'sha256':item.sha256}
    return {'job_id':None}


async def owned(db, id, lease, worker):
    job=await db.get(Job,id)
    result=job.result if job else {}
    if not job or job.status!=Status.running or result.get('lease_worker')!=worker['id'] or \
       not hmac.compare_digest(result.get('lease_token',''),lease) or result.get('lease_expires',0)<=time.time():
        raise HTTPException(409,'Worker lease is no longer active')
    item=await db.get(Item,result['ingestion_id'])
    if not item or item.organization_id not in worker['organization_ids'] or not item.current or item.status=='deleted':
        raise HTTPException(409,'Document is no longer available to this worker')
    return job,item,await db.get(Document,item.document_id)


@router.get('/{id}/original')
async def original(id:int, x_ingestion_lease:str=Header(''), worker=Depends(identity)):
    async with database.AsyncSessionLocal() as db:
        _,_,doc=await owned(db,id,x_ingestion_lease,worker)
        return FileResponse(service.stored_path(doc),media_type='application/octet-stream',
                            headers={'Cache-Control':'no-store'})


def validate_result(result):
    try:
        assert isinstance(result,dict) and isinstance(result['text'],str) and 0<len(result['text'])<=MAX_TEXT
        assert result['category'] in CATEGORIES and isinstance(result['ocr'],bool)
        assert isinstance(result['needs_review'],bool) and isinstance(result['metadata'],dict)
        assert isinstance(result['warnings'],list) and len(result['warnings'])<=1000
        assert all(isinstance(w,str) and len(w)<=2000 for w in result['warnings'])
        parts=result['parts']; assert isinstance(parts,list) and 0<len(parts)<=20000
        assert all(isinstance(p['locator'],str) and len(p['locator'])<=220 and isinstance(p['text'],str) for p in parts)
        assert sum(len(p['text']) for p in parts)<=MAX_TEXT
        assert isinstance(result['tables'],list) and len(result['tables'])<=1000
        for table in result['tables']:
            assert isinstance(table['locator'],str) and isinstance(table['rows'],list) and len(table['rows'])<=20000
            assert all(isinstance(row,list) and all(c is None or isinstance(c,str) for c in row) for row in table['rows'])
        return result
    except (AssertionError,KeyError,TypeError):
        raise HTTPException(422,'Invalid extraction result') from None


@router.post('/{id}/complete')
async def complete(id:int,request:Request,x_ingestion_lease:str=Header(''),worker=Depends(identity)):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>8*1024*1024: raise HTTPException(413,'Extraction result too large')
    try: payload=json.loads(raw)
    except Exception: raise HTTPException(422,'Invalid JSON') from None
    if not isinstance(payload,dict): raise HTTPException(422,'Invalid extraction response')
    result=validate_result(payload['result']) if 'result' in payload else None
    if result is None and payload.get('failed') is not True: raise HTTPException(422,'Extraction result required')
    async with database.AsyncSessionLocal() as db:
        job,item,doc=await owned(db,id,x_ingestion_lease,worker)
        # Fence completion and all derived writes in the same transaction.
        changed=await db.execute(update(Job).where(Job.id==id,Job.status==Status.running,
            Job.result['lease_token'].as_string()==x_ingestion_lease,
            Job.result['lease_expires'].as_float()>time.time()).values(status=Status.completed if result else Status.failed))
        if not changed.rowcount: raise HTTPException(409,'Worker lease changed')
        await db.refresh(item)
        if not item.current or item.status=='deleted': raise HTTPException(409,'Document removed or superseded')
        if result:
            item.extracted=result
            if item.category=='general': item.category=result['category']
            # Remote output is always reviewed, even if its classifier says otherwise.
            result['needs_review']=True
            result['warnings'].append('Remote extraction requires verification against the original before indexing.')
            item.extracted=dict(result); item.status='needs_review'; item.error=None; item.retry_at=None
            await service.index_item(db,item,doc)
            job.progress_pct=100; job.current_step='Remote extraction awaiting review'
        else:
            from datetime import timedelta
            item.status='failed'; item.error='Remote extraction failed. Review the original or retry.'
            item.retry_at=service.now()+timedelta(seconds=60*2**item.attempts) if item.attempts<3 else None
            job.error_message=item.error
        job.completed_at=service.now()
        job.result={k:v for k,v in job.result.items() if not k.startswith('lease_')}
        service.event(item,'worker_completed' if result else 'worker_failed',worker=worker['id'])
        await db.commit()
    return {'saved':True}
