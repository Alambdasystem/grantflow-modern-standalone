"""Six original regression intents against disposable data and current auth.

No hardcoded live port, real credentials, fixed customer IDs, or provider calls.
Generated text is a reviewable candidate; it must not overwrite human content.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock
import pytest
from test_integration_audit import client,template_db,headers,ok,create_application


def change_grant(**changes):
    from db.database import AsyncSessionLocal
    from models.models import Grant
    async def run():
        async with AsyncSessionLocal() as db:
            row=await db.get(Grant,1)
            for key,value in changes.items():setattr(row,key,value)
            await db.commit()
    asyncio.run(run())


class TestBudgetCandidate:
    def test_budget_generate_returns_200(self,client,monkeypatch):
        from routers.ai_router import _ai
        monkeypatch.setattr(_ai,'generate',AsyncMock(return_value='Synthetic reviewed budget narrative with evidence still needed.'))
        app=create_application(client)
        response=ok(client.post('/api/ai/generate',json={'task':'budget','application_id':app['id'],'stream':False},headers=headers()))
        assert response['success'] and response['task']=='budget' and response['draft_id']

    def test_budget_candidate_never_overwrites_human_text(self,client,monkeypatch):
        from routers.ai_router import _ai
        monkeypatch.setattr(_ai,'generate',AsyncMock(return_value='Synthetic reviewed budget narrative with evidence still needed.'))
        app=create_application(client);path='/api/applications/'+str(app['id'])
        ok(client.patch(path,json={'budget_narrative':'Human-authored budget'},headers=headers()))
        result=ok(client.post('/api/ai/generate',json={'task':'budget','application_id':app['id'],'stream':False},headers=headers()))
        assert ok(client.get(path,headers=headers()))['budget_narrative']=='Human-authored budget'
        rows=ok(client.get('/api/operations/records?kind=draft',headers=headers()))
        assert next(r for r in rows if r['id']==result['draft_id'])['body']==result['result']


class TestOrganizationEndpoints:
    @pytest.mark.parametrize('path',['/api/organizations/me','/api/organizations/','/api/organizations/1'])
    def test_reads(self,client,path):
        value=ok(client.get(path,headers=headers()))
        assert value and (isinstance(value,list) or value['id']==1)

    def test_invalid_id_returns_404(self,client):
        ok(client.get('/api/organizations/99999',headers=headers()),404)


class TestBulkLinkOrg:
    def test_bulk_link_returns_200(self,client):
        app=create_application(client)
        linked=ok(client.post('/api/applications/bulk-link-org',json={'org_id':2,'application_ids':[app['id']]},headers=headers()))
        assert linked['updated']==1
        ok(client.post('/api/applications/bulk-link-org',json={'org_id':2,'application_ids':[app['id']]},headers=headers('grant_writer')),403)

    def test_bulk_link_preserves_applicant(self,client):
        app=create_application(client)
        ok(client.post('/api/applications/bulk-link-org',json={'org_id':2,'application_ids':[app['id']]},headers=headers()))
        saved=ok(client.get('/api/applications/'+str(app['id']),headers=headers()))
        assert saved['organization_id']==2 and saved['applicant_id']==app['applicant_id']


class TestEncodingFix:
    def test_fix_encoding_returns_200(self,client):
        assert 'fixed' in ok(client.post('/api/admin/fix-encoding',headers=headers()))

    def test_corrupt_title_is_repaired(self,client):
        change_grant(title='Synthetic \ufffd Grant')
        ok(client.post('/api/admin/fix-encoding',headers=headers()))
        assert '\ufffd' not in ok(client.get('/api/grants/1',headers=headers()))['title']


class TestArchiveExpired:
    def test_archive_expired_returns_200(self,client):
        assert 'archived' in ok(client.post('/api/admin/archive-expired-grants',headers=headers()))

    def test_past_deadline_is_removed_from_active_list(self,client):
        change_grant(deadline=datetime(2001,1,1))
        ok(client.post('/api/admin/archive-expired-grants',headers=headers()))
        assert not ok(client.get('/api/grants/?status=active',headers=headers()))
        assert ok(client.get('/api/grants/1',headers=headers()))['status']=='archived'


class TestBatchRequirements:
    def test_scan_all_requirements_returns_200(self,client):
        change_grant(source_url='https://www.grants.gov/search-results-detail/999998')
        data=ok(client.post('/api/grants/scan-all-requirements',headers=headers()))
        assert data['queued']==1 and data['grant_ids']==[1]

    def test_repeated_batch_scan_does_not_duplicate_queued_work(self,client):
        change_grant(source_url='https://www.grants.gov/search-results-detail/999998')
        assert ok(client.post('/api/grants/scan-all-requirements',headers=headers()))['queued']==1
        assert ok(client.post('/api/grants/scan-all-requirements',headers=headers()))['queued']==0


class TestPureHelpers:
    def test_encoding_replacement(self):
        """Unicode replacement char (U+FFFD) used as separator should become em-dash."""
        from routers.admin import _fix_title_encoding
        assert _fix_title_encoding("WYF Summer 2025 � County") == "WYF Summer 2025 — County"

    def test_encoding_already_clean(self):
        from routers.admin import _fix_title_encoding
        title = "Youth Grant — Summer 2025"
        assert _fix_title_encoding(title) == title

    def test_encoding_multiple_replacements(self):
        from routers.admin import _fix_title_encoding
        assert _fix_title_encoding("App � Grant � Renewal") == "App — Grant — Renewal"
