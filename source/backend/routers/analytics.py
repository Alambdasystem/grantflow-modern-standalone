"""Analytics & dashboard stats router."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import Grant, GrantStatus, GrantApplication, AutomationJob, ApplicationStatus, AutomationJobStatus
from schemas.schemas import DashboardStats
from auth.jwt_handler import get_current_user_token

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def calculate_success_rate(*, approved_count: int, rejected_count: int) -> float | None:
    decided_count = approved_count + rejected_count
    if decided_count <= 0:
        return None
    return round((approved_count / decided_count) * 100, 1)


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    total_grants = (await db.execute(select(func.count(Grant.id)))).scalar_one()
    # compare against the GrantStatus enum to ensure correct SQLAlchemy enum comparison
    active_grants = (await db.execute(
        select(func.count(Grant.id)).where(Grant.status == GrantStatus.active)
    )).scalar_one()
    total_apps = (await db.execute(select(func.count(GrantApplication.id)))).scalar_one()
    submitted = (await db.execute(
        select(func.count(GrantApplication.id)).where(
            GrantApplication.status == ApplicationStatus.submitted
        )
    )).scalar_one()
    approved = (await db.execute(
        select(func.count(GrantApplication.id)).where(
            GrantApplication.status == ApplicationStatus.approved
        )
    )).scalar_one()
    rejected = (await db.execute(
        select(func.count(GrantApplication.id)).where(
            GrantApplication.status == ApplicationStatus.rejected
        )
    )).scalar_one()
    renewals = (await db.execute(
        select(func.count(GrantApplication.id)).where(
            GrantApplication.status == ApplicationStatus.renewal_due
        )
    )).scalar_one()
    running_jobs = (await db.execute(
        select(func.count(AutomationJob.id)).where(
            AutomationJob.status == AutomationJobStatus.running
        )
    )).scalar_one()
    total_awarded_row = (await db.execute(
        select(func.coalesce(func.sum(GrantApplication.amount_awarded), 0.0)).where(
            GrantApplication.status == ApplicationStatus.approved
        )
    )).scalar_one()

    success_rate = calculate_success_rate(
        approved_count=approved,
        rejected_count=rejected,
    )

    return DashboardStats(
        total_grants=total_grants,
        active_grants=active_grants,
        total_applications=total_apps,
        submitted_applications=submitted,
        approved_applications=approved,
        pending_renewals=renewals,
        automation_jobs_running=running_jobs,
        total_awarded=float(total_awarded_row),
        success_rate=success_rate,
    )


@router.get("/grant-pipeline")
async def grant_pipeline(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(GrantApplication.status, func.count(GrantApplication.id).label("count"))
        .group_by(GrantApplication.status)
    )
    rows = result.all()
    return [{"status": r.status.value if hasattr(r.status, "value") else r.status, "count": r.count} for r in rows]
