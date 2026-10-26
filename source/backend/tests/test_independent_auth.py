"""Real password/session provider against disposable SQLite; no mocked authentication."""
import asyncio
import hashlib
import secrets
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from config import settings


@pytest.fixture
def app_client(tmp_path,monkeypatch):
    from db import database
    monkeypatch.setattr(settings,'AUTH_MODE','standalone')
    monkeypatch.setattr(settings,'PUBLIC_ORIGIN','https://testserver')
    monkeypatch.setattr(settings,'SESSION_SECURE',True)
    monkeypatch.setattr(settings,'GFM_BOOTSTRAP_TOKEN',secrets.token_urlsafe(32))
    monkeypatch.setattr(settings,'GFM_BOOTSTRAP_TOKEN_FILE','')
    monkeypatch.setattr(settings,'AUTOMATION_WORKER_ENABLED',False)
    monkeypatch.setattr(settings,'INGESTION_LOCAL_WORKER_ENABLED',False)
    monkeypatch.setattr(settings,'RUN_LEGACY_STARTUP_IMPORTS',False)
    monkeypatch.setattr(settings,'UPLOAD_DIR',str(tmp_path/'uploads'))
    monkeypatch.setattr(settings,'INGESTION_STORAGE_DIR',str(tmp_path/'documents'))
    engine=create_async_engine('sqlite+aiosqlite:///'+str(tmp_path/'test.db'))
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'AsyncSessionLocal',async_sessionmaker(engine,expire_on_commit=False))
    from main import app
    with TestClient(app,base_url='https://testserver') as client:
        yield client
    asyncio.run(engine.dispose())


def headers(client):
    return {'Origin':'https://testserver','X-CSRF-Token':client.cookies.get('__Host-gfm_csrf','')}


def setup(client):
    response=client.post('/api/auth/setup',headers={'Origin':'https://testserver'},json={
        'username':'test_admin','password':'Synthetic passphrase for tests 42!',
        'email':'synthetic-admin@example.com','organization':'Synthetic organization',
        'bootstrap_token':settings.GFM_BOOTSTRAP_TOKEN})
    assert response.status_code==200,response.text
    return response


def test_secure_setup_login_and_cookie_properties(app_client):
    c=app_client
    assert c.get('/api/auth/status').json()['setup_required'] is True
    assert c.get('/api/applications/').status_code==401
    response=setup(c)
    cookie=response.headers.get_list('set-cookie')[0]
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie and 'Path=/' in cookie
    assert 'access_token' not in response.json()
    assert c.get('/api/auth/me').json()['role']=='admin'
    assert c.get('/api/analytics/dashboard').status_code==200
    assert c.post('/api/auth/setup',headers=headers(c),json={'username':'again','password':'Synthetic passphrase for tests 42!',
        'email':'again@example.com','organization':'No','bootstrap_token':settings.GFM_BOOTSTRAP_TOKEN}).status_code==409


def test_setup_secret_origin_and_no_default_accounts(app_client):
    c=app_client
    payload={'username':'admin','password':'Synthetic passphrase for tests 42!','email':'admin@example.com',
        'organization':'Synthetic','bootstrap_token':'x'*40}
    assert c.post('/api/auth/setup',json=payload).status_code==403
    assert c.post('/api/auth/setup',json=payload,headers={'Origin':'https://evil.example.com'}).status_code==403
    assert c.post('/api/auth/setup',json=payload,headers={'Origin':'https://testserver'}).status_code==403
    assert c.post('/api/auth/login',json={'username':'admin','password':'admin'},headers={'Origin':'https://testserver'}).status_code==401


def test_csrf_logout_and_revoked_session(app_client):
    c=app_client;setup(c)
    raw=c.cookies.get('__Host-gfm_session')
    assert c.post('/api/auth/logout').status_code==403
    assert c.post('/api/auth/logout',headers={'Origin':'https://evil.example.com','X-CSRF-Token':c.cookies['__Host-gfm_csrf']}).status_code==403
    assert c.post('/api/auth/logout',headers=headers(c)).status_code==200
    c.cookies.set('__Host-gfm_session',raw)
    assert c.get('/api/auth/me').status_code==401
    c.cookies.clear()
    assert c.get('/api/auth/me',headers={'Authorization':'Bearer '+raw}).status_code==401


def test_refresh_rotation_expiry_and_restart_persistence(app_client):
    from db import database
    from models.auth_models import AuthSession
    c=app_client;setup(c);old=c.cookies.get('__Host-gfm_session');old_csrf=c.cookies.get('__Host-gfm_csrf')
    async def expire_access():
        async with database.AsyncSessionLocal() as db:
            await db.execute(update(AuthSession).values(access_until=int(time.time())-1));await db.commit()
    asyncio.run(expire_access())
    assert c.get('/api/auth/me').status_code==401
    assert c.post('/api/auth/refresh',headers=headers(c)).status_code==200
    new=c.cookies.get('__Host-gfm_session');assert old!=new
    assert c.get('/api/auth/me').status_code==200
    # New client uses durable server-side session after app lifespan restart.
    from main import app
    with TestClient(app,base_url='https://testserver') as other:
        other.cookies.set('__Host-gfm_session',new)
        assert other.get('/api/auth/me').status_code==200
        other.cookies.set('__Host-gfm_session',old)
        assert other.post('/api/auth/refresh',headers={'Origin':'https://testserver','X-CSRF-Token':old_csrf}).status_code==401
    async def expire_absolute():
        async with database.AsyncSessionLocal() as db:
            await db.execute(update(AuthSession).values(absolute_until=int(time.time())-1));await db.commit()
    asyncio.run(expire_absolute())
    assert c.post('/api/auth/refresh',headers=headers(c)).status_code==401


def test_invitation_roles_tenants_and_recovery(app_client):
    c=app_client;setup(c)
    org=c.get('/api/organizations/me').json()['id']
    result=c.post('/api/auth/invitations',headers=headers(c),json={'email':'viewer@example.com','organization_id':org,'role':'viewer'})
    assert result.status_code==200,result.text
    raw=result.json()['url'].split('#invite=')[1]
    from main import app
    with TestClient(app,base_url='https://testserver') as viewer:
        payload={'token':raw,'username':'test_viewer','password':'Another synthetic passphrase 42!'}
        assert viewer.post('/api/auth/accept',headers={'Origin':'https://testserver'},json=payload).status_code==200
        assert viewer.post('/api/auth/accept',headers={'Origin':'https://testserver'},json=payload).status_code==403
        assert viewer.post('/api/auth/login',headers={'Origin':'https://testserver'},json={k:payload[k] for k in ('username','password')}).status_code==200
        assert viewer.get('/api/analytics/dashboard').status_code==200
        assert viewer.post('/api/applications/',headers=headers(viewer),json={'grant_id':1,'title':'denied'}).status_code==403
        assert viewer.post('/api/auth/invitations',headers=headers(viewer),json={'email':'bad@example.com','organization_id':org}).status_code==403
        user=c.get('/api/users/').json(); user=next(u for u in user if u['username']=='test_viewer')
        recovery=c.post('/api/auth/invitations',headers=headers(c),json={'email':'viewer@example.com','organization_id':org,'reset_user_id':user['id']}).json()['url'].split('#invite=')[1]
        payload['token']=recovery;payload['password']='Replaced synthetic passphrase 43!'
        assert viewer.post('/api/auth/accept',headers={'Origin':'https://testserver'},json=payload).status_code==200
        assert viewer.get('/api/auth/me').status_code==401
        assert viewer.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'test_viewer','password':payload['password']}).status_code==200
        assert viewer.get('/api/auth/me').json()['role']=='viewer'
        assert c.patch('/api/auth/accounts/'+str(user['id']),headers=headers(c),json={'is_active':False,'role':'viewer'}).status_code==200
        assert viewer.get('/api/auth/me').status_code==401


def test_migrations_and_hashed_persistence(app_client):
    from db import database
    from models.models import User
    from models.auth_models import AuthSession
    c=app_client;setup(c);raw=c.cookies['__Host-gfm_session']
    async def check():
        await database.init_db();await database.init_db()
        async with database.AsyncSessionLocal() as db:
            user=await db.scalar(select(User))
            assert user.hashed_password.startswith('scrypt32768$') and 'passphrase' not in user.hashed_password
            session=await db.scalar(select(AuthSession));assert session.token_hash==hashlib.sha256(raw.encode()).hexdigest()
            assert raw not in session.token_hash
    asyncio.run(check())


def test_account_rate_limit_and_invalid_cookie(app_client):
    c=app_client
    assert c.get('/api/auth/me',headers={'Cookie':'__Host-gfm_session=not-a-session'}).status_code==401
    for _ in range(10):
        assert c.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'unknown','password':'wrong'}).status_code==401
    assert c.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'unknown','password':'wrong'}).status_code==429


def test_saved_application_upload_and_tenant_denial(app_client):
    c=app_client;setup(c)
    grant=c.post('/api/grants/',headers=headers(c),json={'title':'Synthetic independent grant','description':'Public synthetic opportunity'})
    assert grant.status_code==201,grant.text
    org1=c.get('/api/organizations/me').json()['id']
    org2=c.post('/api/organizations/',headers=headers(c),json={'name':'Second synthetic organization'})
    assert org2.status_code==201,org2.text
    from main import app
    writers=[]
    try:
        for i,org in enumerate([org1,org2.json()['id']]):
            raw=c.post('/api/auth/invitations',headers=headers(c),json={'email':f'writer{i}@example.com','role':'grant_writer','organization_id':org}).json()['url'].split('#invite=')[1]
            writer=TestClient(app,base_url='https://testserver');writer.__enter__();writers.append(writer)
            payload={'token':raw,'username':f'writer{i}','password':'Synthetic writer passphrase 42!'}
            assert writer.post('/api/auth/accept',headers={'Origin':'https://testserver'},json=payload).status_code==200
            assert writer.post('/api/auth/login',headers={'Origin':'https://testserver'},json={k:payload[k] for k in ('username','password')}).status_code==200
        first,other=writers
        app_record=first.post('/api/applications/',headers=headers(first),json={'grant_id':grant.json()['id'],'title':'Private saved application'})
        assert app_record.status_code==201,app_record.text
        appid=app_record.json()['id']
        assert first.patch(f'/api/applications/{appid}',headers=headers(first),json={'notes':'Synthetic persistent note'}).status_code==200
        assert first.get(f'/api/applications/{appid}').json()['notes']=='Synthetic persistent note'
        assert other.get(f'/api/applications/{appid}').status_code==404
        assert first.get('/api/organizations/'+str(org2.json()['id'])).status_code==404
        raw=b'Synthetic organization upload evidence.'
        upload=first.post('/api/ingestion/upload',headers=headers(first),files={'file':('evidence.txt',raw,'text/plain')})
        assert upload.status_code==202,upload.text
        doc=upload.json()['id']
        assert first.get(f'/api/ingestion/documents/{doc}/original').content==raw
        assert other.get(f'/api/ingestion/documents/{doc}/original').status_code==404
        assert other.post('/api/auth/invitations',headers=headers(other),json={'email':'forbidden@example.com','organization_id':org1}).status_code==403
    finally:
        for writer in writers: writer.__exit__(None,None,None)
