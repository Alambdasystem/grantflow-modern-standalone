"""Saved control-plane contracts, not real provider/MFA execution."""
import asyncio
import pytest
from test_ingestion import client,api,headers
from db import database
from models.models import AutomationJob,AutomationJobStatus,IngestionSource
from routers import automation,providers

@pytest.fixture
def controls(api):
    api.app.include_router(automation.router);api.app.include_router(providers.router)
    async def seed():
        async with database.AsyncSessionLocal() as db:
            db.add(IngestionSource(id=1,key='synthetic-control',label='Synthetic folder',organization_id=1,created_by_id=1,enabled=True))
            db.add(AutomationJob(id=500,application_id=1,created_by_id=1,job_type='renew',status=AutomationJobStatus.awaiting_approval,progress_pct=0,steps_log=[],screenshots=[],result={}))
            await db.commit()
    asyncio.run(seed());return api

def test_source_pause_and_interval_validation(controls):
    path='/api/ingestion/sources/1'
    assert controls.put(path,headers=headers(),json={'enabled':False,'interval_seconds':90}).status_code==403
    assert controls.put(path,headers=headers('admin'),json={'enabled':False,'interval_seconds':59}).status_code==422
    assert controls.put(path,headers=headers('admin'),json={'enabled':False,'interval_seconds':90}).status_code==200
    source=controls.get('/api/ingestion/sources',headers=headers()).json()['sources'][0]
    assert source['enabled'] is False and source['interval_seconds']==90

def test_human_job_approval_state_and_role_gate(controls):
    path='/api/automation/jobs/500/approve'
    assert controls.post(path,headers=headers(),json={'action':'approve'}).status_code==403
    assert controls.post(path,headers=headers('admin'),json={'action':'approve'}).status_code==200
    assert controls.get('/api/automation/jobs/500',headers=headers()).json()['status']=='running'
    assert controls.post(path,headers=headers('admin'),json={'action':'approve'}).status_code==409

def test_two_factor_callback_queue_contract_only(controls):
    import sys
    sys.path.insert(0,'/app/automation')
    from orchestrator import _two_factor_queues
    queue=asyncio.Queue();_two_factor_queues[500]=queue
    try:
        path='/api/providers/jobs/500/2fa'
        assert controls.post(path,headers=headers(),json={'code':'000000'}).status_code==403
        assert controls.post(path,headers=headers('admin'),json={'code':''}).status_code==422
        assert controls.post(path,headers=headers('admin'),json={'code':'000000'}).status_code==200
        assert queue.get_nowait()=='000000'
    finally:_two_factor_queues.pop(500,None)
