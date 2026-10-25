"""Grants.gov Workspace sync and application status check endpoints."""
import asyncio
import os
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db, AsyncSessionLocal
from models.models import (
    AutomationJob, AutomationJobStatus, GrantApplication, PortalCredential
)
from auth.jwt_handler import get_current_user_token, require_admin

router = APIRouter(prefix="/api/workspace", tags=["workspace"], dependencies=[Depends(require_admin)])

_AUTOMATION_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "automation")
)


@router.post("/grants-gov/sync")
async def sync_workspace(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_token),
):
    """Pull all applications from the grants.gov Workspace and upsert into GrantFlow."""
    cred_result = await db.execute(
        select(PortalCredential).where(PortalCredential.portal_key == "grants_gov")
    )
    cred = cred_result.scalar_one_or_none()
    if not cred or not cred.is_connected:
        raise HTTPException(
            status_code=422,
            detail="Connect to grants.gov first via the Providers page.",
        )

    job = AutomationJob(
        job_type="workspace_sync",
        portal_key="grants_gov",
        status=AutomationJobStatus.queued,
        created_by=current_user.get("sub"),
        result={},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_workspace_sync, job.id)
    return {"job_id": job.id, "message": "Workspace sync started"}


@router.get("/grants-gov/sync/{job_id}")
async def get_sync_status(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Poll the status of a workspace sync job."""
    job = await db.get(AutomationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "status": job.status.value if hasattr(job.status, "value") else job.status,
        "progress_pct": job.progress_pct,
        "current_step": job.current_step,
        "error_message": job.error_message,
        "result": job.result,
    }


@router.post("/grants-gov/check-status/{application_id}")
async def check_application_status(
    application_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Check the live status of a submitted application by navigating to its Workspace URL."""
    app = await db.get(GrantApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    workspace_url = None
    if app.form_data and "workspace_sync" in app.form_data:
        workspace_url = app.form_data["workspace_sync"].get("workspace_url")

    if not workspace_url:
        raise HTTPException(
            status_code=422,
            detail="No workspace URL for this application. Run Workspace Sync first.",
        )

    job = AutomationJob(
        job_type="workspace_sync",
        portal_key="grants_gov",
        application_id=application_id,
        status=AutomationJobStatus.queued,
        result={"checking_url": workspace_url},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_status_check, job.id, application_id, workspace_url)
    return {"job_id": job.id, "message": "Status check started"}


@router.post("/grants-gov/fill-sf424/{application_id}")
async def fill_sf424(
    application_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_token),
):
    """
    Open the grants.gov Workspace application and auto-fill the SF-424 with org profile data.
    Requires the application to have been synced from Workspace (has workspace_sync.workspace_url).
    """
    from models.models import User, Organization

    app = await db.get(GrantApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    workspace_url = None
    if app.form_data and "workspace_sync" in app.form_data:
        workspace_url = app.form_data["workspace_sync"].get("workspace_url")

    if not workspace_url:
        raise HTTPException(
            status_code=422,
            detail="No workspace URL — sync from grants.gov Workspace first or set the URL manually.",
        )

    # Load org profile
    user_result = await db.execute(
        select(User).where(User.username == current_user.get("username", "")).limit(1)
    )
    user = user_result.scalar_one_or_none()
    org = None
    if user and user.organization_id:
        org = await db.get(Organization, user.organization_id)

    # Serialize for background task (can't pass SQLAlchemy objects across threads)
    org_dict = {}
    if org:
        for field in ("name", "ein", "uei", "address", "city", "state", "zip_code",
                      "country", "congressional_district", "aor_first_name", "aor_last_name",
                      "aor_title", "aor_phone", "aor_email"):
            org_dict[field] = getattr(org, field, None) or ""

    app_dict = {
        "id": app.id,
        "title": app.title or "",
        "amount_requested": app.amount_requested,
        "proposal_text": app.proposal_text,
    }

    # Get CFDA from grant enrichment if available
    if app.grant_id:
        from models.models import Grant
        grant = await db.get(Grant, app.grant_id)
        if grant and grant.meta and "enrichment" in grant.meta:
            app_dict["cfda_number"] = grant.meta["enrichment"].get("cfda_number", "")

    job = AutomationJob(
        job_type="sf424_fill",
        portal_key="grants_gov",
        application_id=application_id,
        status=AutomationJobStatus.queued,
        result={"workspace_url": workspace_url},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_sf424_fill, job.id, workspace_url, org_dict, app_dict)
    return {"job_id": job.id, "message": "SF-424 fill started — browser window will open on your desktop"}


# ── Background workers ─────────────────────────────────────────────────────────

async def _run_sf424_fill(job_id: int, workspace_url: str, org_dict: dict, app_dict: dict):
    sys.path.insert(0, _AUTOMATION_PATH)

    async with AsyncSessionLocal() as db:
        job = await db.get(AutomationJob, job_id)
        if not job:
            return

        job.status = AutomationJobStatus.running
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            from agents.sf424_fill import SF424FillAgent
            agent = SF424FillAgent()

            async def progress(pct, msg):
                job.progress_pct = pct
                job.current_step = msg
                await db.commit()

            result = await agent.fill(
                workspace_url=workspace_url,
                org=org_dict,
                application=app_dict,
                progress_cb=progress,
            )

            if result.get("success"):
                job.status = AutomationJobStatus.completed
                job.completed_at = datetime.now(timezone.utc)
                job.progress_pct = 100
            else:
                job.status = AutomationJobStatus.failed
                job.error_message = result.get("error", "SF-424 fill failed")

            job.result = {
                "filled_fields": result.get("filled_fields", []),
                "skipped_fields": result.get("skipped_fields", []),
                "screenshot": result.get("screenshot"),
                "error": result.get("error"),
            }
            await db.commit()

        except Exception as exc:
            job.status = AutomationJobStatus.failed
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def _run_workspace_sync(job_id: int):
    sys.path.insert(0, _AUTOMATION_PATH)

    async with AsyncSessionLocal() as db:
        job = await db.get(AutomationJob, job_id)
        if not job:
            return

        job.status = AutomationJobStatus.running
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            from agents.workspace_sync import WorkspaceSyncAgent
            agent = WorkspaceSyncAgent()

            async def progress(pct, msg):
                job.progress_pct = pct
                job.current_step = msg
                await db.commit()

            sync_result = await agent.sync(progress_cb=progress)

            if not sync_result.get("success"):
                job.status = AutomationJobStatus.failed
                job.error_message = sync_result.get("error", "Sync failed")
                await db.commit()
                return

            # Upsert applications into GrantFlow
            upserted = 0
            created = 0
            for app_data in sync_result.get("applications", []):
                title = (app_data.get("title") or "").strip()
                if not title:
                    continue

                existing_result = await db.execute(
                    select(GrantApplication).where(GrantApplication.title == title)
                )
                existing = existing_result.scalar_one_or_none()

                ws_meta = {
                    "opportunity_number": app_data.get("opportunity_number"),
                    "cfda": app_data.get("cfda"),
                    "workspace_status": app_data.get("workspace_status"),
                    "last_modified": app_data.get("last_modified"),
                    "workspace_url": app_data.get("workspace_url"),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }

                if existing:
                    if app_data.get("status"):
                        existing.status = app_data["status"]
                    fd = existing.form_data or {}
                    fd["workspace_sync"] = ws_meta
                    existing.form_data = fd
                    upserted += 1
                else:
                    new_app = GrantApplication(
                        title=title,
                        status=app_data.get("status", "draft"),
                        notes=f"Synced from grants.gov Workspace. Opportunity: {app_data.get('opportunity_number', '')}",
                        form_data={"workspace_sync": ws_meta},
                        source_url=app_data.get("workspace_url"),
                    )
                    db.add(new_app)
                    created += 1

            await db.commit()

            job.status = AutomationJobStatus.completed
            job.completed_at = datetime.now(timezone.utc)
            job.progress_pct = 100
            job.result = {
                "created": created,
                "updated": upserted,
                "total_found": len(sync_result.get("applications", [])),
                "applications": sync_result.get("applications", []),
            }
            await db.commit()

        except Exception as exc:
            job.status = AutomationJobStatus.failed
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def _run_status_check(job_id: int, app_id: int, workspace_url: str):
    sys.path.insert(0, _AUTOMATION_PATH)

    async with AsyncSessionLocal() as db:
        job = await db.get(AutomationJob, job_id)
        if not job:
            return

        job.status = AutomationJobStatus.running
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            from agents.workspace_sync import WorkspaceSyncAgent
            agent = WorkspaceSyncAgent()

            async def progress(pct, msg):
                job.progress_pct = pct
                job.current_step = msg
                await db.commit()

            check_result = await agent.check_application_status(
                workspace_url=workspace_url,
                progress_cb=progress,
            )

            if not check_result.get("success"):
                job.status = AutomationJobStatus.failed
                job.error_message = check_result.get("error", "Status check failed")
                await db.commit()
                return

            # Update the application record with new status
            app = await db.get(GrantApplication, app_id)
            if app:
                detected = check_result.get("status")
                if detected:
                    app.status = detected
                fd = app.form_data or {}
                ws = fd.get("workspace_sync", {})
                ws["workspace_status"] = check_result.get("raw_status") or detected
                ws["last_checked"] = datetime.now(timezone.utc).isoformat()
                fd["workspace_sync"] = ws
                app.form_data = fd

            await db.commit()

            job.status = AutomationJobStatus.completed
            job.completed_at = datetime.now(timezone.utc)
            job.progress_pct = 100
            job.result = {
                "detected_status": check_result.get("status"),
                "raw_status": check_result.get("raw_status"),
                "page_url": check_result.get("page_url"),
            }
            await db.commit()

        except Exception as exc:
            job.status = AutomationJobStatus.failed
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
