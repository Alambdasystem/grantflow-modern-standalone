"""Grant applications CRUD + AI proposal generation."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import List
import sys, os, aiofiles, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import GrantApplication, Grant, ApplicationStatus, Document, Workflow, WorkflowStatus, User, Organization, Review, AuditLog, OrganizationRecord
from schemas.schemas import ApplicationCreate, ApplicationUpdate, ApplicationOut, WorkflowStageUpdate, WorkflowStageOut
from auth.jwt_handler import get_current_user_token
from config import settings

router = APIRouter(prefix="/api/applications", tags=["applications"])

DEFAULT_STAGES = [
    "Organization Setup",
    "Document Upload",
    "Grant Matching",
    "Application Draft",
    "Review & Collaboration",
    "Submission",
    "Reporting & Compliance",
]


def configured_stages(config):
    extras = [s.strip()[:100] for s in (config.get('stages', '') if config else '').splitlines() if s.strip()]
    return list(dict.fromkeys(DEFAULT_STAGES[:4] + extras[:20] + DEFAULT_STAGES[4:]))


async def require_current_acceptance(db, app):
    from services.application_sources import require_reviewed_workflow
    await require_reviewed_workflow(db,app)
    from services.application_readiness import latest_acceptance
    _,valid=await latest_acceptance(db,app)
    if not valid:
        raise HTTPException(409, 'A reviewer must accept the current draft before review or submission can be completed')


@router.get("/", response_model=list[ApplicationOut])
async def list_applications(
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    q = select(GrantApplication).order_by(GrantApplication.updated_at.desc().nullslast())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=ApplicationOut, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    grant = await db.get(Grant, payload.grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    user_result = await db.execute(select(User).where(User.identity_id == token["identity_id"]).limit(1))
    user = user_result.scalar_one_or_none()

    app = GrantApplication(
        grant_id=payload.grant_id,
        organization_id=payload.organization_id or (user.organization_id if user else None),
        applicant_id=user.id if user else None,
        title=payload.title or grant.title,
        proposal_text=payload.proposal_text,
        budget_narrative=payload.budget_narrative,
        amount_requested=payload.amount_requested if payload.amount_requested is not None else grant.amount,
        form_data=payload.form_data,
        notes=payload.notes,
        status=ApplicationStatus.draft,
    )
    from services.candidate_quality import require_valid_content
    await require_valid_content(db,app,(app.proposal_text or '')+'\n'+(app.budget_narrative or ''))
    db.add(app)
    await db.flush()

    # Extend the workflow while retaining review/submission/reporting gates.
    config = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id == app.organization_id,
              OrganizationRecord.kind == 'configuration').order_by(OrganizationRecord.id.desc()))).scalars().first()
    stages = configured_stages(config.data if config else {})
    for idx, stage in enumerate(stages):
        db.add(Workflow(
            application_id=app.id,
            stage=stage,
            status=WorkflowStatus.pending,
            order_index=idx,
        ))

    await db.commit()
    await db.refresh(app)
    return app


class BulkLinkOrgPayload(BaseModel):
    org_id: int
    application_ids: List[int]


@router.post("/bulk-link-org")
async def bulk_link_org(
    payload: BulkLinkOrgPayload,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    """Set organization_id on a batch of applications at once."""
    if token.get('role')!='admin':
        raise HTTPException(403,'Administrator required to reassign application organizations')
    org = await db.get(Organization, payload.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(GrantApplication).where(GrantApplication.id.in_(payload.application_ids))
    )
    apps = result.scalars().all()
    for app in apps:
        app.organization_id = payload.org_id

    await db.commit()
    return {"updated": len(apps), "org_id": payload.org_id, "application_ids": [a.id for a in apps]}


@router.get("/{app_id}", response_model=ApplicationOut)
async def get_application(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(GrantApplication).where(GrantApplication.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_id}", response_model=ApplicationOut)
async def update_application(
    app_id: int,
    payload: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(GrantApplication).where(GrantApplication.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    changes = payload.model_dump(exclude_unset=True)
    if any(key in changes for key in ('proposal_text','budget_narrative','amount_requested')):
        from services.candidate_quality import context_for
        from services.draft_validation import draft_issues
        context=await context_for(db,app)
        context['application']['amount_requested']=changes.get('amount_requested',app.amount_requested)
        issues=draft_issues((changes.get('proposal_text',app.proposal_text) or '')+'\n'+(changes.get('budget_narrative',app.budget_narrative) or ''),context,'proposal')
        if issues:raise HTTPException(422,'Saved draft validation failed; reconcile figures or use information-needed placeholders. '+' '.join(issues))
    source_draft_id=changes.pop('source_draft_id',None)
    if 'amount_awarded' in changes and token.get('role') not in {'admin','reviewer'}:
        raise HTTPException(403,'Reviewer or administrator required to record award amounts')
    if source_draft_id:
        candidate=await db.get(OrganizationRecord,source_draft_id)
        if not candidate or candidate.kind!='draft' or candidate.organization_id!=app.organization_id or candidate.data.get('application_id')!=app.id:
            raise HTTPException(404,'Source draft not found for this application')
        if candidate.data.get('source_deleted'): raise HTTPException(409,'Source draft evidence was deleted. Regenerate and review.')
        field='budget_narrative' if candidate.data.get('category')=='budget' else 'proposal_text'
        if field not in changes: raise HTTPException(422,'Save the corresponding draft text with its source reference')
        from models.models import DocumentUse
        from services.document_ingestion import record_use
        ids=(await db.execute(select(DocumentUse.ingestion_id).where(DocumentUse.organization_id==app.organization_id,
            DocumentUse.target_type=='record',DocumentUse.target_id==candidate.id))).scalars().all()
        await record_use(db,ids,app.organization_id,'application',app.id,field)
    if changes.get('status') in {'approved', 'rejected'} and token.get('role') not in {'admin', 'reviewer'}:
        raise HTTPException(403, 'Reviewer or administrator required to record award decisions')
    if changes.get('status') == 'submitted':
        await require_current_acceptance(db, app)
        if any(field in changes for field in ('proposal_text','budget_narrative','amount_requested','form_data')):
            raise HTTPException(409, 'Save draft changes separately and request a fresh review')
    for field, value in changes.items():
        if field == "status" and value:
            setattr(app, field, ApplicationStatus(value))
        else:
            setattr(app, field, value)

    await db.commit()
    await db.refresh(app)
    return app


class AcceptanceInput(BaseModel):
    decision: str
    feedback: str
    revision: str|None=None


@router.get('/{app_id}/readiness')
async def application_readiness(app_id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app=await db.get(GrantApplication,app_id)
    if not app: raise HTTPException(404,'Application not found')
    from services.application_readiness import readiness
    return await readiness(db,app)


@router.get('/{app_id}/reviews')
async def reviews(app_id: int, db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    if not await db.get(GrantApplication, app_id):
        raise HTTPException(404, 'Application not found')
    rows = (await db.execute(select(Review).where(Review.application_id == app_id).order_by(Review.id.desc()))).scalars().all()
    return [{'id':r.id,'status':r.status,'feedback':r.feedback,'reviewer_id':r.reviewer_id,'created_at':r.created_at} for r in rows]


@router.post('/{app_id}/reviews', status_code=201)
async def accept_draft(app_id: int, payload: AcceptanceInput, db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    if token.get('role') not in {'admin', 'reviewer'}:
        raise HTTPException(403, 'Reviewer or administrator required')
    app = await db.get(GrantApplication, app_id)
    if not app:
        raise HTTPException(404, 'Application not found')
    config = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id == app.organization_id,
              OrganizationRecord.kind == 'configuration').order_by(OrganizationRecord.id.desc()))).scalars().first()
    if config and config.data.get('approval_role') == 'admin' and token.get('role') != 'admin':
        raise HTTPException(403, 'This organization requires administrator acceptance')
    if payload.decision not in {'accepted', 'changes_requested'} or not payload.feedback.strip() or len(payload.feedback)>10000:
        raise HTTPException(422, 'Choose accepted or changes_requested and enter review evidence')
    if payload.decision == 'accepted' and not (app.proposal_text or '').strip():
        raise HTTPException(422, 'Cannot accept an empty draft')
    if payload.decision=='accepted':
        from services.candidate_quality import require_valid_content
        await require_valid_content(db,app,(app.proposal_text or '')+'\n'+(app.budget_narrative or ''))
        from services.application_sources import require_reviewed_workflow
        await require_reviewed_workflow(db,app)
    import hashlib
    from services.application_readiness import draft_revision
    revision=draft_revision(app)
    if payload.revision is not None and payload.revision!=revision:
        raise HTTPException(409,'Application changed. Reload and review the saved application again.')
    digest = hashlib.sha256(((app.proposal_text or '')+'\n'+(app.budget_narrative or '')).encode()).hexdigest()
    review=Review(application_id=app_id,reviewer_id=token['local_user_id'],status=payload.decision,
                  feedback=payload.feedback,criteria={'draft_sha256':digest,'application_revision':revision})
    db.add(review)
    db.add(AuditLog(user_id=token['local_user_id'],action='draft_review',resource_type='application',resource_id=app_id,details={'decision':payload.decision,'draft_sha256':digest,'application_revision':revision}))
    await db.commit()
    return {'id':review.id,'status':review.status}


@router.get("/{app_id}/documents")
async def list_documents(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(Document)
        .where(Document.application_id == app_id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "original_filename": d.original_filename,
            "document_type": d.document_type,
            "file_size": d.file_size,
            "content_type": d.content_type,
            "text_extracted": bool(d.extracted_text),
            "text_length": len(d.extracted_text or ""),
            "ai_summary": d.ai_summary,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.post("/{app_id}/documents")
async def upload_document(
    app_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("general"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    from routers.ingestion import upload
    category = document_type if document_type in ('financials','mission','priorities','successful_grants','audits','award_history') else 'general'
    return await upload(file=file,category=category,application_id=app_id,grant_id=None,db=db,token=_)


@router.get("/{app_id}/workflow", response_model=list[WorkflowStageOut])
async def get_workflow(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(Workflow)
        .where(Workflow.application_id == app_id)
        .order_by(Workflow.order_index)
    )
    stages = result.scalars().all()
    return [
        WorkflowStageOut(
            id=s.id,
            application_id=s.application_id,
            stage=s.stage,
            status=s.status.value,
            order_index=s.order_index,
            notes=s.notes,
        )
        for s in stages
    ]


@router.patch("/{app_id}/workflow/{stage_id}", response_model=WorkflowStageOut)
async def update_workflow_stage(
    app_id: int,
    stage_id: int,
    payload: WorkflowStageUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == stage_id, Workflow.application_id == app_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Workflow stage not found")

    if payload.status == 'completed' and stage.stage in {'Review & Collaboration','Submission'}:
        app = await db.get(GrantApplication, app_id)
        if not app:
            raise HTTPException(404, 'Application not found')
        await require_current_acceptance(db, app)

    try:
        stage.status = WorkflowStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status '{payload.status}'. Must be: pending, active, completed, blocked")

    if payload.notes is not None:
        stage.notes = payload.notes

    if payload.status == "completed" and not stage.completed_at:
        stage.completed_at = datetime.now(timezone.utc)
    elif payload.status != "completed":
        stage.completed_at = None

    await db.commit()
    await db.refresh(stage)
    return WorkflowStageOut(
        id=stage.id,
        application_id=stage.application_id,
        stage=stage.stage,
        status=stage.status.value,
        order_index=stage.order_index,
        notes=stage.notes,
    )


@router.post("/{app_id}/workflow/advance", response_model=list[WorkflowStageOut])
async def advance_workflow(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Mark the current active stage completed and activate the next pending stage."""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.application_id == app_id)
        .order_by(Workflow.order_index)
    )
    stages = result.scalars().all()
    if not stages:
        raise HTTPException(status_code=404, detail="No workflow stages found for this application")

    # Find current active stage
    active = next((s for s in stages if s.status == WorkflowStatus.active), None)
    # If nothing active yet, activate the first pending stage
    if not active:
        first_pending = next((s for s in stages if s.status == WorkflowStatus.pending), None)
        if first_pending:
            first_pending.status = WorkflowStatus.active
        await db.commit()
        for s in stages:
            await db.refresh(s)
        return [WorkflowStageOut(id=s.id, application_id=s.application_id, stage=s.stage,
                                  status=s.status.value, order_index=s.order_index, notes=s.notes) for s in stages]

    # Complete the active stage
    if active.stage in {'Review & Collaboration','Submission'}:
        app = await db.get(GrantApplication, app_id)
        if not app:
            raise HTTPException(404, 'Application not found')
        await require_current_acceptance(db, app)
    active.status = WorkflowStatus.completed
    active.completed_at = datetime.now(timezone.utc)

    # Activate the next pending stage
    next_stage = next(
        (s for s in stages if s.order_index > active.order_index and s.status == WorkflowStatus.pending),
        None,
    )
    if next_stage:
        next_stage.status = WorkflowStatus.active

    await db.commit()
    for s in stages:
        await db.refresh(s)
    return [WorkflowStageOut(id=s.id, application_id=s.application_id, stage=s.stage,
                              status=s.status.value, order_index=s.order_index, notes=s.notes) for s in stages]
