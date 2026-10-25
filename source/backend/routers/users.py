"""Users & Auth router."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import User, UserRole, AuditLog
from schemas.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from auth.jwt_handler import (
    bearer_scheme, get_current_user_token, require_admin,
    revoke_anthesis_identity, validate_anthesis_identity,
)

router = APIRouter(prefix="/api/users", tags=["users"])
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/login")
async def login():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="GrantFlow sign-in moved to Anthesis. Open /auth/login?next=/gfm-app/dashboard",
    )


@auth_router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    await validate_anthesis_identity(credentials.credentials)
    await revoke_anthesis_identity(credentials.credentials)
    return {"success": True}


@auth_router.get("/me", response_model=UserOut)
async def me(token_data: dict = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.identity_id == token_data["identity_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        'id': user.id, 'username': token_data['username'],
        'email': token_data.get('email') or user.email, 'full_name': user.full_name,
        'role': token_data['role'], 'is_active': True, 'created_at': user.created_at,
    }


@router.get("/", response_model=list[UserOut])
async def list_users(
    _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/")
async def create_user(_: dict = Depends(require_admin)):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Create users in Anthesis Rubix; GrantFlow identities are centrally managed",
    )
