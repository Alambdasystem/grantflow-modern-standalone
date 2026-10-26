"""Automation jobs router — launch, monitor, and control Playwright agents."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import AutomationJob, AutomationJobStatus, BrowserSession, GrantApplication
from schemas.schemas import AutomationJobCreate, AutomationJobOut, HumanApprovalAction
from auth.jwt_handler import get_current_user_token
from config import settings

router = APIRouter(prefix="/api/automation", tags=["automation"])

# In-memory live job progress (keyed by job_id)
_job_events: dict[int, list[dict]] = {}
_enqueue_lock = asyncio.Lock()


async def enforce_capacity(db, user_id):
    count = (await db.execute(select(func.count(AutomationJob.id)).where(
        AutomationJob.created_by_id == user_id,
        AutomationJob.status.in_(['queued','running','awaiting_approval'])))).scalar_one()
    if count >= settings.AUTOMATION_MAX_PENDING_PER_USER:
        raise HTTPException(429, 'Pending job limit reached. Wait for completion or cancel queued work before retrying.', headers={'Retry-After':'30'})


@router.get('/queue')
async def queue_status(db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    from services import job_queue
    rows = (await db.execute(select(AutomationJob.status, func.count(AutomationJob.id))
        .where(AutomationJob.created_by_id == token['local_user_id']).group_by(AutomationJob.status))).all()
    return {'counts':{status.value:count for status,count in rows},
        'concurrency':settings.AUTOMATION_CONCURRENCY, 'pending_limit':settings.AUTOMATION_MAX_PENDING_PER_USER,
        'worker_enabled':settings.AUTOMATION_WORKER_ENABLED, 'last_poll_at':job_queue.last_poll_at,
        'last_error_at':job_queue.last_error_at, 'mode':'single-service persistent dispatcher',
        'scope':'Current account; concurrency is shared across accounts'}


async def _run_automation_job(job_id: int):
    """Background task that imports and runs the Playwright orchestrator."""
    from db.database import AsyncSessionLocal
    from services.migration_safety import held
    async with AsyncSessionLocal() as safety_db:
        if await held(safety_db):
            await safety_db.execute(update(AutomationJob).where(AutomationJob.id==job_id).values(status=AutomationJobStatus.paused))
            await safety_db.commit()
            return
    try:
        # Lazy import to keep startup fast
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        sys.path.insert(0, os.path.join(backend_dir, "automation"))
        from orchestrator import run_job  # noqa
        await run_job(job_id, _job_events)
    except Exception as exc:
        from db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(update(AutomationJob).where(AutomationJob.id == job_id).values(
                status=AutomationJobStatus.failed, error_message='Automation failed; inspect server logs.', current_step='Failed'))
            await db.commit()
        _job_events.setdefault(job_id, []).append({
            "type": "error", "message": str(exc), "progress": 100
        })


@router.get("/jobs", response_model=list[AutomationJobOut])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(AutomationJob).order_by(AutomationJob.created_at.desc()).limit(100)
    )
    return result.scalars().all()


@router.post("/jobs", response_model=AutomationJobOut, status_code=201)
async def create_job(
    payload: AutomationJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    async with _enqueue_lock:
        if payload.job_type not in {'scrape', 'renew'}:
            raise HTTPException(422, 'This queue supports discovery and renewal drafts only; external submission requires a separate reviewed workflow.')
        if payload.application_id and await db.get(GrantApplication, payload.application_id) is None:
            raise HTTPException(404, 'Application not found')
        if payload.job_type == 'renew' and not payload.application_id:
            raise HTTPException(422, 'Renewal requires an application')
        if payload.job_type == 'renew':
            completed = (await db.execute(select(AutomationJob).where(
                AutomationJob.created_by_id == token['local_user_id'],
                AutomationJob.application_id == payload.application_id,
                AutomationJob.job_type == 'renew', AutomationJob.status == AutomationJobStatus.completed
            ).order_by(AutomationJob.id.desc()))).scalars().first()
            if completed and (completed.result or {}).get('renewal_application_id'):
                return completed
        query_text = str(payload.params.get('query', '')).strip()[:500]
        dedup = select(AutomationJob).where(
            AutomationJob.created_by_id == token['local_user_id'],
            AutomationJob.application_id == payload.application_id,
            AutomationJob.job_type == payload.job_type,
            AutomationJob.status.in_([AutomationJobStatus.queued, AutomationJobStatus.running, AutomationJobStatus.awaiting_approval]))
        if payload.job_type == 'scrape':
            dedup = dedup.where(AutomationJob.result['query'].as_string() == query_text)
        existing = (await db.execute(dedup)).scalars().first()
        if existing:
            return existing
        await enforce_capacity(db, token['local_user_id'])
        job = AutomationJob(
            application_id=payload.application_id,
            job_type=payload.job_type,
            portal_key=payload.portal_key,
            portal_url=payload.portal_url,
            status=AutomationJobStatus.queued,
            progress_pct=0,
            steps_log=[],
            screenshots=[],
            result={"managed_queue": True, "query": query_text},
            created_by_id=token["local_user_id"],
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        return job


@router.get("/jobs/{job_id}", response_model=AutomationJobOut)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(AutomationJob).where(AutomationJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/stream")
async def stream_job_events(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Server-Sent Events stream for live job progress."""
    if await db.get(AutomationJob, job_id) is None:
        raise HTTPException(status_code=404, detail='Job not found')
    async def event_gen():
        from db.database import AsyncSessionLocal
        previous = None
        while True:
            async with AsyncSessionLocal() as progress_db:
                row = await progress_db.get(AutomationJob, job_id)
                if row is None:
                    return
                evt = {'type': row.status.value, 'progress': row.progress_pct,
                       'message': row.current_step or row.status.value}
                encoded = json.dumps(evt)
                if encoded != previous:
                    yield f'data: {encoded}\n\n'
                    previous = encoded
                if row.status in {AutomationJobStatus.completed, AutomationJobStatus.failed, AutomationJobStatus.paused}:
                    return
            await asyncio.sleep(1)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/approve")
async def approve_job(
    job_id: int,
    payload: HumanApprovalAction,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(AutomationJob).where(AutomationJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if token.get("role") not in {"admin", "reviewer"}:
        raise HTTPException(403, "Reviewer approval required")
    if job.status != AutomationJobStatus.awaiting_approval:
        raise HTTPException(409, "Job is not awaiting approval")
    if payload.action == "approve":
        job.status = AutomationJobStatus.running
        job.requires_human = False
        _job_events.setdefault(job_id, []).append({"type": "approved", "message": "Human approved — resuming."})
    elif payload.action == "reject":
        job.status = AutomationJobStatus.failed
        _job_events.setdefault(job_id, []).append({"type": "rejected", "message": "Human rejected."})
    await db.commit()
    return {"ok": True, "action": payload.action}


@router.post("/jobs/{job_id}/run", status_code=202)
async def run_existing_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Re-trigger a queued (or failed) job so it actually runs."""
    result = await db.execute(select(AutomationJob).where(AutomationJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {AutomationJobStatus.failed, AutomationJobStatus.paused}:
        raise HTTPException(409, 'Only failed or paused jobs can be retried')
    if job.job_type not in {'scrape', 'renew'}:
        raise HTTPException(422, 'Use the specific reviewed portal workflow for this job')
    async with _enqueue_lock:
        await enforce_capacity(db, job.created_by_id)
        job.result = {**(job.result or {}), 'managed_queue': True}
        job.status = AutomationJobStatus.queued
        job.progress_pct = 0
        job.current_step = "Queued"
        job.error_message = None
        await db.commit()
    return {"ok": True, "job_id": job_id}


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(AutomationJob).where(AutomationJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {AutomationJobStatus.completed, AutomationJobStatus.failed}:
        raise HTTPException(409, 'Job is already finished')
    from services.job_queue import active
    task = active.get(job_id)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    job.status = AutomationJobStatus.paused
    job.current_step = 'Cancelled by user'
    job.error_message = "Cancelled by user"
    await db.commit()
    return {"ok": True}
