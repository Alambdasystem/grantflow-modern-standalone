"""QA regressions using disposable records and synthetic provider responses only."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from test_ingestion import client, api, headers
from services.grant_integrity import requirement_error, deduplicate, catalog_state, opportunity_id
from services.draft_validation import draft_issues


def grant(**overrides):
    return SimpleNamespace(title='Synthetic County Youth Program', funding_agency='Synthetic County', source_url='https://county.example/grants/youth', deadline=None, requirements_detail={}, **overrides)


def test_mismatched_requirements_never_become_a_verified_package():
    g=grant()
    g.requirements_detail={'opp_id':'359120','agency':'Different country','required_forms':[{'name':'Wrong form','is_mandatory':True}]}
    assert requirement_error(g)
    g.source_url='https://www.grants.gov/search-results-detail/359121'
    assert requirement_error(g)
    g.source_url='https://www.grants.gov/search-results-detail/359120'
    assert requirement_error(g) is None
    assert opportunity_id('https://grants.gov.evil.example/results-detail/359120') is None


def test_nonfederal_source_never_uses_first_federal_search_result(monkeypatch):
    from automation.agents.grant_requirements import GrantRequirementsAgent
    agent=GrantRequirementsAgent()
    search=AsyncMock(); monkeypatch.setattr(agent,'_search_opp',search)
    result=asyncio.run(agent.fetch(source_url='https://county.example/youth',grant_title='County Youth'))
    assert not result['success'] and result['error']
    search.assert_not_called()


def test_duplicate_display_keeps_distinct_funding_rounds_and_missing_sources():
    a,b,c,d=grant(),grant(),grant(),grant()
    b.source_url+='?utm_source=search'
    c.source_url+='?round=2027'
    d.source_url=None
    assert deduplicate([a,b,c,d])==[a,c,d]


def test_historical_announcement_and_expired_deadline_are_explicit():
    g=grant();g.source_url='https://county.example/2023/grant-awardees-announced/'
    assert catalog_state(g)=='historical_announcement'
    g.deadline=datetime.now(timezone.utc)-timedelta(days=1)
    assert catalog_state(g)=='expired'


@pytest.mark.parametrize('text,amount',[
    ('- Staff: $12,000\n- Supplies: $14,000\nTotal budget: $20,000',100),
    ('Requested amount: $20,000',100),
    ('- Staff: $50.25\n- Supplies: $49.75\nTotal: $99.99',100),
    ('We achieved a 90% improvement in student outcomes.',100),
])
def test_invalid_ai_draft_is_rejected(text,amount):
    assert draft_issues(text,{'application':{'amount_requested':amount}},'proposal')


def test_exact_decimal_budget_and_explicit_targets_are_allowed():
    text='- Staff: $50.25\n- Supplies: $49.75\nTotal budget: $100.00\nProposed target: 20% improvement; confirm feasibility.'
    assert not draft_issues(text,{'application':{'amount_requested':100}},'budget')
    assert not draft_issues('We achieved 90% student participation [Annual Report v1].',{'knowledge_documents':[{'title':'Annual Report v1','excerpt':'90% student participation'}]},'proposal')


def test_invalid_stream_never_exposes_partial_candidate(monkeypatch):
    from services.ai_service import AIService,AIUnavailable
    async def run():
        service=AIService()
        async def chunks(*args):
            yield '- Staff: $12,000\n- Supplies: $14,000\n'
            yield 'Total budget: $20,000'
        monkeypatch.setattr(service,'_stream_generate',chunks)
        exposed=[]
        try:
            with pytest.raises(AIUnavailable):
                async for chunk in service.stream_generate('proposal',{'application':{'amount_requested':100}}):exposed.append(chunk)
            assert not exposed
        finally:await service._client.aclose()
    asyncio.run(run())


def test_cache_readiness_and_all_score_routes_agree(api):
    from routers import grants
    from db import database
    from models.models import Grant
    api.app.include_router(grants.router)
    async def setup():
        async with database.AsyncSessionLocal() as db:
            g=await db.get(Grant,1)
            g.requirements=['Wrong imported package']
            g.source_url='https://county.example/youth'
            g.requirements_detail={'opp_id':'999999','required_forms':[{'name':'Unrelated form','is_mandatory':True}]}
            db.add(Grant(title=g.title,funding_agency='County',source_url=g.source_url))
            await db.commit()
    asyncio.run(setup())
    req=api.get('/api/grants/1/requirements',headers=headers()).json()
    assert req['status']=='error' and req['requirements']=={} and req['error']
    workspace=api.get('/api/grants/1/workspace',headers=headers()).json()
    assert not workspace['requirements'] and workspace['requirements_warning']
    ready=api.get('/api/applications/1/readiness',headers=headers()).json()
    assert not next(c for c in ready['checks'] if c['key']=='requirements_known')['passed']
    scores=[api.get('/api/grants/',headers=headers()).json()[0]['ai_match_score'],api.post('/api/grants/search',json={},headers=headers()).json()[0]['ai_match_score'],api.get('/api/grants/1',headers=headers()).json()['ai_match_score'],workspace['alignment']['score']]
    assert len(set(scores))==1


def test_generated_candidate_cannot_ignore_saved_amount(api,monkeypatch):
    from routers import ai_router
    api.patch('/api/applications/1',json={'amount_requested':100,'proposal_text':'Human draft'},headers=headers())
    monkeypatch.setattr(ai_router._ai,'generate',AsyncMock(return_value='Requested amount: $20,000'))
    r=api.post('/api/ai/generate',json={'application_id':1,'task':'proposal','stream':False},headers=headers())
    assert r.status_code==503 and 'withheld' in r.json()['detail']
    assert api.get('/api/applications/1',headers=headers()).json()['proposal_text']=='Human draft'


def test_profile_complete_is_computed_not_trusted_from_legacy_flag(api):
    from db import database
    from models.models import Organization
    async def setup():
        async with database.AsyncSessionLocal() as db:
            row=await db.get(Organization,1);row.profile_complete=True;await db.commit()
    asyncio.run(setup())
    assert not api.get('/api/organizations/me',headers=headers()).json()['profile_complete']


def test_explicit_qa_drafts_excluded_from_metrics_not_deleted(api):
    from routers import analytics
    api.app.include_router(analytics.router)
    before=api.get('/api/analytics/dashboard',headers=headers()).json()['total_applications']
    created=api.post('/api/applications/',json={'grant_id':1,'title':'QA TEST - disposable - DO NOT SUBMIT'},headers=headers()).json()
    assert api.get('/api/analytics/dashboard',headers=headers()).json()['total_applications']==before
    assert api.get('/api/applications/'+str(created['id']),headers=headers()).status_code==200
