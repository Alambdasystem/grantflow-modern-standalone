import asyncio
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_ingestion import client, api, upload, headers


@pytest.fixture
def workers(api,tmp_path,monkeypatch):
    from config import settings
    from routers import ingestion_workers
    registry=tmp_path/'workers.json'
    registry.write_text(json.dumps([{'id':name,'enabled':True,'organization_ids':[org],
        'token_sha256':hashlib.sha256((name*32).encode()).hexdigest()} for name,org in [('a',1),('b',1),('c',2)]]))
    monkeypatch.setattr(settings,'INGESTION_WORKER_REGISTRY',str(registry))
    api.app.include_router(ingestion_workers.router)
    return api,registry


def auth(worker='a',lease=None):
    out={'Authorization':'Bearer '+worker*32}
    if lease: out['X-Ingestion-Lease']=lease
    return out


def test_claim_exclusive_scope_review_and_revocation(workers):
    api,registry=workers
    item=upload(api)
    assert api.post('/api/ingestion-workers/claim').status_code==401
    assert api.post('/api/ingestion-workers/claim',headers=auth('c')).json()['job_id'] is None
    with ThreadPoolExecutor(2) as pool:
        claims=list(pool.map(lambda name:api.post('/api/ingestion-workers/claim',headers=auth(name)).json(),['a','b']))
    assert sum(bool(c['job_id']) for c in claims)==1
    monitor=api.get('/api/ingestion/monitor',headers=headers()).json()
    assert {w['id'] for w in monitor['workers']}=={'a','b'}
    assert all(w['status']=='recently_seen' for w in monitor['workers'])
    index=next(i for i,c in enumerate(claims) if c['job_id'])
    name=['a','b'][index]; claim=claims[index]
    root=f'/api/ingestion-workers/{claim["job_id"]}'
    assert api.get(root+'/original',headers=auth(name,'bad')).status_code==409
    original=api.get(root+'/original',headers=auth(name,claim['lease_token']))
    assert original.status_code==200
    from services.document_extract import extract
    result=extract(original.content,'mission.txt')
    result['needs_review']=False
    response=api.post(root+'/complete',headers=auth(name,claim['lease_token']),json={'result':result})
    assert response.status_code==200,response.text
    assert api.get(f'/api/ingestion/documents/{item["id"]}',headers=headers()).json()['status']=='needs_review'
    assert api.get('/api/ingestion/search?q=education',headers=headers()).json()==[]
    assert api.post(root+'/complete',headers=auth(name,claim['lease_token']),json={'result':result}).status_code==409
    registry.write_text('[]')
    assert api.post('/api/ingestion-workers/claim',headers=auth(name)).status_code==401


def test_expired_lease_recovery_and_restart(workers,monkeypatch):
    api,_=workers
    upload(api)
    old=api.post('/api/ingestion-workers/claim',headers=auth()).json()
    from db import database
    from services import job_queue
    from models.models import AutomationJob
    monkeypatch.setattr(job_queue,'AsyncSessionLocal',database.AsyncSessionLocal)
    asyncio.run(job_queue.recover())
    assert api.post('/api/ingestion-workers/claim',headers=auth('b')).json()['job_id'] is None
    async def expire():
        async with database.AsyncSessionLocal() as db:
            job=await db.get(AutomationJob,old['job_id'])
            job.result={**job.result,'lease_expires':time.time()-1};await db.commit()
    asyncio.run(expire())
    new=api.post('/api/ingestion-workers/claim',headers=auth('b')).json()
    assert new['job_id']==old['job_id'] and new['lease_token']!=old['lease_token']
    root=f'/api/ingestion-workers/{old["job_id"]}'
    assert api.post(root+'/complete',headers=auth('a',old['lease_token']),json={'failed':True}).status_code==409
    assert api.post(root+'/complete',headers=auth('b',new['lease_token']),json={'failed':True}).status_code==200


def test_deleted_document_cannot_be_completed(workers):
    api,_=workers
    item=upload(api)
    claim=api.post('/api/ingestion-workers/claim',headers=auth()).json()
    assert api.delete(f'/api/ingestion/documents/{item["id"]}',headers=headers('admin')).status_code==200
    root=f'/api/ingestion-workers/{claim["job_id"]}'
    assert api.get(root+'/original',headers=auth('a',claim['lease_token'])).status_code==409
    assert api.post(root+'/complete',headers=auth('a',claim['lease_token']),json={'failed':True}).status_code==409
