"""Public discovery release must never release imported/portal/renewal jobs."""
import asyncio
from types import SimpleNamespace
import pytest
from test_integration_audit import client, template_db, headers, ok
from services.migration_safety import public_discovery


@pytest.mark.parametrize('kind,marked,application,portal,url,expected', [
    ('scrape',True,None,None,None,True),
    ('scrape',False,None,None,None,False),
    ('renew',True,None,None,None,False),
    ('submit',True,None,None,None,False),
    ('scrape',True,1,None,None,False),
    ('scrape',True,None,'grants_gov',None,False),
    ('scrape',True,None,None,'https://example.com',False),
])
def test_only_server_stamped_uncredentialed_search_is_released(kind,marked,application,portal,url,expected):
    job=SimpleNamespace(job_type=kind,result={'public_discovery_v1':marked},application_id=application,portal_key=portal,portal_url=url)
    assert public_discovery(job) is expected


def test_new_search_is_stamped_without_releasing_old_search_or_hold(client):
    from db import database
    from models.auth_models import MigrationSafety
    from models.models import AutomationJob,AutomationJobStatus
    async def seed():
        async with database.AsyncSessionLocal() as db:
            db.add(MigrationSafety(id=1,external_jobs_paused=True,source_cutoff='synthetic'))
            db.add(AutomationJob(job_type='scrape',status=AutomationJobStatus.queued,
                created_by_id=1,result={'managed_queue':True,'query':'synthetic education'}))
            await db.commit()
    asyncio.run(seed())
    payload={'job_type':'scrape','params':{'query':'synthetic education'}}
    job=ok(client.post('/api/automation/jobs',json=payload,headers=headers()),201)
    assert job['result']['public_discovery_v1'] is True
    again=ok(client.post('/api/automation/jobs',json=payload,headers=headers()),201)
    assert again['id']==job['id']
    async def check():
        async with database.AsyncSessionLocal() as db:
            assert (await db.get(MigrationSafety,1)).external_jobs_paused is True
    asyncio.run(check())
    ok(client.post('/api/automation/jobs',json={**payload,'portal_key':'grants_gov'},headers=headers()),422)


def test_public_search_never_launches_browser_on_empty_http_sources(monkeypatch):
    from automation.agents.grant_scraper import GrantScraperAgent
    async def empty(*args,**kwargs):return []
    monkeypatch.setattr(GrantScraperAgent,'_scrape_via_http',empty)
    import playwright.async_api
    def denied():raise AssertionError('Public discovery must not launch browser')
    monkeypatch.setattr(playwright.async_api,'async_playwright',denied)
    assert asyncio.run(GrantScraperAgent().scrape('synthetic',allow_browser=False))==[]


def test_runner_allows_new_public_job_but_pauses_imported_and_renewal_jobs(client,monkeypatch):
    from db import database
    from models.models import AutomationJob,AutomationJobStatus
    from models.auth_models import MigrationSafety
    from routers.automation import _run_automation_job
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'automation'))
    import orchestrator
    calls=[]
    async def execute(job_id,events):calls.append(job_id)
    monkeypatch.setattr(orchestrator,'run_job',execute)
    async def run():
        async with database.AsyncSessionLocal() as db:
            db.add(MigrationSafety(id=1,external_jobs_paused=True,source_cutoff='synthetic'))
            jobs=[AutomationJob(job_type=kind,status=AutomationJobStatus.queued,
                  created_by_id=1,result={'managed_queue':True,**marker}) for kind,marker in
                  [('scrape',{}),('renew',{'public_discovery_v1':True}),('scrape',{'public_discovery_v1':True})]]
            db.add_all(jobs);await db.commit();ids=[j.id for j in jobs]
        for job_id in ids:await _run_automation_job(job_id)
        assert calls==[ids[2]]
        async with database.AsyncSessionLocal() as db:
            assert (await db.get(MigrationSafety,1)).external_jobs_paused
            for job_id in ids[:2]:assert (await db.get(AutomationJob,job_id)).status==AutomationJobStatus.paused
    asyncio.run(run())


def test_actual_orchestrator_completes_only_new_public_search_under_hold(client,monkeypatch):
    from db import database
    from models.models import AutomationJob,AutomationJobStatus
    from models.auth_models import MigrationSafety
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'automation'))
    import orchestrator
    from agents.grant_scraper import GrantScraperAgent
    monkeypatch.setattr(orchestrator,'AsyncSessionLocal',database.AsyncSessionLocal)
    calls=[]
    async def source(self,query,**kwargs):
        calls.append(kwargs)
        return [{'title':'Synthetic HTTP funding record','source_url':'https://funder.example/test'}]
    monkeypatch.setattr(GrantScraperAgent,'scrape',source)
    async def run():
        async with database.AsyncSessionLocal() as db:
            db.add(MigrationSafety(id=1,external_jobs_paused=True,source_cutoff='synthetic'))
            old=AutomationJob(job_type='scrape',status=AutomationJobStatus.queued,created_by_id=1,result={'managed_queue':True})
            new=AutomationJob(job_type='scrape',status=AutomationJobStatus.queued,created_by_id=1,result={'managed_queue':True,'public_discovery_v1':True,'query':'synthetic'})
            db.add_all([old,new]);await db.commit();ids=[old.id,new.id]
        for jid in ids:await orchestrator.run_job(jid,{})
        async with database.AsyncSessionLocal() as db:
            assert (await db.get(AutomationJob,ids[0])).status==AutomationJobStatus.paused
            new=await db.get(AutomationJob,ids[1]);assert new.status==AutomationJobStatus.completed
            assert new.result['grants_added']==1
            assert (await db.get(MigrationSafety,1)).external_jobs_paused
        assert len(calls)==1 and calls[0]['allow_browser'] is False
    asyncio.run(run())
