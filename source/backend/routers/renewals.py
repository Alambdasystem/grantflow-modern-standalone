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
import asyncio
from fastapi import HTTPException

_draft_lock=asyncio.Lock()

router = APIRouter(prefix="/api/renewals", tags=["renewals"])


@router.post('/{app_id}/draft',response_model=ApplicationOut)
async def manual_renewal_draft(app_id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    """Internal preparation only. Does not enqueue automation or contact a funder."""
    if token.get('role')=='viewer':raise HTTPException(403,'Read-only account')
    async with _draft_lock:
        parent=await db.get(GrantApplication,app_id)
        if not parent:raise HTTPException(404,'Application not found')
        if parent.status not in {ApplicationStatus.approved,ApplicationStatus.renewal_due}:
            raise HTTPException(409,'Renewal preparation requires an approved or renewal-due application')
        existing=(await db.execute(select(GrantApplication).where(GrantApplication.parent_application_id==parent.id,
            GrantApplication.status.in_([ApplicationStatus.draft,ApplicationStatus.in_review])))).scalars().first()
        if existing:return existing
        from routers.applications import configured_stages
        from models.models import Workflow, WorkflowStatus, OrganizationRecord
        config=(await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id==parent.organization_id,OrganizationRecord.kind=='configuration'))).scalars().first()
        child=GrantApplication(grant_id=parent.grant_id,organization_id=parent.organization_id,applicant_id=token['local_user_id'],
            title=('Renewal draft: '+(parent.title or str(parent.id)))[:255],amount_requested=parent.amount_requested,
            parent_application_id=parent.id,status=ApplicationStatus.draft,
            notes='Internal renewal preparation. Confirm a new funding round, eligibility, requirements and budget; no external submission has occurred.')
        db.add(child);await db.flush()
        for index,stage in enumerate(configured_stages(config.data if config else None)):
            db.add(Workflow(application_id=child.id,stage=stage,status=WorkflowStatus.pending,order_index=index))
        await db.commit();await db.refresh(child)
        return child


@router.post('/{app_id}/complete')
async def complete_renewal_preparation(app_id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    """Record internal preparation completion after review, never an award/submission."""
    if token.get('role') not in {'admin','reviewer'}:raise HTTPException(403,'Reviewer or administrator required')
    parent=await db.get(GrantApplication,app_id)
    if not parent:raise HTTPException(404,'Application not found')
    children=(await db.execute(select(GrantApplication).where(GrantApplication.parent_application_id==app_id).order_by(GrantApplication.id.desc()))).scalars().all()
    from services.application_readiness import latest_acceptance
    accepted=None
    for child in children:
        _,valid=await latest_acceptance(db,child)
        if valid:accepted=child;break
    if not accepted:raise HTTPException(409,'A current renewal draft must be accepted before preparation is completed')
    parent.form_data={**(parent.form_data or {}),'renewal_preparation':{'completed_at':datetime.now(timezone.utc).isoformat(),'draft_id':accepted.id,'reviewer_id':token['local_user_id'],'meaning':'Internal preparation complete; not submitted or awarded'}}
    parent.renewal_due_date=None
    from models.models import AuditLog
    db.add(AuditLog(user_id=token['local_user_id'],action='renewal_preparation_completed',resource_type='application',resource_id=parent.id,details={'draft_id':accepted.id}))
    await db.commit()
    return {'completed':True,'draft_id':accepted.id,'message':'Internal renewal preparation completed. Nothing was submitted.'}


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
