"""Synthetic original formats and stable ownership; no real user credentials."""
import asyncio
import hashlib
import pytest
import bcrypt
from werkzeug.security import generate_password_hash
from auth.legacy_passwords import verify,supported
from test_independent_auth import app_client,setup,headers


@pytest.mark.parametrize('method',['bcrypt','pbkdf2:sha256:260000','pbkdf2:sha256:600000','pbkdf2:sha256:1000000','scrypt:32768:8:1'])
def test_source_hash_formats(method):
    password='Existing synthetic password'
    encoded=bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=4)).decode() if method=='bcrypt' else generate_password_hash(password,method=method)
    assert supported(encoded) and verify(password,encoded)
    assert not verify('incorrect',encoded)


@pytest.mark.parametrize('encoded',['plaintext','!central-identity-only!',hashlib.sha256(b'weak').hexdigest(),'pbkdf2:sha256:999999999$x$abc','scrypt:999999999:8:1$x$abc'])
def test_unsafe_or_unknown_hashes_require_recovery(encoded):
    assert not supported(encoded) and not verify('anything',encoded)


def test_migrated_password_ownership_rehash_and_ceiling(app_client):
    c=app_client;setup(c)
    from db.database import AsyncSessionLocal
    from models.models import User,Organization,UserRole,GrantApplication,Grant
    from models.models import Document
    from config import settings
    from pathlib import Path
    from models.auth_models import MigratedAccount
    from sqlalchemy import select
    async def seed():
        async with AsyncSessionLocal() as db:
            org=Organization(name='Synthetic migrated organization');db.add(org);await db.flush()
            owner=User(username='Original_Owner',email='owner@example.invalid',identity_id='migrated:synthetic:5',
                hashed_password=bcrypt.hashpw(b'OldPwd7!',bcrypt.gensalt(rounds=4)).decode(),role=UserRole.grant_writer,
                organization_id=org.id,is_active=True,is_approved=True)
            viewer=User(username='central_projection',email='viewer@example.invalid',identity_id='synthetic-stable-viewer',
                hashed_password=generate_password_hash('Existing viewer password',method='pbkdf2:sha256:260000'),
                role=UserRole.grant_writer,is_active=True,is_approved=True)
            db.add_all([owner,viewer]);await db.flush()
            db.add_all([MigratedAccount(user_id=owner.id,source_identity='synthetic/5',credential_source='legacy',
                permitted=True,role_ceiling='grant_writer',scopes=['read','write']),
                MigratedAccount(user_id=viewer.id,source_identity='synthetic-stable-viewer',credential_source='central',
                permitted=True,role_ceiling='viewer',scopes=['read','write'],login_alias='central_viewer')])
            grant=Grant(title='Synthetic existing grant');db.add(grant);await db.flush()
            for n in range(9): db.add(GrantApplication(title=f'Synthetic prior application {n}',grant_id=grant.id,applicant_id=owner.id,organization_id=org.id))
            root=Path(settings.UPLOAD_DIR);root.mkdir(parents=True,exist_ok=True)
            (root/'historical.txt').write_bytes(b'Synthetic existing document')
            document=Document(filename='historical.txt',file_path=str(root/'historical.txt'),organization_id=org.id)
            escaped=Document(filename='escaped',file_path='/etc/passwd',organization_id=org.id)
            db.add_all([document,escaped]);await db.flush()
            await db.commit();return owner.id,viewer.id,document.id,escaped.id
    owner,viewer,document_id,escaped_id=asyncio.run(seed())
    c.cookies.clear()
    assert c.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'original_owner','password':'bad'}).status_code==401
    r=c.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'Original_Owner','password':'OldPwd7!'})
    assert r.status_code==200 and r.json()['role']=='grant_writer'
    assert len(c.get('/api/applications/').json())==9
    assert c.get(f'/api/ingestion/legacy-documents/{document_id}/original').content==b'Synthetic existing document'
    assert c.get(f'/api/ingestion/legacy-documents/{escaped_id}/original').status_code==404
    async def hash_after():
        async with AsyncSessionLocal() as db: return (await db.get(User,owner)).hashed_password
    assert asyncio.run(hash_after()).startswith('scrypt32768$')
    c.cookies.clear()
    r=c.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'central_viewer','password':'Existing viewer password'})
    assert r.status_code==200 and r.json()['role']=='viewer'
    assert c.get('/api/applications/').json()==[]
    assert c.get('/api/ingestion/legacy-documents').json()==[]
    assert c.get(f'/api/ingestion/legacy-documents/{document_id}/original').status_code==404
    assert c.post('/api/applications/',headers=headers(c),json={}).status_code==403


def test_migration_hold_blocks_external_dispatch(app_client,monkeypatch):
    c=app_client;setup(c)
    from db.database import AsyncSessionLocal
    from models.auth_models import MigrationSafety
    from services import job_queue
    async def hold():
        async with AsyncSessionLocal() as db:
            db.add(MigrationSafety(id=1,external_jobs_paused=True,source_cutoff='synthetic'));await db.commit()
        await job_queue.schedule_renewals()
    asyncio.run(hold())
    r=c.post('/api/providers/grants_gov/connect',headers=headers(c))
    assert r.status_code==409
    assert c.post('/api/workspace/grants-gov/sync',headers=headers(c)).status_code==409
