"""Source/candidate/renewal regressions. All records and identities are synthetic."""
import asyncio
from types import SimpleNamespace
from datetime import datetime,timedelta
import pytest
from test_integration_audit import client,template_db,headers,ok,create_application
from services.grant_integrity import source_fingerprint,source_review,safe_requirements
from services.draft_validation import draft_issues


def test_total_requested_is_both_total_and_request():
    issues=draft_issues('- Staff: $8,000\n- Supplies: $18,000\nTotal Requested: $20,000',{'application':{'amount_requested':100}},'proposal')
    assert any('26,000' in x for x in issues) and any('100.00' in x for x in issues)


@pytest.mark.parametrize('corrected', [True,False])
def test_ai_correction_is_bounded_and_never_accepts_invalid_retry(monkeypatch,corrected):
    from services.ai_service import AIService,AIUnavailable
    async def run():
        service=AIService();calls=[]
        async def response(task,context,*args):
            calls.append(context)
            if corrected and len(calls)==2:return 'Total Requested: $100.00\n[information needed] Verified costs and outcome evidence.'
            return 'Total Requested: $200.00'
        monkeypatch.setattr(service,'_generate',response)
        try:
            if corrected:assert '$100.00' in await service.generate('budget',{'application':{'amount_requested':100}})
            else:
                with pytest.raises(AIUnavailable):await service.generate('budget',{'application':{'amount_requested':100}})
            assert len(calls)==2 and 'CORRECTION REQUIRED' in calls[-1]['prompt']
        finally:await service._client.aclose()
    asyncio.run(run())


def test_source_review_is_bound_to_exact_source_and_six_fields():
    g=SimpleNamespace(title='Synthetic source',funding_agency='Synthetic agency',source_url='https://agency.example/round-1',meta={},requirements_detail={'opp_id':'wrong'})
    review={'status':'verified','fingerprint':source_fingerprint(g),'fields':dict.fromkeys(['identifier','funder','title','eligibility','deadline','application_url'],'synthetic'),'evidence':[{'url':g.source_url}],'requirements':{'opp_id':'exact'}}
    g.meta={'source_review':review};assert safe_requirements(g)['opp_id']=='exact'
    g.source_url+='changed';assert source_review(g)['status']=='needs_source_verification' and safe_requirements(g)=={}
    g.source_url=g.source_url[:-7];review['fields'].pop('eligibility');assert source_review(g)['status']=='needs_source_verification'


@pytest.mark.parametrize('category',['proposal','budget','arbitrary-label'])
def test_candidate_save_cannot_bypass_validation_with_category(client,category):
    app=create_application(client)
    body={'kind':'draft','title':'Synthetic invalid candidate','category':category,'application_id':app['id'],'body':'- Staff: $1\n- Supplies: $2\nTotal Requested: $100'}
    ok(client.post('/api/operations/records',json=body,headers=headers()),422)
    assert ok(client.get('/api/operations/records?kind=draft',headers=headers()))==[]


def test_application_create_and_patch_reject_bad_figures_and_preserve_saved_text(client):
    invalid='- Staff: $1\n- Supplies: $2\nTotal: $100'
    ok(client.post('/api/applications/',json={'grant_id':1,'amount_requested':100,'proposal_text':invalid},headers=headers()),422)
    app=create_application(client);path=f"/api/applications/{app['id']}"
    ok(client.patch(path,json={'proposal_text':'Human text retained','amount_requested':100},headers=headers()))
    ok(client.patch(path,json={'budget_narrative':invalid},headers=headers()),422)
    assert ok(client.get(path,headers=headers()))['proposal_text']=='Human text retained'


def test_unverified_candidate_can_be_drafted_but_not_accepted(client):
    app=create_application(client);body={'kind':'draft','title':'Synthetic sourced review','application_id':app['id'],'body':'[information needed] Verify funder requirements.'}
    draft=ok(client.post('/api/operations/records',json=body,headers=headers()),201)
    assert draft['data']['quality_review']['warnings']
    ok(client.put('/api/operations/records/'+str(draft['id']),json={**body,'revision':draft['revision'],'status':'accepted'},headers=headers()),422)
    assert ok(client.get('/api/operations/records?kind=draft',headers=headers()))[0]['body']==body['body']


def test_verified_source_is_not_a_complete_package_and_audit_warnings_survive_reads(client):
    from db import database
    from models.models import Grant,OrganizationRecord
    app=create_application(client)
    async def seed():
        async with database.AsyncSessionLocal()as db:
            grant=await db.get(Grant,1)
            grant.meta={'source_review':{'status':'verified','fingerprint':source_fingerprint(grant),'fields':dict.fromkeys(['identifier','funder','title','eligibility','deadline','application_url'],'synthetic'),'evidence':[{'url':'https://agency.example'}],'requirements':{'package_complete':False}}}
            db.add(OrganizationRecord(organization_id=1,created_by_id=1,kind='draft',title='Synthetic audited candidate',body='[information needed] Confirm eligibility.',revision=1,history=[],data={'application_id':app['id'],'quality_review':{'reviewed_at':'2026-10-27','warnings':['Bank eligibility evidence is missing.']}}))
            await db.commit()
    asyncio.run(seed())
    row=ok(client.get('/api/operations/records?kind=draft',headers=headers()))[0]
    assert 'Bank eligibility evidence is missing.' in row['data']['quality_review']['warnings']
    assert any('Requirements review incomplete' in x for x in row['data']['quality_review']['warnings'])
    ok(client.put('/api/operations/records/'+str(row['id']),json={'kind':'draft','title':row['title'],'body':row['body'],'application_id':app['id'],'revision':1,'status':'accepted'},headers=headers()),422)


def test_internal_renewal_schedule_create_deduplicate_review_complete(client):
    parent=create_application(client);pid=parent['id'];path='/api/applications/'+str(pid)
    due=(datetime.now()-timedelta(days=2)).isoformat()
    ok(client.patch(path,json={'status':'approved','renewal_due_date':due},headers=headers()))
    assert any(a['id']==pid for a in ok(client.get('/api/renewals/due',headers=headers())))
    child=ok(client.post(f'/api/renewals/{pid}/draft',headers=headers('grant_writer')))
    assert ok(client.post(f'/api/renewals/{pid}/draft',headers=headers()))['id']==child['id']
    assert not ok(client.get('/api/automation/jobs',headers=headers()))
    ok(client.post(f'/api/renewals/{pid}/draft',headers=headers('viewer')),403)
    ok(client.post(f'/api/renewals/{pid}/complete',headers=headers('grant_writer')),403)
    ok(client.post(f'/api/renewals/{pid}/complete',headers=headers()),409)
    cpath='/api/applications/'+str(child['id'])
    ok(client.patch(cpath,json={'proposal_text':'Human reviewed synthetic renewal preparation'},headers=headers()))
    ok(client.post(cpath+'/reviews',json={'decision':'accepted','feedback':'Synthetic internal review only'},headers=headers()),201)
    assert ok(client.post(f'/api/renewals/{pid}/complete',headers=headers()))['completed']
    saved=ok(client.get(path,headers=headers()));assert saved['renewal_due_date'] is None
    assert saved['status']=='approved' and saved['form_data']['renewal_preparation']['draft_id']==child['id']


def test_repair_manifest_has_24_explainable_public_source_reviews():
    import json
    from pathlib import Path
    # Mounted in full regression runner; source review shape is also checked above.
    path=Path('/reviews/2026-10-27.json')
    if not path.exists():
        path=Path(__file__).resolve().parents[3]/'docs/source-reviews/2026-10-27.json'
    rows=json.loads(path.read_text())
    assert len(rows)==24 and len({r['grant_id']for r in rows})==24
    assert sum(r['status']=='verified'for r in rows)==19
    assert all(r['reason'] and r['retrieved_at'] and r['source_url'] for r in rows)
    assert all(r['requirements']['package_complete'] is False for r in rows if r['status']=='verified')


@pytest.mark.parametrize('attempts',[1,3])
def test_restart_recovers_local_ingestion_under_external_hold_without_unpausing_external_jobs(client,monkeypatch,attempts):
    from db import database
    from models.models import IngestionDocument,AutomationJob,AutomationJobStatus
    from models.auth_models import MigrationSafety
    from services import job_queue
    from sqlalchemy import select
    monkeypatch.setattr(job_queue,'AsyncSessionLocal',database.AsyncSessionLocal)
    item=ok(client.post('/api/ingestion/upload',files={'file':('synthetic-restart.txt',b'Synthetic restart evidence')},headers=headers()),202)
    async def run():
        async with database.AsyncSessionLocal()as db:
            doc=await db.get(IngestionDocument,item['id']);doc.status='processing';doc.attempts=attempts
            job=(await db.execute(select(AutomationJob).where(AutomationJob.job_type=='ingest'))).scalars().one();jid=job.id;job.status=AutomationJobStatus.running
            db.add(MigrationSafety(id=1,external_jobs_paused=True,source_cutoff='synthetic'))
            external=AutomationJob(created_by_id=1,job_type='renew',status=AutomationJobStatus.paused,result={'managed_queue':True},error_message='Manual external pause')
            db.add(external);await db.commit();eid=external.id
        await job_queue.recover();await job_queue.recover()
        async with database.AsyncSessionLocal()as db:
            doc=await db.get(IngestionDocument,item['id']);job=await db.get(AutomationJob,jid)
            assert doc.status==('queued'if attempts<3 else'failed')
            assert job.status==(AutomationJobStatus.queued if attempts<3 else AutomationJobStatus.failed)
            assert (await db.get(AutomationJob,eid)).status==AutomationJobStatus.paused
            assert (await db.get(MigrationSafety,1)).external_jobs_paused
    asyncio.run(run())


def test_local_failed_retry_under_hold_does_not_poll_external_sources_or_duplicate_jobs(client,monkeypatch):
    from db import database
    from models.models import IngestionDocument,AutomationJob,AutomationJobStatus
    from models.auth_models import MigrationSafety
    from services import job_queue,document_ingestion
    from sqlalchemy import select
    monkeypatch.setattr(job_queue,'AsyncSessionLocal',database.AsyncSessionLocal)
    async def prohibited():raise AssertionError('External source polling is held')
    monkeypatch.setattr(document_ingestion,'schedule',prohibited)
    item=ok(client.post('/api/ingestion/upload',files={'file':('synthetic-retry.txt',b'Synthetic retained evidence')},headers=headers()),202)
    async def run():
        async with database.AsyncSessionLocal()as db:
            doc=await db.get(IngestionDocument,item['id']);doc.status='failed';doc.attempts=1;doc.retry_at=datetime.now()-timedelta(seconds=1)
            job=(await db.execute(select(AutomationJob))).scalars().one();job.status=AutomationJobStatus.failed
            db.add(MigrationSafety(id=1,external_jobs_paused=True,source_cutoff='synthetic'));await db.commit()
        await job_queue.scheduled_documents();await job_queue.scheduled_documents()
        async with database.AsyncSessionLocal()as db:
            jobs=(await db.execute(select(AutomationJob).where(AutomationJob.status==AutomationJobStatus.queued))).scalars().all()
            assert len(jobs)==1 and jobs[0].job_type=='ingest'
    asyncio.run(run())


@pytest.mark.parametrize('budget',[512,1024,2048])
def test_small_full_app_budget_refuses_ocr_before_loading_native_model(monkeypatch,budget):
    from services.document_extract import extract,require_ocr_capacity
    monkeypatch.setenv('GFM_EXTRACTION_MEMORY_LIMIT_MB',str(budget))
    if budget<2048:
        with pytest.raises(ValueError,match='OCR requires at least 2048 MB'):
            extract(b'synthetic input','synthetic.png')
    else:assert require_ocr_capacity()is None
    assert extract(b'Synthetic plain text','synthetic.txt')['text']


def test_extractor_environment_caps_threads_and_omits_service_credentials(monkeypatch):
    from services.document_ingestion import extraction_env
    monkeypatch.setenv('OPENBLAS_NUM_THREADS','128');monkeypatch.setenv('ALAMBDA_API_TOKEN','synthetic-secret-not-for-extractors')
    env=extraction_env()
    assert all(env[k]=='1'for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'))
    assert 'ALAMBDA_API_TOKEN'not in env and int(env['GFM_EXTRACTION_MEMORY_LIMIT_MB'])>=0
