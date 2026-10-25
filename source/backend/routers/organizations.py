"""Organization profile routes for client onboarding and RAG context management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import Organization, User
from schemas.schemas import OrganizationCreate, OrganizationOut
from auth.jwt_handler import get_current_user_token, require_admin

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("/", response_model=list[OrganizationOut])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(Organization).order_by(Organization.id))
    return result.scalars().all()


@router.get("/me", response_model=OrganizationOut)
async def get_my_organization(
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    user_result = await db.execute(select(User).where(User.identity_id == token["identity_id"]).limit(1))
    user = user_result.scalar_one_or_none()
    if not user or not user.organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    organization = await db.get(Organization, user.organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.patch("/me", response_model=OrganizationOut)
async def update_my_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    user_result = await db.execute(select(User).where(User.identity_id == token["identity_id"]).limit(1))
    user = user_result.scalar_one_or_none()
    if not user or not user.organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    organization = await db.get(Organization, user.organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    for field, value in payload.model_dump().items():
        setattr(organization, field, value)
    organization.profile_complete = True
    await db.commit()
    await db.refresh(organization)
    return organization


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization_by_id(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    organization = await db.get(Organization, org_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.post("/", response_model=OrganizationOut, status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    existing = await db.execute(select(Organization).where(Organization.name == payload.name).limit(1))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization already exists")

    organization = Organization(**payload.model_dump(), profile_complete=True)
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return organization
