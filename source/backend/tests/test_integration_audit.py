"""Isolated GFM API audit. No production DB, startup seeds, or external traffic.

Run explicitly: python -m pytest tests/test_integration_audit.py -v
Failures are findings; do not weaken assertions to make the audit green.
"""
import asyncio
import os
import re
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SANDBOX = tempfile.TemporaryDirectory(prefix="gfm-audit-")
os.environ.update(DEBUG="false", DATABASE_URL="sqlite+aiosqlite:///" + Path(SANDBOX.name, "unused.db").as_posix(),
                  SECRET_KEY="isolated-audit-key-not-for-production",
                  UPLOAD_DIR=str(Path(SANDBOX.name, "uploads")),
                  SCREENSHOT_DIR=str(Path(SANDBOX.name, "screenshots")))

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from main import app
from db.database import Base, get_db
from models.models import Organization, User, UserRole, Grant, GrantStatus
from auth.jwt_handler import hash_password, create_access_token, verify_password
from models.auth_models import MigrationSafety  # Register before every disposable schema.
from config import settings

PASSWORD = "Isolated-test-only-2026!"
HASH = hash_password(PASSWORD)


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("gfm-template")
    engine = create_async_engine("sqlite+aiosqlite:///" + (tmp_path / "audit.db").as_posix())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Organization(id=1, name="Audit WYF", mission="youth education"),
                        Organization(id=2, name="Other organization")])
            await db.flush()
            for i, role in enumerate(UserRole, 1):
                db.add(User(id=i, identity_id='synthetic-'+role.value, username=role.value, email=role.value+"@example.com",
                            hashed_password=HASH, role=role, organization_id=1,
                            is_active=True, is_approved=True))
            db.add(Grant(id=1, title="Audit youth education grant", amount=1000,
                         status=GrantStatus.active, category="education", deadline=datetime(2099, 12, 31)))
            await db.commit()
    asyncio.run(prepare())
    asyncio.run(engine.dispose())
    return tmp_path / "audit.db"


@pytest.fixture
def client(tmp_path, monkeypatch, template_db):
    shutil.copyfile(template_db, tmp_path / "audit.db")
    engine = create_async_engine("sqlite+aiosqlite:///" + (tmp_path / "audit.db").as_posix())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def override():
        async with factory() as session:
            yield session
            await session.commit()  # Match get_db's transaction lifecycle, including flush-only routers.
    from db import database
    from db.database import get_public_db
    from auth import jwt_handler
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'AsyncSessionLocal',factory)
    monkeypatch.setattr(settings,'AUTH_MODE','anthesis')
    monkeypatch.setattr(settings,'AUTOMATION_WORKER_ENABLED',False)  # No lifespan/dispatcher in this API fixture.
    async def central_identity(token):
        # The local signature is a fixture transport only, never a production login.
        try:data=jwt_handler.decode_token(token)
        except Exception:
            from fastapi import HTTPException
            raise HTTPException(401,'Synthetic identity rejected the token')
        role=data['role']
        return {'identity_id':'synthetic-'+role,'username':data['username'],'role':role,
                'local_user_id':data['user_id'],'grantflow_access':['read'] if role=='viewer' else ['read','write']}
    monkeypatch.setattr(jwt_handler,'validate_anthesis_identity',central_identity)
    app.dependency_overrides[get_public_db]=override
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    def blocked(*args, **kwargs):
        raise AssertionError("External network is prohibited in isolated audit")
    import httpx
    import requests
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    # Background agents are a separate integration boundary, never run against real portals.
    from starlette.background import BackgroundTasks
    monkeypatch.setattr(BackgroundTasks, "__call__", AsyncMock())
    c = TestClient(app, raise_server_exceptions=False)  # Deliberately do not run lifespan seeds.
    yield c
    c.close()
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def headers(role="admin"):
    token = create_access_token({"sub": role, "username": role, "role": role,
                                 "user_id": list(UserRole).index(UserRole(role)) + 1})
    return {"Authorization": "Bearer " + token}


def ok(response, status=200):
    assert response.status_code == status, response.text[:400]
    return response.json() if response.content else None


PROTECTED = [(method, route.path) for route in app.routes
             if route.path.startswith("/api/") and not route.path.startswith(("/api/give", "/api/auth/login", "/api/docs", "/api/redoc", "/api/openapi"))
             for method in sorted(route.methods or [])]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_private_route_requires_auth(client, method, path):
    path = re.sub(r"\{[^}]+\}", "99999", path)
    response = client.request(method, path, json={})
    if path in ('/api/auth/setup','/api/auth/accept'):
        # Valid payload reaches the central-mode gate rather than schema validation.
        body={'username':'synthetic_user','password':PASSWORD,'email':'synthetic@example.com','organization':'Synthetic','bootstrap_token':'x'*40,'token':'x'*40}
        response=client.request(method,path,json=body)
    if path=='/api/auth/status':
        assert response.status_code==200 and response.json()['mode']=='anthesis'
        return
    if path.startswith(('/api/auth/setup','/api/auth/refresh','/api/auth/invitations','/api/auth/accept','/api/auth/accounts/')):
        assert response.status_code==404  # Standalone routes are disabled in central mode.
        return
    assert response.status_code in (401, 403), f"{method} {path}: {response.status_code}"


@pytest.mark.parametrize("path", ["/health", "/api/auth/me", "/api/users/", "/api/grants/",
    "/api/grants/1", "/api/grants/categories/list", "/api/grants/1/requirements",
    "/api/applications/", "/api/organizations/", "/api/organizations/me", "/api/organizations/1",
    "/api/renewals/due", "/api/analytics/dashboard", "/api/analytics/grant-pipeline",
    "/api/automation/jobs", "/api/providers", "/api/foundations", "/api/donors", "/api/donors/campaigns/list"])
def test_feature_read_contracts(client, path):
    ok(client.get(path, headers=headers()))


@pytest.mark.parametrize("path", ["/api/grants/99999", "/api/applications/99999",
    "/api/organizations/99999", "/api/automation/jobs/99999", "/api/foundations/99999",
    "/api/donors/99999", "/api/give/nonexistent", "/api/grant-planning?grant_id=99999",
    "/api/workspace/grants-gov/sync/99999"])
def test_missing_records(client, path):
    ok(client.get(path, headers=headers()), 404)


@pytest.mark.parametrize("role", [r.value for r in UserRole])
def test_login_and_identity(client, role):
    ok(client.post('/api/auth/login',json={'username':role,'password':PASSWORD}),410)
    user=ok(client.get('/api/auth/me',headers=headers(role)))
    assert user['username']==role and user['role']==role
    ok(client.get('/api/auth/me',headers={'Authorization':'Bearer invalid'}),401)


def test_invalid_credentials(client):
    ok(client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}), 410)
    ok(client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"}), 401)


@pytest.mark.parametrize("path", ["/api/admin/fix-encoding", "/api/admin/archive-expired-grants"])
def test_admin_gates(client, path):
    ok(client.post(path, headers=headers("grant_writer")), 403)
    ok(client.post(path, headers=headers()))


def create_application(client, role="admin"):
    return ok(client.post("/api/applications/", json={"grant_id": 1, "title": "Audit draft"}, headers=headers(role)), 201)


def test_application_workflow_and_documents(client):
    item = create_application(client)
    path = f"/api/applications/{item['id']}"
    assert item["organization_id"] == 1 and item["status"] == "draft"
    assert ok(client.patch(path, json={"notes": "Audit note"}, headers=headers()))["notes"] == "Audit note"
    stages = ok(client.get(path + "/workflow", headers=headers()))
    assert len(stages) == 7
    assert ok(client.post(path + "/workflow/advance", headers=headers()))[0]["status"] == "active"
    assert ok(client.post(path + "/workflow/advance", headers=headers()))[0]["status"] == "completed"
    ok(client.patch(path + f"/workflow/{stages[0]['id']}", json={"status": "invalid"}, headers=headers()), 422)
    upload = ok(client.post(path + "/documents", files={"file": ("audit.txt", b"Youth education audit", "text/plain")}, headers=headers()))
    assert upload['id'] and upload['status']=='queued' and upload['application_id']==item['id']
    assert len(ok(client.get(path + "/documents", headers=headers()))) == 1


def test_viewer_cannot_create_application(client):
    ok(client.post("/api/applications/", json={"grant_id": 1}, headers=headers("viewer")), 403)


def test_document_upload_rejects_missing_application(client):
    ok(client.post("/api/applications/99999/documents", files={"file": ("audit.txt", b"audit", "text/plain")}, headers=headers()), 404)


def test_search_and_planning_promotion(client):
    found = ok(client.post("/api/grants/search", json={"query": "youth"}, headers=headers()))
    assert any(x["id"] == 1 for x in found)
    body = {"grant_id": 1}
    profile = ok(client.post("/api/grant-planning", json=body, headers=headers()))
    assert profile["grant_id"] == 1
    promoted = ok(client.post("/api/grant-planning/promote", json=body, headers=headers()))
    assert promoted["application"]["status"] == "draft"


@pytest.mark.parametrize("task", ["proposal", "budget", "executive_summary", "compliance"])
def test_ai_generation_contract_and_persistence(client, monkeypatch, task):
    from routers.ai_router import _ai
    monkeypatch.setattr(_ai, "generate", AsyncMock(return_value="Synthetic audit narrative"))
    item = create_application(client)
    data = ok(client.post("/api/ai/generate", json={"task": task, "application_id": item["id"], "stream": False}, headers=headers()))
    assert data["result"] == "Synthetic audit narrative"
    if task in ("proposal", "budget"):
        saved = ok(client.get(f"/api/applications/{item['id']}", headers=headers()))
        assert saved['proposal_text' if task=='proposal' else 'budget_narrative'] is None
        assert data['saved_to_application'] is False and data['draft_id']
        candidate=ok(client.get('/api/operations/records?kind=draft',headers=headers()))
        assert next(r for r in candidate if r['id']==data['draft_id'])['body']==data['result']


def test_ai_chat(client, monkeypatch):
    from routers.ai_router import _ai
    monkeypatch.setattr(_ai, "chat", AsyncMock(return_value="Synthetic grounded reply"))
    data = ok(client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Our mission?"}], "stream": False}, headers=headers()))
    assert data["reply"] == "Synthetic grounded reply"


def test_ai_matching_signature(client, monkeypatch):
    from routers.ai_router import _ai
    async def generate(task, context, model=None, payload=None):
        return "[]"
    monkeypatch.setattr(_ai, "generate", generate)
    ok(client.post("/api/ai/match-grants", headers=headers()))


def test_jobs_renewal_and_workspace_precondition(client):
    item = create_application(client)
    ok(client.post('/api/automation/jobs',json={'job_type':'monitor','application_id':item['id']},headers=headers()),422)
    job = ok(client.post("/api/automation/jobs", json={"job_type": "renew", "application_id": item["id"]}, headers=headers()), 201)
    assert ok(client.get(f"/api/automation/jobs/{job['id']}", headers=headers()))["status"] == "queued"
    renewal = ok(client.post(f"/api/renewals/{item['id']}/auto-renew", headers=headers()), 202)
    assert renewal["job_id"]
    ok(client.post("/api/workspace/grants-gov/sync", headers=headers()), 422)


def test_provider_credential_lifecycle(client):
    saved = ok(client.put("/api/providers/grants_gov", json={"username": "audit", "password": "synthetic-secret"}, headers=headers()))
    assert "synthetic-secret" not in str(saved)
    assert saved["has_credentials"]
    response = client.delete("/api/providers/grants_gov", headers=headers())
    assert response.status_code in (200, 204)


def test_foundation_lifecycle(client):
    item = ok(client.post("/api/foundations", json={"name": "Audit foundation"}, headers=headers()), 201)
    path = f"/api/foundations/{item['id']}"
    assert ok(client.get(path, headers=headers()))["name"] == "Audit foundation"
    ok(client.patch(path, json={"notes": "Audited"}, headers=headers()))
    contact = ok(client.post(path + "/contacts", json={"name": "Audit contact"}, headers=headers()), 201)
    ok(client.delete(path + f"/contacts/{contact['id']}", headers=headers()), 204)
    ok(client.delete(path, headers=headers()), 204)


def test_donor_campaign_and_public_giving(client):
    donor = ok(client.post("/api/donors", json={"first_name": "Audit", "email": "audit@example.com"}, headers=headers()), 201)
    campaign = ok(client.post("/api/donors/campaigns", json={"name": "Audit campaign", "goal_amount": 1000}, headers=headers()), 201)
    slug = campaign["slug"]
    ok(client.get("/api/give/" + slug))
    donation = ok(client.post("/api/donors/donations", json={"donor_id": donor["id"], "campaign_id": campaign["id"], "amount": 25}, headers=headers()), 201)
    assert donation["amount"] == 25
    saved = ok(client.get(f"/api/donors/campaigns/{campaign['id']}", headers=headers()))
    assert saved["raised_amount"] == 25


def test_negative_donation_rejected(client):
    ok(client.post("/api/donors/donations", json={"amount": -10}, headers=headers()), 422)


def test_password_hash_roundtrip():
    assert verify_password(PASSWORD, HASH)
    assert not verify_password("wrong", HASH)


@pytest.mark.parametrize("lines,expected", [([], 0), ([{"quantity": 3, "unit_cost": 2.5}], 7.5), ([{"quantity": None}], 0)])
def test_budget_math(lines, expected):
    from routers.grant_planning import _budget_total
    assert _budget_total(lines) == expected


@pytest.mark.parametrize("name,expected", [("Youth & STEAM 2027", "youth-steam-2027"), ("  Summer  ", "summer")])
def test_campaign_slug(name, expected):
    from routers.donors import _slug_from_name
    assert _slug_from_name(name) == expected


def test_discovery_deduplicates_and_enrichment_persists(client, monkeypatch):
    from routers.grants import GrantScraperAgent
    from routers import grant_enrichment
    rows = [{"title": "New audit opportunity", "funding_agency": "Audit agency",
             "source_url": "https://example.com/audit", "description": "Mentoring", "amount": 2000}]
    monkeypatch.setattr(GrantScraperAgent, "scrape", AsyncMock(return_value=rows))
    body = {"query": "mentoring", "max_results": 2}
    first = ok(client.post("/api/grants/discover", json=body, headers=headers()))
    assert first["imported"] == 1
    again = ok(client.post("/api/grants/discover", json=body, headers=headers()))
    assert again["imported"] == 0 and again["updated"] == 1
    monkeypatch.setattr(grant_enrichment, "_enrich_generic_url", AsyncMock(return_value={"required_documents": ["Audit letter"]}))
    grant_id = first["grants"][0]["id"]
    enriched = ok(client.post(f"/api/grants/{grant_id}/enrich", headers=headers()))
    assert "Audit letter" in enriched["requirements"]
    rejected=ok(client.post(f"/api/grants/{grant_id}/requirements", headers=headers()),422)
    assert 'exact Grants.gov opportunity ID' in rejected['detail']
    ok(client.post("/api/grants/scan-all-requirements", headers=headers()))


def test_organization_update_and_user_creation(client, monkeypatch):
    import startup_seed
    monkeypatch.setattr(startup_seed, "after_user_registration", AsyncMock())
    data = ok(client.patch("/api/organizations/me", json={"name": "Audit WYF", "mission": "Literacy"}, headers=headers()))
    assert data["mission"] == "Literacy"
    body = {"username": "new-auditor", "email": "new@example.com", "password": PASSWORD, "role": "reviewer"}
    ok(client.post("/api/users/", json=body, headers=headers("viewer")), 403)
    ok(client.post("/api/users/", json=body, headers=headers()), 410)
    assert all(u['username']!='new-auditor' for u in ok(client.get('/api/users/',headers=headers())))


def test_foundation_grant_creation(client):
    foundation = ok(client.post("/api/foundations", json={"name": "Audit funder"}, headers=headers()), 201)
    grant = ok(client.post(f"/api/foundations/{foundation['id']}/grants", json={"title": "Audit award", "amount_min": 500}, headers=headers()), 201)
    assert grant["foundation_id"] == foundation["id"]


def test_public_donation_and_private_campaign(client):
    campaign = ok(client.post("/api/donors/campaigns", json={"name": "Public audit", "goal_amount": 100}, headers=headers()), 201)
    response = ok(client.post(f"/api/give/{campaign['slug']}/donate", json={"amount": 15, "donor_first_name": "Audit", "donor_email": "audit@example.com"}), 201)
    assert response
    private = ok(client.post("/api/donors/campaigns", json={"name": "Private audit", "is_public": False}, headers=headers()), 201)
    ok(client.get(f"/api/give/{private['slug']}"), 404)


def test_ai_streaming_contract(client, monkeypatch):
    from routers.ai_router import _ai
    async def stream(*args, **kwargs):
        yield "Synthetic"
        yield " response"
    monkeypatch.setattr(_ai, "stream_chat", stream)
    response = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Audit"}], "stream": True}, headers=headers())
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert '"chunk": "Synthetic"' in response.text and "data: [DONE]" in response.text


def test_scraper_dedupe_and_matching():
    from automation.agents.grant_scraper import _dedupe_results, _matches_query, _infer_category
    a = {"title": "Audit", "source_url": "https://example.com"}
    assert len(_dedupe_results([a, dict(a)])) == 1
    assert _matches_query("mentoring", "Youth mentoring program")
    assert not _matches_query("robotics", "Arts festival")
    assert _infer_category("Unclassified opportunity") == "General"


def test_enrichment_url_parsers():
    from routers.grant_enrichment import _extract_fr_doc_number, _extract_grants_gov_opp_id
    assert _extract_fr_doc_number("https://federalregister.gov/documents/2026/09/15/2026-12345/audit") == "2026-12345"
    assert _extract_grants_gov_opp_id("https://grants.gov/view?oppId=12345") == "12345"
    assert _extract_fr_doc_number("https://example.com") is None


def test_match_score_without_profile():
    from routers.grants import _score_match
    assert _score_match({"title": "Youth education"}, None)[0] == 0
