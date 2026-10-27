"""Foundation grants management — private, community, corporate, family foundations."""
import os, sys
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import Foundation, FoundationContact, Grant, GrantApplication
from auth.jwt_handler import get_current_user_token

router = APIRouter(prefix="/api/foundations", tags=["foundations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class FoundationContactIn(BaseModel):
    name: str
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary: bool = False
    relationship_notes: Optional[str] = None


class FoundationIn(BaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    grant_type: str = "private"
    focus_areas: list[str] = []
    geographic_focus: Optional[str] = None
    portal_type: str = "website"
    portal_url: Optional[str] = None
    portal_key: Optional[str] = None
    typical_amount_min: Optional[float] = None
    typical_amount_max: Optional[float] = None
    accepts_unsolicited: bool = True
    requires_loi: bool = False
    loi_deadline_days_before: int = 60
    cycle: str = "rolling"
    eligibility_notes: Optional[str] = None
    notes: Optional[str] = None
    contacts: list[FoundationContactIn] = []


class FoundationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    grant_type: Optional[str] = None
    focus_areas: Optional[list[str]] = None
    geographic_focus: Optional[str] = None
    portal_type: Optional[str] = None
    portal_url: Optional[str] = None
    portal_key: Optional[str] = None
    typical_amount_min: Optional[float] = None
    typical_amount_max: Optional[float] = None
    accepts_unsolicited: Optional[bool] = None
    requires_loi: Optional[bool] = None
    loi_deadline_days_before: Optional[int] = None
    cycle: Optional[str] = None
    eligibility_notes: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize(f: Foundation) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "description": f.description,
        "website": f.website,
        "grant_type": f.grant_type,
        "focus_areas": f.focus_areas or [],
        "geographic_focus": f.geographic_focus,
        "portal_type": f.portal_type,
        "portal_url": f.portal_url,
        "portal_key": f.portal_key,
        "typical_amount_min": f.typical_amount_min,
        "typical_amount_max": f.typical_amount_max,
        "accepts_unsolicited": f.accepts_unsolicited,
        "requires_loi": f.requires_loi,
        "loi_deadline_days_before": f.loi_deadline_days_before,
        "cycle": f.cycle,
        "eligibility_notes": f.eligibility_notes,
        "notes": f.notes,
        "is_active": f.is_active,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "contacts": [
            {
                "id": c.id,
                "name": c.name,
                "title": c.title,
                "email": c.email,
                "phone": c.phone,
                "is_primary": c.is_primary,
                "relationship_notes": c.relationship_notes,
            }
            for c in (f.contacts or [])
        ],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_foundations(
    q: Optional[str] = Query(None),
    grant_type: Optional[str] = Query(None),
    cycle: Optional[str] = Query(None),
    requires_loi: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(True),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    stmt = select(Foundation).options(selectinload(Foundation.contacts))
    if is_active is not None:
        stmt = stmt.where(Foundation.is_active == is_active)
    if grant_type:
        stmt = stmt.where(Foundation.grant_type == grant_type)
    if cycle:
        stmt = stmt.where(Foundation.cycle == cycle)
    if requires_loi is not None:
        stmt = stmt.where(Foundation.requires_loi == requires_loi)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(Foundation.name.ilike(like), Foundation.description.ilike(like),
                Foundation.geographic_focus.ilike(like))
        )
    stmt = stmt.order_by(Foundation.id.asc())
    result = await db.execute(stmt)
    from services.grant_integrity import normalized, source_key
    foundations, seen = [], set()
    for row in result.scalars().all():
        key = (normalized(row.name), source_key(row.website))
        if row.website and key in seen:
            continue
        if row.website:
            seen.add(key)
        foundations.append(row)
    return {"items": [_serialize(f) for f in foundations[offset:offset+limit]], "total": len(foundations)}


@router.post("", status_code=201)
async def create_foundation(
    body: FoundationIn,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    foundation = Foundation(
        name=body.name,
        description=body.description,
        website=body.website,
        grant_type=body.grant_type,
        focus_areas=body.focus_areas,
        geographic_focus=body.geographic_focus,
        portal_type=body.portal_type,
        portal_url=body.portal_url,
        portal_key=body.portal_key,
        typical_amount_min=body.typical_amount_min,
        typical_amount_max=body.typical_amount_max,
        accepts_unsolicited=body.accepts_unsolicited,
        requires_loi=body.requires_loi,
        loi_deadline_days_before=body.loi_deadline_days_before,
        cycle=body.cycle,
        eligibility_notes=body.eligibility_notes,
        notes=body.notes,
        is_active=True,
    )
    db.add(foundation)
    await db.flush()

    for c in body.contacts:
        contact = FoundationContact(
            foundation_id=foundation.id,
            name=c.name,
            title=c.title,
            email=c.email,
            phone=c.phone,
            is_primary=c.is_primary,
            relationship_notes=c.relationship_notes,
        )
        db.add(contact)

    await db.commit()
    result = await db.execute(
        select(Foundation).options(selectinload(Foundation.contacts)).where(Foundation.id == foundation.id)
    )
    return _serialize(result.scalar_one())


@router.get("/{foundation_id}")
async def get_foundation(
    foundation_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(Foundation).options(selectinload(Foundation.contacts)).where(Foundation.id == foundation_id)
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Foundation not found")
    return _serialize(f)


@router.patch("/{foundation_id}")
async def update_foundation(
    foundation_id: int,
    body: FoundationUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(Foundation).options(selectinload(Foundation.contacts)).where(Foundation.id == foundation_id)
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Foundation not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(f, field, value)

    await db.commit()
    result2 = await db.execute(
        select(Foundation).options(selectinload(Foundation.contacts)).where(Foundation.id == foundation_id)
    )
    return _serialize(result2.scalar_one())


@router.delete("/{foundation_id}", status_code=204)
async def delete_foundation(
    foundation_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    f = await db.get(Foundation, foundation_id)
    if not f:
        raise HTTPException(status_code=404, detail="Foundation not found")
    await db.delete(f)
    await db.commit()


# ── Contacts ──────────────────────────────────────────────────────────────────

@router.post("/{foundation_id}/contacts", status_code=201)
async def add_contact(
    foundation_id: int,
    body: FoundationContactIn,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    f = await db.get(Foundation, foundation_id)
    if not f:
        raise HTTPException(status_code=404, detail="Foundation not found")

    contact = FoundationContact(
        foundation_id=foundation_id,
        name=body.name,
        title=body.title,
        email=body.email,
        phone=body.phone,
        is_primary=body.is_primary,
        relationship_notes=body.relationship_notes,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return {
        "id": contact.id,
        "foundation_id": contact.foundation_id,
        "name": contact.name,
        "title": contact.title,
        "email": contact.email,
        "phone": contact.phone,
        "is_primary": contact.is_primary,
        "relationship_notes": contact.relationship_notes,
    }


@router.delete("/{foundation_id}/contacts/{contact_id}", status_code=204)
async def remove_contact(
    foundation_id: int,
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    contact = await db.get(FoundationContact, contact_id)
    if not contact or contact.foundation_id != foundation_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()


# ── Foundation grants (link existing grants to a foundation) ──────────────────

@router.get("/{foundation_id}/grants")
async def list_foundation_grants(
    foundation_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    f = await db.get(Foundation, foundation_id)
    if not f:
        raise HTTPException(status_code=404, detail="Foundation not found")
    result = await db.execute(
        select(Grant).where(Grant.foundation_id == foundation_id).order_by(desc(Grant.created_at))
    )
    grants = result.scalars().all()
    return [
        {
            "id": g.id,
            "title": g.title,
            "amount": g.amount,
            "amount_max": g.amount_max,
            "deadline": g.deadline.isoformat() if g.deadline else None,
            "deadline_str": g.deadline_str,
            "status": g.status.value if hasattr(g.status, "value") else g.status,
            "source_url": g.source_url,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        }
        for g in grants
    ]


@router.post("/{foundation_id}/grants", status_code=201)
async def create_foundation_grant(
    foundation_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Create a new grant opportunity linked to this foundation."""
    f = await db.get(Foundation, foundation_id)
    if not f:
        raise HTTPException(status_code=404, detail="Foundation not found")

    grant = Grant(
        title=body.get("title", f.name + " Grant"),
        description=body.get("description"),
        funding_agency=f.name,
        amount=body.get("amount_min"),
        amount_max=body.get("amount_max"),
        deadline_str=body.get("deadline_str"),
        source_url=body.get("source_url") or f.website,
        grant_type="foundation",
        foundation_id=foundation_id,
        tags=body.get("tags", []),
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return {"id": grant.id, "title": grant.title, "foundation_id": foundation_id}
