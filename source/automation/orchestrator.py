"""Automation orchestrator — dispatches jobs to Playwright agents."""
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

# Ensure backend module path is available
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from db.database import AsyncSessionLocal
from models.models import AutomationJob, AutomationJobStatus, Grant
from sqlalchemy import select, update

# Keyed by job_id — holds an asyncio.Queue that receives the user's 2FA code.
_two_factor_queues: dict[int, asyncio.Queue] = {}


async def run_job(job_id: int, events: dict) -> None:
    """
    Execute an AutomationJob by its type.
    Writes progress events to the shared `events` dict used by the SSE stream.
    """
    async with AsyncSessionLocal() as db:
        from services.migration_safety import held
        if await held(db):
            await db.execute(update(AutomationJob).where(AutomationJob.id==job_id).values(status=AutomationJobStatus.paused))
            await db.commit()
            return
        result = await db.execute(select(AutomationJob).where(AutomationJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            _emit(events, job_id, "error", "Job not found", 0)
            return

        claimed = await db.execute(update(AutomationJob).where(
            AutomationJob.id == job_id, AutomationJob.status == AutomationJobStatus.queued).values(
            status=AutomationJobStatus.running, started_at=datetime.now(timezone.utc)))
        await db.commit()
        if claimed.rowcount != 1:
            return
        await db.refresh(job)

        _emit(events, job_id, "started", f"Job {job_id} ({job.job_type}) started", 5)

        try:
            if job.job_type == "scrape":
                await _run_scrape(job, db, events)
            elif job.job_type in ("login", "autofill", "submit"):
                await _run_portal_job(job, db, events)
            elif job.job_type == "renew":
                await _run_renew(job, db, events)
            else:
                _emit(events, job_id, "error", f"Unknown job type: {job.job_type}", 100)
                job.status = AutomationJobStatus.failed
                job.error_message = f"Unknown job type: {job.job_type}"
                await db.commit()
                return

            job.steps_log = events.get(job_id, [])[-200:]
            job.status = AutomationJobStatus.completed
            job.completed_at = datetime.now(timezone.utc)
            job.progress_pct = 100
            await db.commit()
            _emit(events, job_id, "completed", "Job completed successfully", 100)

        except Exception as exc:
            job.steps_log = events.get(job_id, [])[-200:]
            job.status = AutomationJobStatus.failed
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            _emit(events, job_id, "error", f"Job failed: {exc}", 100)


async def _run_scrape(job: AutomationJob, db, events: dict):
    from agents.grant_scraper import GrantScraperAgent
    from models.models import Grant, GrantStatus

    scraper = GrantScraperAgent()
    query = (job.result or {}).get("query", "youth nonprofit grant")

    async def progress(pct, message):
        if pct is not None:
            job.progress_pct = pct
            await db.commit()
        _emit(events, job.id, "progress", message, pct or job.progress_pct)

    options = {'allow_browser': False} if (job.result or {}).get('public_discovery_v1') else {}
    raw_grants = await scraper.scrape(query, max_results=50, progress_cb=progress, **options)

    added = 0
    for g in raw_grants:
        if not g.get("title"):
            continue
        duplicate = (await db.execute(select(Grant.id).where(Grant.source_url == g["source_url"] if g.get("source_url") else Grant.title == g["title"]))).scalars().first()
        if duplicate:
            continue
        grant = Grant(
            title=g["title"],
            description=g.get("description"),
            funding_agency=g.get("funding_agency"),
            amount=g.get("amount"),
            deadline_str=g.get("deadline_str"),
            source_url=g.get("source_url"),
            category=g.get("category", "General"),
            status=GrantStatus.active,
            tags=[],
            requirements=[],
        )
        db.add(grant)
        added += 1

    await db.commit()
    job.result = {**(job.result or {}), "grants_added": added, "raw_count": len(raw_grants)}


async def _run_portal_job(job: AutomationJob, db, events: dict):
    """Login + optional 2FA + form fill flow."""
    creds = (job.result or {}).get("credentials", {})
    if not creds or not job.portal_key:
        raise ValueError("Missing portal_key or credentials for portal job")

    from agents.portal_login import PortalLoginAgent
    from models.models import PortalCredential
    login_agent = PortalLoginAgent()

    async def progress(pct, msg):
        job.progress_pct = pct
        job.current_step = msg
        await db.commit()
        _emit(events, job.id, "progress", msg, pct)

    # ── Create a queue so the 2FA endpoint can send the code ─────────────────
    totp_queue: asyncio.Queue = asyncio.Queue()
    _two_factor_queues[job.id] = totp_queue

    async def get_totp_code() -> str | None:
        """Called by the login agent when 2FA is required. Blocks until code arrives."""
        import asyncio as _aio
        # Signal the UI that 2FA is needed
        job.status = AutomationJobStatus.awaiting_approval
        job.current_step = "Waiting for 2FA code"
        result_so_far = job.result or {}
        job.result = {**result_so_far, "requires_2fa": True, "two_factor_hint": "Enter your Login.gov authenticator code in the Providers page."}
        await db.commit()
        _emit(events, job.id, "2fa_needed", "Waiting for 2FA code from user", job.progress_pct)
        try:
            code = await _aio.wait_for(totp_queue.get(), timeout=300)  # 5-min window
            job.status = AutomationJobStatus.running
            job.current_step = "Submitting 2FA code"
            await db.commit()
            return code
        except _aio.TimeoutError:
            raise RuntimeError("2FA timeout — no code received within 5 minutes")

    async def on_device_auth(message: str):
        """Called when Login.gov security check detected — marks job awaiting_approval."""
        job.status = AutomationJobStatus.awaiting_approval
        job.current_step = "Waiting for device verification"
        result_so_far = job.result or {}
        job.result = {
            **result_so_far,
            "requires_device_auth": True,
            "two_factor_hint": message,
        }
        await db.commit()
        _emit(events, job.id, "device_auth_needed", message, job.progress_pct)

    login_result = await login_agent.login(
        portal_key=job.portal_key,
        username=creds.get("username", ""),
        password=creds.get("password", ""),
        progress_cb=progress,
        get_totp_code=get_totp_code,
        on_device_auth=on_device_auth,
    )

    # ── Clean up queue ────────────────────────────────────────────────────────
    _two_factor_queues.pop(job.id, None)

    if login_result.get("screenshot"):
        job.screenshots = [login_result["screenshot"]]

    # ── Update PortalCredential record ────────────────────────────────────────
    cred_result = await db.execute(
        select(PortalCredential).where(PortalCredential.portal_key == job.portal_key)
    )
    cred_row = cred_result.scalar_one_or_none()
    if cred_row:
        cred_row.last_login_at = datetime.now(timezone.utc)
        if login_result.get("success"):
            cred_row.is_connected = True
            cred_row.last_login_status = "success"
        else:
            cred_row.is_connected = False
            cred_row.last_login_status = "failed"

    if not login_result.get("success"):
        error_msg = login_result.get("error") or f"Login failed at step: {login_result.get('step', 'unknown')}"
        raise RuntimeError(error_msg)

    # Update result with login data (strip huge storage_state from result to save space)
    safe_result = {k: v for k, v in login_result.items() if k not in ("storage_state", "cookies")}
    job.result = {**(job.result or {}), **safe_result, "login_success": True}

    if job.job_type == "autofill" and job.portal_url:
        from agents.form_filler import FormFillerAgent
        filler = FormFillerAgent()
        form_result = await filler.autofill(
            portal_url=job.portal_url,
            form_data=(job.result or {}).get("form_data", {}),
            storage_state=login_result.get("storage_state"),
            progress_cb=progress,
        )
        job.result = {**job.result, **form_result}
        if form_result.get("screenshot"):
            job.screenshots = (job.screenshots or []) + [form_result["screenshot"]]


async def _run_renew(job: AutomationJob, db, events: dict):
    """AI-driven renewal: generate a renewal proposal and create a new draft application."""
    from models.models import (
        GrantApplication, Grant, Organization, ApplicationStatus,
        Workflow, WorkflowStatus,
    )

    async def _step(msg: str, pct: int):
        job.progress_pct = pct
        job.current_step = msg
        await db.commit()
        _emit(events, job.id, "progress", msg, pct)

    await _step("Loading original application", 10)
    original_app = await db.get(GrantApplication, job.application_id)
    if not original_app:
        raise ValueError(f"Application {job.application_id} not found")
    existing = (await db.execute(select(GrantApplication).where(
        GrantApplication.parent_application_id == original_app.id,
        GrantApplication.applicant_id == original_app.applicant_id).order_by(GrantApplication.id))).scalars().first()
    if existing:
        job.result = {**(job.result or {}), 'renewed': True, 'renewal_application_id': existing.id,
                      'note': 'Existing renewal draft recovered; review before submission.'}
        await db.commit()
        return

    await _step("Loading grant and org profile", 25)
    grant = await db.get(Grant, original_app.grant_id) if original_app.grant_id else None
    org = await db.get(Organization, original_app.organization_id) if original_app.organization_id else None

    await _step("Generating renewal proposal with AI", 40)
    context = {
        "grant": {
            "title": grant.title if grant else "Unknown grant",
            "description": grant.description if grant else "",
            "funding_agency": grant.funding_agency if grant else "",
            "amount": grant.amount if grant else None,
        },
        "organization": {
            "name": org.name if org else "Unknown organization",
            "mission": org.mission if org else "",
            "capabilities": org.capabilities if org else "",
            "categories": org.categories if org else [],
        },
        "previous_proposal": original_app.proposal_text or "",
        "original_application_id": original_app.id,
    }
    from models.models import OrganizationRecord, Document
    from sqlalchemy import or_, false
    records = (await db.execute(select(OrganizationRecord).where(
        OrganizationRecord.organization_id == original_app.organization_id,
        OrganizationRecord.kind.in_(['configuration','knowledge','audit','partnership'])
    ).order_by(OrganizationRecord.id.desc()))).scalars().all() if org else []
    config = next((r.data for r in records if r.kind=='configuration'), {})
    context['organization_configuration'] = config
    context['knowledge_documents'] = [{'title':f'{r.title} [record {r.id}, revision {r.revision}]',
        'excerpt':r.body[:2500], 'document_type':r.data.get('category'), 'source_url':r.data.get('source_url')}
        for r in records if r.kind=='knowledge'][:20]
    docs = (await db.execute(select(Document).where(or_(Document.application_id==original_app.id,
        ((Document.organization_id==original_app.organization_id) & Document.application_id.is_(None)) if org else false()))
        .order_by(Document.id.desc()).limit(10))).scalars().all()
    from models.models import IngestionDocument, DocumentUse
    ingested_ids=set((await db.execute(select(IngestionDocument.document_id).where(
        IngestionDocument.organization_id==original_app.organization_id))).scalars().all())
    docs=[d for d in docs if d.id not in ingested_ids]
    context['knowledge_documents'] += [{'title':d.original_filename or d.filename,
        'excerpt':(d.extracted_text or d.ai_summary or '')[:2500], 'document_type':d.document_type} for d in docs]
    from services.document_ingestion import retrieval, record_use
    evidence=await retrieval(db,original_app.organization_id,original_app.title or '') if org else []
    context['knowledge_documents']+=evidence
    context['audit_and_partnership_evidence'] = [{'title':r.title,'revision':r.revision,'body':r.body[:2500],
        'details':r.data} for r in records if r.kind in ('audit','partnership')][:20]

    from services.ai_service import AIService
    ai = AIService()
    try:
        renewal_text = await ai.generate("renewal", context)
    finally:
        await ai._client.aclose()

    await _step("Creating renewal draft application", 70)

    from routers.applications import configured_stages

    renewal_app = GrantApplication(
        grant_id=original_app.grant_id,
        organization_id=original_app.organization_id,
        applicant_id=original_app.applicant_id,
        title=f"{(original_app.title or 'Grant').removesuffix(' — Renewal Draft')} — Renewal Draft",
        proposal_text=renewal_text,
        budget_narrative=original_app.budget_narrative,
        amount_requested=original_app.amount_requested,
        status=ApplicationStatus.draft,
        parent_application_id=original_app.id,
        year_number=(original_app.year_number or 1) + 1,
        notes=f"Auto-generated renewal from application #{original_app.id}",
    )
    db.add(renewal_app)
    await db.flush()
    await record_use(db,[e['ingestion_id'] for e in evidence],original_app.organization_id,
                     'application',renewal_app.id,'proposal_text')
    parent_uses=(await db.execute(select(DocumentUse).where(DocumentUse.organization_id==original_app.organization_id,
        DocumentUse.target_type=='application',DocumentUse.target_id==original_app.id))).scalars().all()
    for use in parent_uses:
        await record_use(db,[use.ingestion_id],original_app.organization_id,'application',renewal_app.id,'proposal_text')
        if use.field=='budget_narrative':
            await record_use(db,[use.ingestion_id],original_app.organization_id,'application',renewal_app.id,'budget_narrative')

    for idx, stage in enumerate(configured_stages(config)):
        db.add(Workflow(
            application_id=renewal_app.id,
            stage=stage,
            status=WorkflowStatus.pending,
            order_index=idx,
        ))

    await _step("Finalizing and updating statuses", 90)
    job.result = {
        **(job.result or {}),
        "renewed": True,
        "renewal_application_id": renewal_app.id,
        "note": "Renewal draft created — review and submit from the application page.",
    }
    await db.commit()


def _emit(events: dict, job_id: int, event_type: str, message: str, progress: int):
    events.setdefault(job_id, []).append({
        "type": event_type,
        "message": message,
        "progress": progress,
    })
