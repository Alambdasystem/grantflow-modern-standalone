"""Grant planning persistence + promotion into application drafting."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth.jwt_handler import get_current_user_token
from db.database import get_db
from models.models import (
    ApplicationStatus,
    Grant,
    GrantApplication,
    GrantPlanningProfile,
    User,
    Workflow,
    WorkflowStatus,
)
from schemas.schemas import (
    ApplicationOut,
    GrantPlanningProfileOut,
    GrantPlanningProfileUpsert,
    GrantPlanningPromoteRequest,
    GrantPlanningPromoteResponse,
)

router = APIRouter(prefix="/api/grant-planning", tags=["grant-planning"])

DEFAULT_STAGES = [
    "Organization Setup",
    "Document Upload",
    "Grant Matching",
    "Application Draft",
    "Review & Collaboration",
    "Submission",
    "Reporting & Compliance",
]


def _budget_total(lines: list[dict]) -> float:
    total = 0.0
    for line in lines:
        quantity = float(line.get("quantity") or 0)
        unit_cost = float(line.get("unit_cost") or 0)
        total += quantity * unit_cost
    return total


def _serialize_profile(profile: GrantPlanningProfile) -> GrantPlanningProfileOut:
    return GrantPlanningProfileOut(
        id=profile.id,
        grant_id=profile.grant_id,
        application_id=profile.application_id,
        organization_id=profile.organization_id,
        created_by_id=profile.created_by_id,
        strategic_fit=profile.strategic_fit_data or {},
        partners=profile.collaboration_data or [],
        budget_lines=profile.budget_data or [],
        compliance_items=profile.compliance_data or [],
        summary=profile.summary_data or {},
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _current_user(db: AsyncSession, token: dict) -> User | None:
    result = await db.execute(select(User).where(User.identity_id == token["identity_id"]).limit(1))
    return result.scalar_one_or_none()


async def _find_profile(
    db: AsyncSession,
    grant_id: int,
    application_id: int | None = None,
) -> GrantPlanningProfile | None:
    query = select(GrantPlanningProfile).where(GrantPlanningProfile.grant_id == grant_id)
    if application_id is None:
        query = query.where(GrantPlanningProfile.application_id.is_(None))
    else:
        query = query.where(GrantPlanningProfile.application_id == application_id)
    query = query.order_by(GrantPlanningProfile.updated_at.desc().nullslast(), GrantPlanningProfile.id.desc())
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none()


async def _upsert_profile(
    payload: GrantPlanningProfileUpsert,
    db: AsyncSession,
    token: dict,
) -> GrantPlanningProfile:
    grant = await db.get(Grant, payload.grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    user = await _current_user(db, token)
    profile = await _find_profile(db, payload.grant_id, payload.application_id)
    if not profile:
        profile = GrantPlanningProfile(
            grant_id=payload.grant_id,
            application_id=payload.application_id,
            organization_id=user.organization_id if user else None,
            created_by_id=user.id if user else None,
        )
        db.add(profile)

    strategic_fit = payload.strategic_fit.model_dump(mode="json")
    budget_lines = [line.model_dump(mode="json") for line in payload.budget_lines]
    summary = {
        **payload.summary,
        "budget_total": _budget_total(budget_lines),
        "partner_count": len(payload.partners),
        "compliance_ready_count": len([item for item in payload.compliance_items if item.status == "ready"]),
        "strategic_fit_score": strategic_fit.get("score"),
    }

    profile.strategic_fit_data = strategic_fit
    profile.collaboration_data = [item.model_dump(mode="json") for item in payload.partners]
    profile.budget_data = budget_lines
    profile.compliance_data = [item.model_dump(mode="json") for item in payload.compliance_items]
    profile.summary_data = summary
    await db.flush()
    return profile


def _proposal_text(grant: Grant, payload: GrantPlanningPromoteRequest) -> str:
    strategic_fit = payload.strategic_fit
    high_scores = [priority.label for priority in strategic_fit.priorities if priority.score >= 4]
    concerns = [priority.label for priority in strategic_fit.priorities if priority.score <= 2]
    partners = ", ".join(partner.name for partner in payload.partners[:4]) or "Partnership slate pending"
    compliance = ", ".join(item.title for item in payload.compliance_items[:4]) or "Compliance checklist pending"
    return (
        f"Strategic fit for {grant.title}:\n"
        f"North star: {strategic_fit.north_star or 'No north star recorded.'}\n\n"
        f"Strong alignment areas: {', '.join(high_scores) if high_scores else 'None yet identified.'}\n"
        f"Primary diligence items: {', '.join(concerns) if concerns else 'No critical blockers logged.'}\n\n"
        f"Priority partners: {partners}.\n"
        f"Compliance focus: {compliance}."
    )


def _budget_narrative(payload: GrantPlanningPromoteRequest) -> str:
    lines = []
    for item in payload.budget_lines:
        lines.append(
            f"{item.item}: {item.quantity:g} x ${item.unit_cost:,.2f} in {item.category.lower()}"
        )
    if not lines:
        return "Budget lines not yet defined."
    return "; ".join(lines)


def _notes_text(payload: GrantPlanningPromoteRequest) -> str:
    partner_count = len(payload.partners)
    ready_count = len([item for item in payload.compliance_items if item.status == "ready"])
    return (
        f"Promoted from Gap Solutions workspace. Strategic fit score: {payload.strategic_fit.score or 0}. "
        f"Partners tracked: {partner_count}. Compliance ready items: {ready_count}."
    )


async def _bootstrap_workflows(db: AsyncSession, application_id: int):
    for idx, stage in enumerate(DEFAULT_STAGES):
        db.add(
            Workflow(
                application_id=application_id,
                stage=stage,
                status=WorkflowStatus.pending,
                order_index=idx,
            )
        )


@router.get("", response_model=GrantPlanningProfileOut)
async def get_profile(
    grant_id: int = Query(...),
    application_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    profile = await _find_profile(db, grant_id, application_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Planning profile not found")
    return _serialize_profile(profile)


@router.post("", response_model=GrantPlanningProfileOut)
async def save_profile(
    payload: GrantPlanningProfileUpsert,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    profile = await _upsert_profile(payload, db, token)
    await db.commit()
    await db.refresh(profile)
    return _serialize_profile(profile)


@router.post("/promote", response_model=GrantPlanningPromoteResponse)
async def promote_to_application(
    payload: GrantPlanningPromoteRequest,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    grant = await db.get(Grant, payload.grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    user = await _current_user(db, token)
    profile = await _upsert_profile(payload, db, token)
    budget_total = _budget_total(profile.budget_data or [])

    application = None
    if profile.application_id:
        application = await db.get(GrantApplication, profile.application_id)

    if not application:
        application = GrantApplication(
            grant_id=grant.id,
            organization_id=user.organization_id if user else None,
            applicant_id=user.id if user else None,
            title=payload.application_title or f"{grant.title} Strategy Draft",
            status=ApplicationStatus.draft,
        )
        db.add(application)
        await db.flush()
        await _bootstrap_workflows(db, application.id)

    application.title = payload.application_title or application.title or grant.title
    application.proposal_text = _proposal_text(grant, payload)
    application.budget_narrative = _budget_narrative(payload)
    application.amount_requested = budget_total or grant.amount
    application.notes = _notes_text(payload)
    application.form_data = {
        **(application.form_data or {}),
        "grant_planning_profile_id": profile.id,
        "grant_planning": {
            "strategic_fit": profile.strategic_fit_data or {},
            "partners": profile.collaboration_data or [],
            "budget_lines": profile.budget_data or [],
            "compliance_items": profile.compliance_data or [],
            "summary": profile.summary_data or {},
        },
    }

    profile.application_id = application.id

    await db.commit()
    await db.refresh(application)
    await db.refresh(profile)
    return GrantPlanningPromoteResponse(
        application=ApplicationOut.model_validate(application),
        planning_profile=_serialize_profile(profile),
    )