"""Donor management and donation campaign endpoints."""
import os, sys, re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db, get_public_db
from models.models import Donor, DonationCampaign, Donation
from auth.jwt_handler import get_current_user_token, require_admin

router = APIRouter(prefix="/api/donors", tags=["donors"], dependencies=[Depends(require_admin)])
public_router = APIRouter(prefix="/api/give", tags=["give"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DonorIn(BaseModel):
    donor_type: str = "individual"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: str = "US"
    is_anonymous: bool = False
    tags: list[str] = []
    notes: Optional[str] = None


class CampaignIn(BaseModel):
    name: str
    description: Optional[str] = None
    slug: Optional[str] = None
    goal_amount: Optional[float] = None
    campaign_type: str = "general"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    is_public: bool = True
    thank_you_message: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    goal_amount: Optional[float] = None
    campaign_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    thank_you_message: Optional[str] = None


class DonationIn(BaseModel):
    donor_id: Optional[int] = None
    campaign_id: Optional[int] = None
    amount: float = Field(gt=0, allow_inf_nan=False)
    currency: str = "USD"
    donation_type: str = "cash"
    is_restricted: bool = False
    restriction_purpose: Optional[str] = None
    received_at: Optional[datetime] = None
    is_anonymous: bool = False
    notes: Optional[str] = None
    # Inline donor info for new donors submitted via public /give page
    donor_first_name: Optional[str] = None
    donor_last_name: Optional[str] = None
    donor_email: Optional[str] = None
    donor_phone: Optional[str] = None
    donor_type: str = "individual"
    donor_organization_name: Optional[str] = None


def _slug_from_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80]
    return base


def _serialize_donor(d: Donor) -> dict:
    display = ""
    if d.donor_type == "individual":
        parts = [d.first_name or "", d.last_name or ""]
        display = " ".join(p for p in parts if p) or d.email or "Anonymous"
    else:
        display = d.organization_name or d.email or "Unknown"
    return {
        "id": d.id,
        "donor_type": d.donor_type,
        "display_name": display,
        "first_name": d.first_name,
        "last_name": d.last_name,
        "organization_name": d.organization_name,
        "email": d.email,
        "phone": d.phone,
        "address": d.address,
        "city": d.city,
        "state": d.state,
        "zip_code": d.zip_code,
        "country": d.country,
        "is_anonymous": d.is_anonymous,
        "total_donated": d.total_donated or 0.0,
        "tags": d.tags or [],
        "notes": d.notes,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _serialize_campaign(c: DonationCampaign, donation_count: int = 0) -> dict:
    pct = 0.0
    if c.goal_amount and c.goal_amount > 0:
        pct = min(100.0, round((c.raised_amount or 0) / c.goal_amount * 100, 1))
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "slug": c.slug,
        "goal_amount": c.goal_amount,
        "raised_amount": c.raised_amount or 0.0,
        "progress_pct": pct,
        "campaign_type": c.campaign_type,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "is_active": c.is_active,
        "is_public": c.is_public,
        "thank_you_message": c.thank_you_message,
        "donation_count": donation_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_donation(d: Donation) -> dict:
    return {
        "id": d.id,
        "donor_id": d.donor_id,
        "campaign_id": d.campaign_id,
        "amount": d.amount,
        "currency": d.currency,
        "donation_type": d.donation_type,
        "is_restricted": d.is_restricted,
        "restriction_purpose": d.restriction_purpose,
        "received_at": d.received_at.isoformat() if d.received_at else None,
        "is_anonymous": d.is_anonymous,
        "acknowledgment_sent": d.acknowledgment_sent,
        "notes": d.notes,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ── Donor CRUD ────────────────────────────────────────────────────────────────

@router.get("")
async def list_donors(
    q: Optional[str] = Query(None),
    donor_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    stmt = select(Donor)
    if donor_type:
        stmt = stmt.where(Donor.donor_type == donor_type)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(Donor.first_name.ilike(like), Donor.last_name.ilike(like),
                Donor.organization_name.ilike(like), Donor.email.ilike(like))
        )
    stmt = stmt.order_by(desc(Donor.total_donated), desc(Donor.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    donors = result.scalars().all()

    total_result = await db.execute(select(func.count()).select_from(Donor))
    total = total_result.scalar() or 0

    total_raised_result = await db.execute(select(func.sum(Donor.total_donated)))
    total_raised = total_raised_result.scalar() or 0.0

    return {
        "items": [_serialize_donor(d) for d in donors],
        "total": total,
        "total_raised": total_raised,
    }


@router.post("", status_code=201)
async def create_donor(
    body: DonorIn,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    donor = Donor(**body.model_dump())
    db.add(donor)
    await db.commit()
    await db.refresh(donor)
    return _serialize_donor(donor)


@router.get("/{donor_id}")
async def get_donor(
    donor_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    donor = await db.get(Donor, donor_id)
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")

    donations_result = await db.execute(
        select(Donation).where(Donation.donor_id == donor_id).order_by(desc(Donation.received_at))
    )
    donations = donations_result.scalars().all()

    return {**_serialize_donor(donor), "donations": [_serialize_donation(d) for d in donations]}


@router.patch("/{donor_id}")
async def update_donor(
    donor_id: int,
    body: DonorIn,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    donor = await db.get(Donor, donor_id)
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(donor, field, value)
    await db.commit()
    await db.refresh(donor)
    return _serialize_donor(donor)


@router.delete("/{donor_id}", status_code=204)
async def delete_donor(
    donor_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    donor = await db.get(Donor, donor_id)
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    await db.delete(donor)
    await db.commit()


# ── Campaign CRUD ─────────────────────────────────────────────────────────────

@router.get("/campaigns/list")
async def list_campaigns(
    is_active: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    stmt = select(DonationCampaign)
    if is_active is not None:
        stmt = stmt.where(DonationCampaign.is_active == is_active)
    stmt = stmt.order_by(desc(DonationCampaign.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    campaigns = result.scalars().all()

    total_result = await db.execute(select(func.count()).select_from(DonationCampaign))
    total = total_result.scalar() or 0

    # Get donation counts per campaign
    counts_result = await db.execute(
        select(Donation.campaign_id, func.count(Donation.id)).group_by(Donation.campaign_id)
    )
    counts = {row[0]: row[1] for row in counts_result.fetchall()}

    return {
        "items": [_serialize_campaign(c, counts.get(c.id, 0)) for c in campaigns],
        "total": total,
    }


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignIn,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_token),
):
    slug = body.slug or _slug_from_name(body.name)

    # Ensure unique slug
    existing = await db.execute(select(DonationCampaign).where(DonationCampaign.slug == slug))
    if existing.scalar_one_or_none():
        import uuid
        slug = f"{slug}-{str(uuid.uuid4())[:6]}"

    campaign = DonationCampaign(
        name=body.name,
        description=body.description,
        slug=slug,
        goal_amount=body.goal_amount,
        raised_amount=0.0,
        campaign_type=body.campaign_type,
        start_date=body.start_date,
        end_date=body.end_date,
        is_active=body.is_active,
        is_public=body.is_public,
        thank_you_message=body.thank_you_message,
        created_by_id=current_user.get("id"),
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    campaign = await db.get(DonationCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    donations_result = await db.execute(
        select(Donation).where(Donation.campaign_id == campaign_id).order_by(desc(Donation.received_at))
    )
    donations = donations_result.scalars().all()
    count = len(donations)

    return {
        **_serialize_campaign(campaign, count),
        "donations": [_serialize_donation(d) for d in donations],
    }


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    campaign = await db.get(DonationCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(campaign, field, value)
    await db.commit()
    await db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    campaign = await db.get(DonationCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(campaign)
    await db.commit()


# ── Donations ─────────────────────────────────────────────────────────────────

@router.post("/donations", status_code=201)
async def record_donation(
    body: DonationIn,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    donor_id = body.donor_id

    # If no donor_id but inline donor info provided, find or create donor
    if not donor_id and body.donor_email:
        existing = await db.execute(
            select(Donor).where(Donor.email == body.donor_email).limit(1)
        )
        existing_donor = existing.scalar_one_or_none()
        if existing_donor:
            donor_id = existing_donor.id
        else:
            new_donor = Donor(
                donor_type=body.donor_type,
                first_name=body.donor_first_name,
                last_name=body.donor_last_name,
                organization_name=body.donor_organization_name,
                email=body.donor_email,
                phone=body.donor_phone,
                is_anonymous=body.is_anonymous,
                total_donated=0.0,
            )
            db.add(new_donor)
            await db.flush()
            donor_id = new_donor.id

    donation = Donation(
        donor_id=donor_id,
        campaign_id=body.campaign_id,
        amount=body.amount,
        currency=body.currency,
        donation_type=body.donation_type,
        is_restricted=body.is_restricted,
        restriction_purpose=body.restriction_purpose,
        received_at=body.received_at or datetime.now(timezone.utc),
        is_anonymous=body.is_anonymous,
        notes=body.notes,
    )
    db.add(donation)

    # Update donor total_donated
    if donor_id:
        donor = await db.get(Donor, donor_id)
        if donor:
            donor.total_donated = (donor.total_donated or 0.0) + body.amount

    # Update campaign raised_amount
    if body.campaign_id:
        campaign = await db.get(DonationCampaign, body.campaign_id)
        if campaign:
            campaign.raised_amount = (campaign.raised_amount or 0.0) + body.amount

    await db.commit()
    await db.refresh(donation)
    return _serialize_donation(donation)


@router.patch("/donations/{donation_id}/acknowledge")
async def mark_acknowledged(
    donation_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    donation = await db.get(Donation, donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    donation.acknowledgment_sent = True
    donation.acknowledgment_sent_at = datetime.now(timezone.utc)
    await db.commit()
    return {"acknowledged": True, "donation_id": donation_id}


# ── Public campaign endpoint (no auth) ────────────────────────────────────────

@public_router.get("/{slug}")
async def get_public_campaign(
    slug: str,
    db: AsyncSession = Depends(get_public_db),
):
    result = await db.execute(
        select(DonationCampaign).where(
            DonationCampaign.slug == slug,
            DonationCampaign.is_public == True,
            DonationCampaign.is_active == True,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not active")

    count_result = await db.execute(
        select(func.count(Donation.id)).where(Donation.campaign_id == campaign.id)
    )
    count = count_result.scalar() or 0

    return _serialize_campaign(campaign, count)


@public_router.post("/{slug}/donate", status_code=201)
async def public_donate(
    slug: str,
    body: DonationIn,
    db: AsyncSession = Depends(get_public_db),
):
    """Accept a donation submission from the public give page."""
    result = await db.execute(
        select(DonationCampaign).where(
            DonationCampaign.slug == slug,
            DonationCampaign.is_public == True,
            DonationCampaign.is_active == True,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not active")

    body.campaign_id = campaign.id

    donor_id = None
    if body.donor_email:
        existing = await db.execute(
            select(Donor).where(Donor.email == body.donor_email).limit(1)
        )
        existing_donor = existing.scalar_one_or_none()
        if existing_donor:
            donor_id = existing_donor.id
        else:
            new_donor = Donor(
                donor_type=body.donor_type,
                first_name=body.donor_first_name,
                last_name=body.donor_last_name,
                organization_name=body.donor_organization_name,
                email=body.donor_email,
                phone=body.donor_phone,
                is_anonymous=body.is_anonymous,
                total_donated=0.0,
            )
            db.add(new_donor)
            await db.flush()
            donor_id = new_donor.id

    donation = Donation(
        donor_id=donor_id,
        campaign_id=campaign.id,
        amount=body.amount,
        currency=body.currency,
        donation_type=body.donation_type,
        is_restricted=body.is_restricted,
        restriction_purpose=body.restriction_purpose,
        received_at=body.received_at or datetime.now(timezone.utc),
        is_anonymous=body.is_anonymous,
        notes=body.notes,
    )
    db.add(donation)

    if donor_id:
        donor = await db.get(Donor, donor_id)
        if donor:
            donor.total_donated = (donor.total_donated or 0.0) + body.amount

    campaign.raised_amount = (campaign.raised_amount or 0.0) + body.amount

    await db.commit()

    return {
        "success": True,
        "thank_you_message": campaign.thank_you_message or "Thank you for your generous contribution!",
        "amount": body.amount,
        "campaign": campaign.name,
    }
