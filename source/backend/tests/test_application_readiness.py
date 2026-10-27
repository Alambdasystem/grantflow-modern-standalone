import asyncio
from datetime import timedelta
from test_ingestion import client, api, upload, drain, headers


def test_amount_change_invalidates_acceptance(api):
    assert api.patch('/api/applications/1',json={'proposal_text':'Reviewed proposal','amount_requested':100},headers=headers()).status_code==200
    assert api.post('/api/applications/1/reviews',json={'decision':'accepted','feedback':'Checked saved application'},headers=headers('admin')).status_code==201
    assert api.patch('/api/applications/1',json={'amount_requested':200},headers=headers()).status_code==200
    assert api.patch('/api/applications/1',json={'status':'submitted'},headers=headers()).status_code==409


def test_readiness_is_live_and_scoped(api):
    r=api.get('/api/applications/1/readiness',headers=headers())
    assert r.status_code==200,r.text
    assert not r.json()['ready'] and any(c['key']=='proposal' and not c['passed'] for c in r.json()['checks'])
    assert api.get('/api/applications/2/readiness',headers=headers()).status_code==404


def test_matching_and_dashboard_use_correct_dates(api):
    from db import database
    from models.models import IngestionDocument,Grant
    from services.document_ingestion import now
    item=upload(api);drain()
    async def setup():
        async with database.AsyncSessionLocal() as db:
            row=await db.get(IngestionDocument,item['id']);row.evidence_date=now().date()-timedelta(days=90);row.review_due=now().date()-timedelta(days=1)
            grant=await db.get(Grant,1);grant.deadline=now()+timedelta(days=2)
            await db.commit()
    asyncio.run(setup())
    status=api.get('/api/operations/knowledge-status',headers=headers()).json()
    assert status['sources'][0]['needs_review'] is True
    actions=api.get('/api/operations/next-actions',headers=headers()).json()
    assert actions[0]['due'] is not None


def test_ai_candidate_preserves_saved_text_and_carries_deletion_provenance(api,monkeypatch):
    from routers import ai_router
    from unittest.mock import AsyncMock
    document=upload(api);drain()
    assert api.patch('/api/applications/1',json={'proposal_text':'Human reviewed narrative'},headers=headers()).status_code==200
    monkeypatch.setattr(ai_router._ai,'generate',AsyncMock(return_value='New candidate based on source'))
    response=api.post('/api/ai/generate',json={'application_id':1,'task':'proposal','stream':False},headers=headers())
    assert response.status_code==200,response.text
    assert api.get('/api/applications/1',headers=headers()).json()['proposal_text']=='Human reviewed narrative'
    candidate=response.json()
    assert candidate['draft_id'] and not candidate['saved_to_application']
    assert api.patch('/api/applications/1',json={'proposal_text':candidate['result'],'source_draft_id':candidate['draft_id']},headers=headers()).status_code==200
    assert api.delete(f'/api/ingestion/documents/{document["id"]}',headers=headers('admin')).status_code==200
    assert 'Source document deleted' in api.get('/api/applications/1',headers=headers()).json()['proposal_text']


def test_stale_review_and_submission_patch_bypass_are_rejected(api):
    api.patch('/api/applications/1',json={'proposal_text':'Saved'},headers=headers())
    old=api.get('/api/applications/1/readiness',headers=headers()).json()['revision']
    api.patch('/api/applications/1',json={'form_data':{'answer':'changed'}},headers=headers())
    assert api.post('/api/applications/1/reviews',json={'decision':'accepted','feedback':'Review','revision':old},headers=headers('admin')).status_code==409
    assert api.post('/api/applications/1/reviews',json={'decision':'accepted','feedback':'Current review'},headers=headers('admin')).status_code==201
    assert api.patch('/api/applications/1',json={'status':'submitted','amount_requested':99},headers=headers()).status_code==409
    assert api.patch('/api/applications/1',json={'amount_requested':-1},headers=headers()).status_code==422
    assert api.patch('/api/applications/1',json={'amount_awarded':500},headers=headers()).status_code==403


def test_matching_excludes_overdue_evidence_and_checks_ceiling_compatibility():
    from routers.operations import alignment
    from models.models import Organization,Grant
    from types import SimpleNamespace
    org=Organization(name='Synthetic',mission='Science',categories=[])
    grant=Grant(id=1,title='Education',amount_max=100000)
    config=SimpleNamespace(kind='configuration',data={'funding_min':1000,'funding_max':5000})
    stale=SimpleNamespace(id=1,original_filename='old.txt',filename='old.txt',extracted_text='Education',ai_summary=None,ingestion_citation={'needs_review':True})
    score=alignment(org,grant,[config],[stale])
    assert next(f for f in score['factors'] if f['name']=='Knowledge evidence')['score']==0
    assert next(f for f in score['factors'] if f['name']=='Funding scale')['score']==15
    assert score['warnings']


def test_readiness_uses_saved_package_and_reviewed_checklist(api):
    from db import database
    from models.models import Grant
    async def package():
        async with database.AsyncSessionLocal() as db:
            g=await db.get(Grant,1)
            g.source_url='https://www.grants.gov/search-results-detail/999999'
            g.requirements_detail={'opp_id':'999999','required_forms':[{'name':'SF-424','is_mandatory':True}], 'required_attachments':None}
            await db.commit()
    asyncio.run(package())
    checks=api.get('/api/applications/1/readiness',headers=headers()).json()['checks']
    assert not next(c for c in checks if c['label']=='SF-424')['passed']
    audit={'kind':'audit','title':'Synthetic package verification','status':'accepted','application_id':1,
        'checklist':[{'label':'SF-424','done':True,'evidence':'Verified synthetic completed form','owner':'QA reviewer'}]}
    assert api.post('/api/operations/records',json=audit,headers=headers('admin')).status_code==201
    checks=api.get('/api/applications/1/readiness',headers=headers()).json()['checks']
    assert next(c for c in checks if c['label']=='SF-424')['passed']
    api.patch('/api/applications/1',json={'amount_requested':100,'form_data':{'grant_planning':{'summary':{'budget_total':150}}}},headers=headers())
    report=api.get('/api/applications/1/readiness',headers=headers()).json()
    assert any('cost sharing' in w for w in report['warnings'])
