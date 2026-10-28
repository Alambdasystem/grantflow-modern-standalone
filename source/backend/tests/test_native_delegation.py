"""Real native sessions; explicit owner delegation never confers admin/tenant access."""
import asyncio,time
import pytest
from sqlalchemy import select
from test_independent_auth import app_client,headers

PASSWORD='Synthetic delegate passphrase 2026!'

def seed(case='valid'):
    from db import database
    from models.models import User,UserRole,Organization,Grant,GrantApplication
    from models.auth_models import AuthDelegation
    from auth.standalone import password_hash
    async def run():
        async with database.AsyncSessionLocal() as db:
            db.add_all([Organization(id=1,name='WYF synthetic'),Organization(id=2,name='Other synthetic')]);await db.flush()
            for uid,org in [(1,1),(2,1),(3,2),(4,1)]:
                db.add(User(id=uid,username='delegate' if uid==2 else 'owner'+str(uid),identity_id='standalone:synthetic-'+str(uid),
                    hashed_password=password_hash(PASSWORD),email=str(uid)+'@example.com',organization_id=org,
                    role=UserRole.viewer if case=='viewer' and uid==2 else UserRole.admin if case=='admin_owner' and uid==1 else UserRole.grant_writer,
                    is_active=not(case=='disabled_owner' and uid==1),is_approved=True))
            db.add(Grant(id=1,title='Synthetic public opportunity'));await db.flush()
            db.add_all([GrantApplication(id=i,grant_id=1,applicant_id=1,organization_id=1,title='Owner application '+str(i)) for i in range(1,10)])
            db.add_all([GrantApplication(id=99,grant_id=1,applicant_id=3,organization_id=2,title='Other tenant'),GrantApplication(id=98,grant_id=1,applicant_id=4,organization_id=1,title='Other owner same tenant')])
            if case!='absent':db.add(AuthDelegation(delegate_user_id=2,owner_user_id=3 if case=='cross_org' else 1,organization_id=1,
                expires_at=int(time.time())+3600 if case!='expired' else 1,reason='Explicit synthetic mirror approval'))
            await db.commit()
    asyncio.run(run())

def login(c):
    r=c.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'delegate','password':PASSWORD})
    assert r.status_code==200,r.text

def test_delegate_sees_exact_owner_records_writes_on_behalf_and_is_audited(app_client):
    c=app_client;seed();login(c)
    assert set(r['id'] for r in c.get('/api/applications/').json())==set(range(1,10))
    assert c.get('/api/applications/99').status_code==404
    assert c.get('/api/applications/98').status_code==404
    assert c.get('/api/organizations/2').status_code==404
    assert c.post('/api/grants/',headers=headers(c),json={'title':'Forbidden admin grant'}).status_code==403
    r=c.post('/api/applications/',headers=headers(c),json={'grant_id':1,'title':'Synthetic delegated onboarding','amount_requested':100})
    assert r.status_code==201,r.text
    assert r.json()['applicant_id']==1 and r.json()['organization_id']==1
    from db import database
    from models.models import AuditLog,User
    async def check():
        async with database.AsyncSessionLocal() as db:
            logs=(await db.execute(select(AuditLog).where(AuditLog.action=='delegated_request'))).scalars().all()
            assert any(x.user_id==2 and x.resource_id==1 and x.details['actor_user_id']==2 for x in logs)
            assert (await db.get(User,1)).username=='owner1'
    asyncio.run(check())

@pytest.mark.parametrize('case',['expired','cross_org','viewer','disabled_owner','admin_owner'])
def test_invalid_delegation_fails_closed(app_client,case):
    seed(case);login(app_client);assert app_client.get('/api/applications/').status_code==403

def test_no_delegation_keeps_owner_isolation_and_revocation_is_immediate(app_client):
    seed('absent');login(app_client);assert app_client.get('/api/applications/').json()==[]
    from db import database
    from models.auth_models import AuthDelegation
    async def set_access(expiry):
        async with database.AsyncSessionLocal() as db:
            row=await db.get(AuthDelegation,2)
            if row:row.expires_at=expiry
            else:db.add(AuthDelegation(delegate_user_id=2,owner_user_id=1,organization_id=1,expires_at=expiry,reason='Synthetic approved'))
            await db.commit()
    asyncio.run(set_access(int(time.time())+3600));assert len(app_client.get('/api/applications/').json())==9
    asyncio.run(set_access(1));assert app_client.get('/api/applications/').status_code==403
