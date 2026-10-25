"""Real API and SQLAlchemy dependencies against disposable data; no startup agents."""
import asyncio
import os
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

os.environ['DEBUG'] = 'false'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import database
from models.models import User, UserRole, Grant, GrantApplication, Organization
from routers import applications, organizations, users
from auth import jwt_handler


@pytest.fixture
def client(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings,'INGESTION_STORAGE_DIR',str(tmp_path/'private-documents'))
    monkeypatch.setattr(settings,'INGESTION_SOURCE_MANIFEST','')
    engine = create_async_engine('sqlite+aiosqlite:///' + (tmp_path / 'isolated.db').as_posix())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'AsyncSessionLocal', factory)
    async def setup():
        async with engine.begin() as c:
            await c.run_sync(database.Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Organization(id=1, name='one'), Organization(id=2, name='two')])
            await db.flush()
            db.add_all([User(id=i, identity_id='central-'+str(i), username='user'+str(i),
                             email=str(i)+'@example.test', hashed_password='!disabled!',
                             role=UserRole.grant_writer, organization_id=i, is_active=True, is_approved=True) for i in (1,2)])
            db.add(Grant(id=1, title='Shared catalog grant'))
            await db.flush()
            db.add_all([GrantApplication(id=i, grant_id=1, applicant_id=i, organization_id=i, title='Application '+str(i)) for i in (1,2)])
            await db.commit()
    asyncio.run(setup())
    async def validate(value):
        if value not in {'writer', 'viewer', 'admin', 'new'}:
            from fastapi import HTTPException
            raise HTTPException(401, 'Invalid central token')
        return {'identity_id': 'central-3' if value == 'new' else 'central-1',
                'username': value, 'role': value if value in {'admin', 'viewer'} else 'grant_writer',
                'grantflow_access': ['read'] if value == 'viewer' else ['read', 'write']}
    monkeypatch.setattr(jwt_handler, 'validate_anthesis_identity', validate)
    app = FastAPI()
    for router in (applications.router, organizations.router, users.auth_router, users.router):
        app.include_router(router)
    with TestClient(app) as c:
        yield c
    asyncio.run(engine.dispose())


def headers(role='writer'):
    return {'Authorization': 'Bearer '+role}


def test_lists_and_detail_are_owner_scoped(client):
    r = client.get('/api/applications/', headers=headers())
    assert r.status_code == 200, r.text
    assert [x['id'] for x in r.json()] == [1]
    assert client.get('/api/applications/2', headers=headers()).status_code == 404
    assert client.get('/api/organizations/2', headers=headers()).status_code == 404
    assert client.get('/api/applications/2', headers=headers('admin')).status_code == 200


def test_cannot_modify_or_upload_to_another_owner(client):
    assert client.patch('/api/applications/2', headers=headers(), json={'title': 'changed'}).status_code == 404
    r = client.post('/api/applications/', headers=headers(), json={'grant_id': 1, 'organization_id': 2})
    assert r.status_code == 403, r.text


def test_read_scope_cannot_write_and_auth_is_required(client):
    assert client.post('/api/applications/', headers=headers('viewer'), json={'grant_id': 1}).status_code == 403
    assert client.get('/api/applications/').status_code == 401
    assert client.get('/api/applications/', headers=headers('old-local-jwt')).status_code == 401
    assert client.get('/api/users/', headers=headers()).status_code == 403


def test_new_central_identity_gets_owner_projection_without_local_password(client):
    r = client.post('/api/applications/', headers=headers('new'), json={'grant_id': 1, 'title': 'New central owner'})
    assert r.status_code == 201, r.text
    result = client.get('/api/applications/', headers=headers('new'))
    assert len(result.json()) == 1
    assert result.json()[0]['title'] == 'New central owner'


def test_legacy_gfm_login_disabled(client):
    assert client.post('/api/auth/login', json={'username': 'old', 'password': 'anything'}).status_code == 410
