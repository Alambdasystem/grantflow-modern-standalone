"""Seed only synthetic Docker records. Refuse any database other than the lab DB."""
import asyncio
import json
import sys
sys.path.insert(0,'/app/backend')
from sqlalchemy import select
from config import settings
from db.database import AsyncSessionLocal
from models.models import Organization,User,UserRole,Grant,GrantApplication

assert settings.DATABASE_URL=='sqlite+aiosqlite:////data/grantflow-lab.db'
async def main():
    async with AsyncSessionLocal() as db:
        orgs=[]
        for name in ['SYNTHETIC PARITY WYF','SYNTHETIC PARITY OTHER']:
            org=(await db.execute(select(Organization).where(Organization.name==name))).scalar_one_or_none()
            if org is None:
                org=Organization(name=name,mission='Synthetic education and science programs',profile_complete=True);db.add(org);await db.flush()
            orgs.append(org)
        owners={}
        for role in ['admin','viewer','grant_writer','reviewer','other_writer']:
            identity='docker-lab-'+role
            user=(await db.execute(select(User).where(User.identity_id==identity))).scalar_one_or_none()
            if user is None:
                user=User(identity_id=identity,username='parity_'+role,email=role+'@example.test',hashed_password='!synthetic-only!',
                          role=UserRole.grant_writer if role=='other_writer' else UserRole(role),is_active=True,is_approved=True);db.add(user);await db.flush()
            user.organization_id=orgs[1 if role=='other_writer' else 0].id
            owners[role]=user.id
        grant=(await db.execute(select(Grant).where(Grant.title=='SYNTHETIC PARITY Education Grant'))).scalar_one_or_none()
        if grant is None:
            grant=Grant(title='SYNTHETIC PARITY Education Grant',description='Synthetic science education',category='education',amount=10000,status='active');db.add(grant);await db.flush()
        for i in range(1,10):
            title='SYNTHETIC WYF application '+str(i)
            if (await db.execute(select(GrantApplication.id).where(GrantApplication.title==title))).scalar_one_or_none() is None:
                db.add(GrantApplication(grant_id=grant.id,applicant_id=owners['grant_writer'],organization_id=orgs[0].id,title=title))
        await db.commit()
        print(json.dumps({'organizations':[o.id for o in orgs],'owners':owners,'grant_id':grant.id,'synthetic_applications':9}))
asyncio.run(main())
