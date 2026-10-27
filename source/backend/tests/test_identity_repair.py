"""Synthetic WYF mismatch reproduction and explicitly reviewed lab repair."""
import asyncio
from pathlib import Path
import sqlite3
import sys
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from db import database
from models.models import User,UserRole,Organization,Grant,GrantApplication
from auth import jwt_handler
from routers import users,applications,organizations
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'migration'))
from reviewed_identity_link import reconcile

@pytest.fixture
def mismatch(tmp_path,monkeypatch):
    path=tmp_path/'synthetic-wyf.db'
    engine=create_async_engine('sqlite+aiosqlite:///'+path.as_posix())
    factory=async_sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(database,'AsyncSessionLocal',factory)
    async def seed():
        async with engine.begin() as c: await c.run_sync(database.Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Organization(id=1,name='SYNTHETIC WYF'),Organization(id=2,name='SYNTHETIC OTHER')]);await db.flush()
            db.add_all([User(id=5,username='synthetic_legacy',email='same@example.test',hashed_password='!disabled!',role=UserRole.grant_writer,organization_id=1,is_active=True,is_approved=True),
                        User(id=6,identity_id='other-identity',username='other',email='other@example.test',hashed_password='!disabled!',role=UserRole.grant_writer,organization_id=2,is_active=True,is_approved=True)])
            db.add(Grant(id=1,title='SYNTHETIC grant'));await db.flush()
            for i in range(1,10):db.add(GrantApplication(id=i,grant_id=1,applicant_id=5,organization_id=1,title='Synthetic application '+str(i)))
            db.add(GrantApplication(id=99,grant_id=1,applicant_id=6,organization_id=2,title='Other tenant'));await db.commit()
    asyncio.run(seed())
    async def identity(token):
        return {'identity_id':'other-identity' if token=='other' else 'synthetic-wyf','username':token,
                'email':'same@example.test','role':'viewer' if token=='viewer' else 'grant_writer','grantflow_access':['read','write']}
    monkeypatch.setattr(jwt_handler,'validate_anthesis_identity',identity)
    app=FastAPI()
    for router in [users.auth_router,applications.router,organizations.router]:app.include_router(router)
    decision={'legacy_user_id':5,'expected_username':'synthetic_legacy','expected_org_id':1,'expected_application_count':9,
              'central_identity_id':'synthetic-wyf','approved_by':'synthetic operator','evidence_reference':'synthetic verified membership; not email match'}
    with TestClient(app) as client:yield path,client,decision
    asyncio.run(engine.dispose())

def h(role='writer'):return {'Authorization':'Bearer '+role}

def test_reproduce_then_explicit_link_and_persistence(mismatch):
    path,c,d=mismatch
    assert c.get('/api/applications/',headers=h('viewer')).json()==[]
    assert c.get('/api/organizations/me',headers=h('viewer')).status_code==404
    assert reconcile(path,d)['status']=='dry_run'
    assert c.get('/api/applications/',headers=h()).json()==[]
    with sqlite3.connect(path) as source,sqlite3.connect(path.with_suffix('.backup')) as backup:source.backup(backup)
    assert reconcile(path,d,True)['status']=='applied'
    assert len(c.get('/api/applications/',headers=h()).json())==9
    assert c.get('/api/organizations/me',headers=h()).json()['id']==1
    assert c.get('/api/applications/99',headers=h()).status_code==404
    assert c.get('/api/organizations/2',headers=h()).status_code==404
    assert c.get('/api/applications/1',headers=h('other')).status_code==404
    assert c.patch('/api/applications/1',headers=h('viewer'),json={'title':'denied'}).status_code==403
    assert c.patch('/api/applications/1',headers=h(),json={'title':'Saved synthetic change'}).status_code==200
    assert reconcile(path,d,True)['status']=='already_linked'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT title FROM grant_applications WHERE id=1').fetchone()[0]=='Saved synthetic change'
        assert db.execute('SELECT COUNT(*) FROM grant_applications WHERE applicant_id=5').fetchone()[0]==9
        assert db.execute('SELECT identity_id FROM identity_migration_map WHERE source=? AND source_user_id=?',('gfm','5')).fetchone()[0]=='synthetic-wyf'
    # Explicit copied-store rollback rehearsal, never a production restore.
    with sqlite3.connect(path.with_suffix('.backup')) as backup,sqlite3.connect(path) as target:backup.backup(target)
    assert c.get('/api/applications/',headers=h()).json()==[]

def test_email_match_and_incomplete_approval_do_not_link(mismatch):
    path,c,d=mismatch
    assert c.get('/api/applications/',headers=h()).json()==[]
    with pytest.raises(ValueError):reconcile(path,{**d,'approved_by':''},True)
    with pytest.raises(ValueError):reconcile(path,{**d,'expected_org_id':2},True)
    with pytest.raises(ValueError):reconcile(path,{**d,'central_identity_id':'other-identity'},True)
    assert c.get('/api/applications/1',headers=h('other')).status_code==404

def test_original_host_path_is_refused():
    with pytest.raises(ValueError):reconcile('C:/Users/Owner/Anthesis/grantflow-modern/backend/grantflow_modern.db',{})

def test_bulk_organization_link_preserves_tenant_boundaries(mismatch):
    path,c,d=mismatch
    reconcile(path,d,True)
    r=c.post('/api/applications/bulk-link-org',headers=h(),json={'org_id':1,'application_ids':list(range(1,10))})
    # Organization reassignment now requires an explicit administrator role,
    # including requests that would leave the organization unchanged.
    assert r.status_code==403
    assert c.post('/api/applications/bulk-link-org',headers=h(),json={'org_id':2,'application_ids':[1]}).status_code==403
    assert c.get('/api/applications/1',headers=h()).json()['organization_id']==1
    assert c.get('/api/applications/99',headers=h()).status_code==404
    assert c.post('/api/applications/bulk-link-org',headers=h('viewer'),json={'org_id':1,'application_ids':[1]}).status_code==403
