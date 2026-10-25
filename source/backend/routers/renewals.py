"""Renewals router — track renewal due dates, auto-renew via automation."""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "automation"))

from db.database import get_db
from models.models import GrantApplication, ApplicationStatus, AutomationJob, AutomationJobStatus
from schemas.schemas import ApplicationOut
from auth.jwt_handler import get_current_user_token

router = APIRouter(prefix="/api/renewals", tags=["renewals"])


@router.get("/due", response_model=list[ApplicationOut])
async def renewals_due(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=90)
    result = await db.execute(
        select(GrantApplication).where(
            GrantApplication.renewal_due_date <= soon,
            GrantApplication.status.in_([
                ApplicationStatus.approved,
                ApplicationStatus.renewal_due,
            ]),
        ).order_by(GrantApplication.renewal_due_date.asc())
    )
    return result.scalars().all()


@router.post("/{app_id}/auto-renew", status_code=202)
async def trigger_auto_renew(
    app_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    app = await db.get(GrantApplication, app_id)
    if not app:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Application not found")

    from routers.automation import create_job
    from schemas.schemas import AutomationJobCreate
    job = await create_job(AutomationJobCreate(application_id=app_id, job_type='renew'), background_tasks, db, token)
    return {"ok": True, "job_id": job.id, "message": "Renewal draft queued; human review is required"}
