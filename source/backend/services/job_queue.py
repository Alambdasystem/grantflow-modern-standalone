"""Persistent single-service dispatcher. Interrupted jobs require an explicit retry."""
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from db.database import AsyncSessionLocal
from models.models import AutomationJob, AutomationJobStatus as Status, OrganizationRecord, GrantApplication
from config import settings

active: dict[int, asyncio.Task] = {}
last_poll_at = None
last_error_at = None


async def schedule_renewals():
    """Opt-in organization policy creates draft jobs only, never submissions."""
    from routers.automation import _enqueue_lock, enforce_capacity
    from fastapi import HTTPException
    async with _enqueue_lock:
        async with AsyncSessionLocal() as db:
            from services.migration_safety import held
            if await held(db): return
            policies = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.kind == 'configuration'))).scalars().all()
            for policy in policies:
                if not policy.data.get('auto_renew'):
                    continue
                due = datetime.now(timezone.utc) + timedelta(days=policy.data.get('renewal_lead_days',30))
                apps = (await db.execute(select(GrantApplication).where(GrantApplication.organization_id == policy.organization_id,
                    GrantApplication.status.in_(['approved','renewal_due']),GrantApplication.renewal_due_date <= due))).scalars().all()
                for app in apps:
                    existing = (await db.execute(select(AutomationJob.id).where(AutomationJob.application_id == app.id,
                        AutomationJob.job_type == 'renew'))).scalars().first()
                    if existing:
                        continue  # failures require review/retry; never duplicate or silently re-run
                    try:
                        await enforce_capacity(db, app.applicant_id)
                    except HTTPException as exc:
                        if exc.status_code == 429:
                            continue  # try on the next scheduling pass after capacity clears
                        raise
                    db.add(AutomationJob(application_id=app.id,created_by_id=app.applicant_id,
                        job_type='renew',status=Status.queued,progress_pct=0,steps_log=[],screenshots=[],
                        result={'managed_queue':True,'scheduled_by_policy':policy.id,'policy_revision':policy.revision}))
                    await db.flush()
            await db.commit()



async def recover():
    async with AsyncSessionLocal() as db:
        from services.migration_safety import held
        if await held(db): return
        await db.execute(update(AutomationJob).where(AutomationJob.status == Status.running,
            AutomationJob.result['lease_token'].as_string().is_(None), AutomationJob.result["managed_queue"].as_boolean() == True).values(
            status=Status.paused, error_message='Interrupted by service restart. Review before retrying.',
            current_step='Interrupted; retry required'))
        await db.commit()
        from models.models import IngestionDocument
        rows = (await db.execute(select(AutomationJob).where(AutomationJob.job_type=='ingest',
            AutomationJob.status==Status.paused, AutomationJob.error_message=='Interrupted by service restart. Review before retrying.'))).scalars().all()
        for job in rows:
            item=await db.get(IngestionDocument,job.result.get('ingestion_id'))
            if item and item.current and item.status!='deleted':
                job.status=Status.queued; item.status='queued'
                job.error_message=None; job.current_step='Resuming idempotent ingestion after restart'
        await db.commit()


async def run(job_id):
    from routers.automation import _run_automation_job
    try:
        async with AsyncSessionLocal() as db:
            job=await db.get(AutomationJob,job_id)
            ingestion=job.job_type=='ingest'
        if ingestion:
            from services.document_ingestion import process
            await process(job_id)
        else:
            await _run_automation_job(job_id)
    finally:
        active.pop(job_id, None)


async def worker():
    global last_poll_at, last_error_at
    last_schedule = 0.0
    while True:
        try:
            now = asyncio.get_running_loop().time()
            from routers.ingestion_workers import recover_expired
            await recover_expired()
            if now-last_schedule >= 60:
                await schedule_renewals()
                from services.document_ingestion import schedule
                last_schedule = now
                try:
                    async with AsyncSessionLocal() as safety_db:
                        from services.migration_safety import held
                        if not await held(safety_db): await schedule()
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Document source scheduling failed; queued work continues')
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(AutomationJob).where(
                    AutomationJob.status == Status.queued,
                    AutomationJob.job_type.in_(['scrape', 'renew', 'ingest'] if settings.INGESTION_LOCAL_WORKER_ENABLED else ['scrape', 'renew']),
                    AutomationJob.result['managed_queue'].as_boolean() == True).order_by(AutomationJob.id).limit(20))).scalars().all()
                for row in rows:
                    from services.migration_safety import held
                    if row.job_type!='ingest' and await held(db): continue
                    if len(active) >= settings.AUTOMATION_CONCURRENCY:
                        break
                    # Only jobs explicitly created through the persistent queue are dispatched.
                    if row.id not in active and (row.result or {}).get('managed_queue'):
                        active[row.id] = asyncio.create_task(run(row.id))
            last_poll_at = datetime.now(timezone.utc).isoformat()
        except asyncio.CancelledError:
            raise
        except Exception:
            last_error_at = datetime.now(timezone.utc).isoformat()
            # Keep the worker alive on transient DB failures; persisted jobs remain queued.
            import logging
            logging.getLogger(__name__).exception('Queue polling failed')
        await asyncio.sleep(2)


async def shutdown(task):
    task.cancel()
    for job in list(active.values()):
        job.cancel()
    await asyncio.gather(task, *list(active.values()), return_exceptions=True)
