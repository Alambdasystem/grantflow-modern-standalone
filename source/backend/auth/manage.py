"""Operator-only password recovery from an authenticated container shell.

Never accepts passwords on argv or prints them. Does not import or link accounts.
"""
import argparse
import asyncio
import getpass
from pathlib import Path
from urllib.parse import urlsplit
from config import settings


async def run(username,enable):
    if settings.AUTH_MODE!='standalone': raise RuntimeError('Standalone mode is required')
    path=Path(urlsplit(settings.DATABASE_URL).path).resolve()
    if Path(settings.GFM_DATA_ROOT).resolve() not in path.parents or '/anthesis/' in path.as_posix().lower():
        raise RuntimeError('Recovery is restricted to the standalone data root')
    from db.database import AsyncSessionLocal
    from models.models import User
    from models.auth_models import AuthSession,AuthRate
    from auth.standalone import password_hash,digest
    from sqlalchemy import select,delete
    async with AsyncSessionLocal() as db:
        user=await db.scalar(select(User).where(User.username==username,User.identity_id.like('standalone:%')))
        if not user: raise RuntimeError('Standalone user not found')
        password=getpass.getpass('New password: ')
        if password!=getpass.getpass('Confirm password: '): raise RuntimeError('Passwords differ')
        user.hashed_password=await asyncio.to_thread(password_hash,password)
        if enable: user.is_active=True
        await db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
        await db.execute(delete(AuthRate).where(AuthRate.key==digest('account:'+username.lower())))
        await db.commit()
    print('Password changed; all sessions revoked. Role and organization were preserved.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument('--enable',action='store_true')
    args=parser.parse_args()
    asyncio.run(run(args.username,args.enable))
