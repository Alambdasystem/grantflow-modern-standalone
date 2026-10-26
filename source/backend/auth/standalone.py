"""Independent local identity provider: scrypt, hashed opaque sessions, CSRF and revocation.

No public registration, default password, Anthesis fallback, email linking or token
storage in localStorage. Account recovery uses expiring administrator-issued links.
"""
import asyncio
import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import time
import uuid
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from config import settings

router = APIRouter(prefix='/api/auth', tags=['standalone authentication'])


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_name():
    return '__Host-gfm_session' if settings.SESSION_SECURE else 'gfm_session'


def csrf_name():
    return '__Host-gfm_csrf' if settings.SESSION_SECURE else 'gfm_csrf'


def enabled():
    if settings.AUTH_MODE != 'standalone':
        raise HTTPException(404, 'Standalone authentication is not enabled')


def origin(request):
    if request.headers.get('origin') != settings.PUBLIC_ORIGIN.rstrip('/'):
        raise HTTPException(403, 'Request origin is not permitted')


def password_hash(password):
    if not 14 <= len(password) <= 128:
        raise HTTPException(422, 'Use a password or passphrase of 14–128 characters')
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=128*1024*1024)
    return 'scrypt32768$' + base64.urlsafe_b64encode(salt).decode() + '$' + base64.urlsafe_b64encode(value).decode()


def password_matches(password, encoded):
    try:
        algorithm, salt, expected = encoded.split('$')
        if algorithm != 'scrypt32768' or len(password) > 128:
            return False
        actual = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=32768,r=8,p=1,dklen=32,maxmem=128*1024*1024)
        return hmac.compare_digest(actual,base64.urlsafe_b64decode(expected))
    except (ValueError,TypeError):
        return False


async def rate_limit(request, account=''):
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthRate
    now=int(time.time()); ip=request.client.host if request.client else 'unknown'
    keys=[('ip:'+ip,60)]
    if account: keys.append(('account:'+account.lower(),10))
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuthRate).where(AuthRate.until < now))
        for raw,limit in keys:
            key=digest(raw)
            await db.execute(insert(AuthRate).values(key=key,attempts=1,until=now+900)
                .on_conflict_do_update(index_elements=['key'],set_={'attempts':AuthRate.attempts+1}))
            attempts=await db.scalar(select(AuthRate.attempts).where(AuthRate.key==key))
            if attempts>limit:
                await db.commit()
                raise HTTPException(429,'Too many attempts. Try again later.',headers={'Retry-After':'900'})
        await db.commit()


def identity(user,migrated=None):
    role=user.role.value
    scopes=['read'] if role=='viewer' else ['read','write']
    if migrated:
        role='viewer' if 'viewer' in {role,migrated.role_ceiling} else role if migrated.role_ceiling=='admin' else migrated.role_ceiling
        scopes=[s for s in scopes if s in migrated.scopes]
    return {'sub':user.identity_id,'identity_id':user.identity_id,'username':user.username,
            'email':user.email,'role':role,'grantflow_access':scopes}


async def session_record(request, allow_refresh=False):
    enabled()
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthSession,MigratedAccount
    from models.models import User
    raw=request.cookies.get(cookie_name(),'')
    if not 30 <= len(raw) <= 128:
        raise HTTPException(401,'Sign in to GrantFlow')
    async with AsyncSessionLocal() as db:
        session=await db.get(AuthSession,digest(raw))
        now=int(time.time())
        if not session or session.absolute_until<=now or (not allow_refresh and session.access_until<=now):
            raise HTTPException(401,'Session expired or revoked')
        user=await db.get(User,session.user_id)
        migrated=await db.get(MigratedAccount,session.user_id)
        if (not user or not user.is_active or not user.is_approved
                or not ((user.identity_id or '').startswith('standalone:') or migrated)
                or (migrated and (not migrated.permitted or 'read' not in migrated.scopes))):
            raise HTTPException(401,'Session expired or revoked')
        if request.method.upper() not in {'GET','HEAD','OPTIONS'}:
            origin(request)
            csrf=request.headers.get('x-csrf-token','')
            if not csrf or not hmac.compare_digest(digest(csrf),session.csrf_hash):
                raise HTTPException(403,'CSRF validation failed')
        return session,user


async def authorize(request):
    _,user=await session_record(request)
    from db.database import AsyncSessionLocal
    from models.auth_models import MigratedAccount
    async with AsyncSessionLocal() as db:
        return identity(user,await db.get(MigratedAccount,user.id))


def set_cookies(response, raw, csrf, until):
    age=max(0,until-int(time.time()))
    common={'secure':settings.SESSION_SECURE,'samesite':'lax','path':'/','max_age':age}
    response.set_cookie(cookie_name(),raw,httponly=True,**common)
    response.set_cookie(csrf_name(),csrf,httponly=False,**common)
    response.headers['Cache-Control']='no-store'


async def issue_session(db,user,response,absolute=None):
    from models.auth_models import AuthSession
    now=int(time.time()); until=absolute or now+settings.SESSION_ABSOLUTE_SECONDS
    await db.execute(delete(AuthSession).where(AuthSession.absolute_until<=now))
    raw=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=digest(raw),user_id=user.id,csrf_hash=digest(csrf),
                       access_until=min(until,now+settings.SESSION_ACCESS_SECONDS),absolute_until=until))
    await db.commit()
    set_cookies(response,raw,csrf,until)
    from models.auth_models import MigratedAccount
    who=identity(user,await db.get(MigratedAccount,user.id))
    return {'username':user.username,'role':who['role'],'expires_in':settings.SESSION_ACCESS_SECONDS}


class Credentials(BaseModel):
    username: str = Field(min_length=1,max_length=255)
    password: str = Field(min_length=1,max_length=128)


class Setup(Credentials):
    email: EmailStr
    organization: str = Field(min_length=1,max_length=255)
    bootstrap_token: str = Field(min_length=32,max_length=512)


class Invitation(BaseModel):
    email: EmailStr
    organization_id: int
    role: str = 'grant_writer'
    reset_user_id: int | None = None


class Accept(Credentials):
    token: str = Field(min_length=32,max_length=128)


def normalized_username(value):
    name=value.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,99}',name):
        raise HTTPException(422,'Username must be 3–100 letters, digits, dots, underscores or hyphens')
    return name


@router.get('/status')
async def auth_status(response:Response):
    response.headers['Cache-Control']='no-store'
    if settings.AUTH_MODE!='standalone':
        return {'mode':'anthesis','setup_required':False}
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthControl
    async with AsyncSessionLocal() as db:
        control=await db.get(AuthControl,1)
        return {'mode':'standalone','setup_required':bool(control and not control.bootstrapped)}


@router.post('/setup')
async def setup(payload:Setup,request:Request,response:Response):
    enabled(); origin(request); await rate_limit(request,'bootstrap')
    configured=settings.GFM_BOOTSTRAP_TOKEN
    if settings.GFM_BOOTSTRAP_TOKEN_FILE:
        try: configured=Path(settings.GFM_BOOTSTRAP_TOKEN_FILE).read_text().strip()
        except OSError: raise HTTPException(503,'Administrator setup secret is unavailable') from None
    if len(configured)<32 or not hmac.compare_digest(digest(configured),digest(payload.bootstrap_token)):
        raise HTTPException(403,'Administrator setup is not authorized')
    name=normalized_username(payload.username)
    encoded=await asyncio.to_thread(password_hash,payload.password)
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthControl
    from models.models import User,UserRole,Organization
    async with AsyncSessionLocal() as db:
        changed=await db.execute(update(AuthControl).where(AuthControl.id==1,AuthControl.bootstrapped==False).values(bootstrapped=True))
        if changed.rowcount!=1: raise HTTPException(409,'Administrator setup has already completed')
        org=Organization(name=payload.organization.strip()); db.add(org); await db.flush()
        user=User(username=name,email=str(payload.email).lower(),hashed_password=encoded,
                  identity_id='standalone:'+uuid.uuid4().hex,role=UserRole.admin,organization_id=org.id,is_active=True,is_approved=True)
        db.add(user)
        try: await db.flush()
        except IntegrityError: raise HTTPException(409,'Account details are unavailable') from None
        return await issue_session(db,user,response)


async def login(payload:Credentials,request:Request,response:Response):
    enabled(); origin(request)
    name=payload.username.strip().lower(); await rate_limit(request,name)
    from db.database import AsyncSessionLocal
    from models.models import User
    from models.auth_models import MigratedAccount
    async with AsyncSessionLocal() as db:
        user=await db.scalar(select(User).where(func.lower(User.username)==name))
        if not user:
            alias=await db.scalar(select(MigratedAccount).where(MigratedAccount.login_alias==name))
            if alias: user=await db.get(User,alias.user_id)
        migrated=await db.get(MigratedAccount,user.id) if user else None
        allowed=bool(user and ((user.identity_id or '').startswith('standalone:') or migrated))
        # An unknown identity still pays the same scrypt cost; errors do not enumerate accounts.
        candidate=user.hashed_password if user else 'scrypt32768$MDAwMDAwMDAwMDAwMDAwMA==$MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='
        if migrated and not candidate.startswith('scrypt32768$'):
            from auth.legacy_passwords import verify
            valid=await asyncio.to_thread(verify,payload.password,candidate)
        else:
            valid=await asyncio.to_thread(password_matches,payload.password,candidate)
        if (not valid or not allowed or not user.is_active or not user.is_approved
                or (migrated and (not migrated.permitted or 'read' not in migrated.scopes))):
            raise HTTPException(401,'Invalid username or password')
        if migrated and not candidate.startswith('scrypt32768$'):
            # Legacy passwords may be shorter than the new-account policy; a
            # successful existing password must not be silently changed.
            user.hashed_password=await asyncio.to_thread(_rehash_legacy,payload.password)
        return await issue_session(db,user,response)


def _rehash_legacy(password):
    salt=secrets.token_bytes(16)
    value=hashlib.scrypt(password.encode(),salt=salt,n=32768,r=8,p=1,dklen=32,maxmem=128*1024*1024)
    return 'scrypt32768$'+base64.urlsafe_b64encode(salt).decode()+'$'+base64.urlsafe_b64encode(value).decode()


@router.post('/refresh')
async def refresh(request:Request,response:Response):
    session,user=await session_record(request,allow_refresh=True)
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthSession
    async with AsyncSessionLocal() as db:
        consumed=await db.execute(delete(AuthSession).where(AuthSession.token_hash==session.token_hash))
        if consumed.rowcount!=1: raise HTTPException(401,'Session already rotated or revoked')
        return await issue_session(db,user,response,session.absolute_until)


async def logout(request,response):
    session,_=await session_record(request,allow_refresh=True)
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthSession
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash==session.token_hash)); await db.commit()
    for name in [cookie_name(),csrf_name()]:
        response.delete_cookie(name,path='/',secure=settings.SESSION_SECURE,samesite='lax')
    response.headers['Cache-Control']='no-store'
    return {'success':True}


async def admin(request:Request):
    who=await authorize(request)
    if who['role']!='admin': raise HTTPException(403,'Administrator access required')
    return who


@router.post('/invitations',dependencies=[Depends(admin)])
async def invite(payload:Invitation,response:Response):
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthInvitation,MigratedAccount
    from models.models import Organization,User
    if payload.role not in {'admin','grant_writer','reviewer','viewer'}: raise HTTPException(422,'Invalid role')
    async with AsyncSessionLocal() as db:
        if not await db.get(Organization,payload.organization_id): raise HTTPException(404,'Organization not found')
        if payload.reset_user_id:
            user=await db.get(User,payload.reset_user_id)
            if (not user or not ((user.identity_id or '').startswith('standalone:') or await db.get(MigratedAccount,user.id))
                    or user.email.lower()!=str(payload.email).lower() or user.organization_id!=payload.organization_id):
                raise HTTPException(409,'Recovery must explicitly match an existing standalone identity and organization')
        raw=secrets.token_urlsafe(32)
        db.add(AuthInvitation(token_hash=digest(raw),email=str(payload.email).lower(),role=payload.role,
                             organization_id=payload.organization_id,reset_user_id=payload.reset_user_id,expires_at=int(time.time())+86400))
        await db.commit(); response.headers['Cache-Control']='no-store'
        return {'url':settings.PUBLIC_ORIGIN.rstrip('/')+'/gfm-app/login#invite='+raw,'expires_in':86400}


@router.post('/accept')
async def accept(payload:Accept,request:Request,response:Response):
    enabled(); origin(request); await rate_limit(request,'invite:'+digest(payload.token))
    name=normalized_username(payload.username); encoded=await asyncio.to_thread(password_hash,payload.password)
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthInvitation,AuthSession
    from models.models import User,UserRole
    async with AsyncSessionLocal() as db:
        invitation=await db.get(AuthInvitation,digest(payload.token))
        if not invitation or invitation.expires_at<=int(time.time()): raise HTTPException(403,'Invitation is invalid or expired')
        consumed=await db.execute(delete(AuthInvitation).where(AuthInvitation.token_hash==invitation.token_hash))
        if consumed.rowcount!=1: raise HTTPException(403,'Invitation already used')
        if invitation.reset_user_id:
            user=await db.get(User,invitation.reset_user_id)
            if not user or user.username!=name: raise HTTPException(409,'Recovery username does not match')
            # Recovery never grants a new role or changes ownership.
            user.hashed_password=encoded
            await db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
        else:
            user=User(username=name,email=invitation.email,hashed_password=encoded,identity_id='standalone:'+uuid.uuid4().hex,
                      role=UserRole(invitation.role),organization_id=invitation.organization_id,is_active=True,is_approved=True)
            db.add(user)
        try: await db.flush()
        except IntegrityError: raise HTTPException(409,'Account details are unavailable') from None
        await db.commit()
        return {'success':True,'message':'Account saved. Sign in with your password.'}


class AccountState(BaseModel):
    is_active: bool
    role: str


@router.patch('/accounts/{user_id}',dependencies=[Depends(admin)])
async def account_state(user_id:int,payload:AccountState,request:Request):
    from db.database import AsyncSessionLocal
    from models.auth_models import AuthSession,MigratedAccount
    from models.models import User,UserRole
    if payload.role not in {'admin','grant_writer','reviewer','viewer'}: raise HTTPException(422,'Invalid role')
    current=await authorize(request)
    async with AsyncSessionLocal() as db:
        user=await db.get(User,user_id)
        migrated=await db.get(MigratedAccount,user_id)
        if not user or not ((user.identity_id or '').startswith('standalone:') or migrated): raise HTTPException(404,'Standalone account not found')
        if user.identity_id==current['identity_id'] and (not payload.is_active or payload.role!='admin'):
            raise HTTPException(409,'Use another administrator to change your own administrator access')
        user.is_active=payload.is_active; user.role=UserRole(payload.role)
        if migrated:
            # Explicit destination-administrator decision, never automatic linking.
            migrated.role_ceiling=payload.role; migrated.permitted=payload.is_active
            migrated.scopes=['read'] if payload.role=='viewer' else ['read','write']
        await db.execute(delete(AuthSession).where(AuthSession.user_id==user.id)); await db.commit()
        return {'success':True}
