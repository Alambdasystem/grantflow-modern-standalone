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
