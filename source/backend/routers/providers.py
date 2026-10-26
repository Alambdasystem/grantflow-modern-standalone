"""Portal providers — store credentials and trigger login jobs via OpenClaw (Playwright)."""
import base64
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import PortalCredential, AutomationJob, AutomationJobStatus
from auth.jwt_handler import get_current_user_token, require_admin
from datetime import datetime, timezone

router = APIRouter(prefix="/api/providers", tags=["providers"], dependencies=[Depends(require_admin)])

# ── Static metadata for known portals ─────────────────────────────────────────
KNOWN_PORTALS = [
    {
        "key": "grants_gov",
        "name": "Grants.gov",
        "url": "https://apply07.grants.gov/apply/login.faces",
        "register_url": "https://apply07.grants.gov/apply/register.faces",
        "credential_type": "username_password",
        "description": "Federal grants portal. Register at SAM.gov first to get your UEI, then create a Workspace account.",
        "requirements": ["SAM.gov registration (UEI)", "Grants.gov Workspace account"],
    },
    {
        "key": "sam_gov",
        "name": "SAM.gov",
        "url": "https://sam.gov/profile/details",
        "register_url": "https://sam.gov/content/entity-registration",
        "credential_type": "username_password",
        "description": "System for Award Management — required for all federal grants. Provides UEI number.",
        "requirements": ["EIN (Tax ID)", "DUNS / UEI number", "Login.gov account"],
    },
    {
        "key": "justgrants",
        "name": "JustGrants (DOJ)",
        "url": "https://justgrants.usdoj.gov",
        "register_url": "https://justgrants.usdoj.gov",
        "credential_type": "username_password",
        "description": "Department of Justice grants management system.",
        "requirements": ["SAM.gov registration", "DOJ entity registration"],
    },
    {
        "key": "foundation_center",
        "name": "Candid / Foundation Center",
        "url": "https://candid.org/login",
        "register_url": "https://candid.org/join",
        "credential_type": "username_password",
        "description": "Foundation Directory for private/foundation grant research.",
        "requirements": ["Nonprofit status", "Candid account"],
    },
    {
        "key": "instrumentl",
        "name": "Instrumentl",
        "url": "https://www.instrumentl.com/login",
        "register_url": "https://www.instrumentl.com/register",
        "credential_type": "api_key",
        "description": "AI-powered grant discovery and management platform.",
        "requirements": ["Instrumentl API key from account settings"],
    },
    {
        "key": "fluxx",
        "name": "Fluxx Grantseeker",
        "url": "https://grantseeker.fluxx.io",
        "register_url": "https://grantseeker.fluxx.io",
        "credential_type": "username_password",
        "description": "Foundation grant portal used by many private foundations.",
        "requirements": ["Foundation invitation or public access"],
    },
]


def _b64enc(s: str) -> str:
    return base64.b64encode(s.encode()).decode() if s else ""

def _b64dec(s: str) -> str:
    try:
        return base64.b64decode(s.encode()).decode() if s else ""
    except Exception:
        return ""


class ProviderUpsert(BaseModel):
    portal_key: str | None = None   # provided in URL path; optional in body
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    notes: str | None = None


class ProviderOut(BaseModel):
    id: int
    portal_key: str
    portal_name: str
    portal_url: str | None
    credential_type: str
    has_credentials: bool
    username: str | None
    is_connected: bool
    last_login_at: str | None
    last_login_status: str | None
    last_job_id: int | None
    notes: str | None

    model_config = {"from_attributes": True}


def _to_out(cred: PortalCredential) -> ProviderOut:
    return ProviderOut(
        id=cred.id,
        portal_key=cred.portal_key,
        portal_name=cred.portal_name,
        portal_url=cred.portal_url,
        credential_type=cred.credential_type or "username_password",
        has_credentials=bool(cred.password_b64 or cred.api_key_b64),
        username=cred.username,
        is_connected=cred.is_connected or False,
        last_login_at=cred.last_login_at.isoformat() if cred.last_login_at else None,
        last_login_status=cred.last_login_status,
        last_job_id=cred.last_job_id,
        notes=cred.notes,
    )


async def seed_providers_from_env():
    """Called at startup — writes any env-configured credentials to DB so they appear in the UI."""
    import base64 as _b64
    from db.database import AsyncSessionLocal

    portal_envs = [
        ("grants_gov",         settings.GRANTS_GOV_USERNAME,          settings.GRANTS_GOV_PASSWORD),
        ("sam_gov",            settings.SAM_GOV_USERNAME,             settings.SAM_GOV_PASSWORD),
        ("justgrants",         settings.JUSTGRANTS_USERNAME,          settings.JUSTGRANTS_PASSWORD),
        ("foundation_center",  settings.FOUNDATION_CENTER_USERNAME,   settings.FOUNDATION_CENTER_PASSWORD),
    ]

    async with AsyncSessionLocal() as db:
        for portal_key, username, password in portal_envs:
            if not username and not password:
                continue
            result = await db.execute(
                select(PortalCredential).where(PortalCredential.portal_key == portal_key)
            )
            cred = result.scalar_one_or_none()
            static = next((p for p in KNOWN_PORTALS if p["key"] == portal_key), None)

            if not cred:
                cred = PortalCredential(portal_key=portal_key)
                db.add(cred)

            # Only update if not already set (don't overwrite user-changed credentials)
            if static:
                cred.portal_name = static["name"]
                cred.portal_url = static["url"]
                cred.credential_type = static["credential_type"]

            if username and not cred.username:
                cred.username = username
            if password and not cred.password_b64:
                cred.password_b64 = _b64enc(password)

        await db.commit()


@router.get("")
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Return all known portals with their saved credential status."""
    result = await db.execute(select(PortalCredential))
    saved = {c.portal_key: c for c in result.scalars().all()}

    out = []
    for portal in KNOWN_PORTALS:
        cred = saved.get(portal["key"])
        if cred:
            out.append({**portal, "credential": _to_out(cred)})
        else:
            out.append({**portal, "credential": None})

    # Also append any saved credentials for portals not in the static list
    for key, cred in saved.items():
        if not any(p["key"] == key for p in KNOWN_PORTALS):
            out.append({
                "key": key,
                "name": cred.portal_name,
                "url": cred.portal_url,
                "credential_type": cred.credential_type or "username_password",
                "description": cred.notes or "Custom portal",
                "requirements": [],
                "credential": _to_out(cred),
            })

    return out


@router.put("/{portal_key}")
async def upsert_provider(
    portal_key: str,
    payload: ProviderUpsert,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Save (or update) credentials for a portal."""
    result = await db.execute(
        select(PortalCredential).where(PortalCredential.portal_key == portal_key)
    )
    cred = result.scalar_one_or_none()

    # Look up static metadata
    static = next((p for p in KNOWN_PORTALS if p["key"] == portal_key), None)
    portal_name = static["name"] if static else portal_key.replace("_", " ").title()
    portal_url = static["url"] if static else None
    ctype = static["credential_type"] if static else "username_password"

    if not cred:
        cred = PortalCredential(portal_key=portal_key)
        db.add(cred)

    cred.portal_name = portal_name
    cred.portal_url = portal_url
    cred.credential_type = ctype
    cred.notes = payload.notes

    if payload.username is not None:
        cred.username = payload.username
    if payload.password:
        cred.password_b64 = _b64enc(payload.password)
        cred.is_connected = False  # reset on new credentials
    if payload.api_key:
        cred.api_key_b64 = _b64enc(payload.api_key)
        cred.is_connected = False

    await db.commit()
    await db.refresh(cred)
    return _to_out(cred)


@router.post("/{portal_key}/connect")
async def connect_provider(
    portal_key: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Trigger an OpenClaw (Playwright) login job through the automation orchestrator."""
    from services.migration_safety import require_released
    await require_released(db)
    result = await db.execute(
        select(PortalCredential).where(PortalCredential.portal_key == portal_key)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="No credentials saved for this portal. Add credentials first.")

    username = cred.username or ""
    password = _b64dec(cred.password_b64 or "")
    api_key = _b64dec(cred.api_key_b64 or "")

    if not (username and password) and not api_key:
        raise HTTPException(status_code=422, detail="Portal has no usable credentials saved.")

    job = AutomationJob(
        job_type="login",
        portal_key=portal_key,
        portal_url=cred.portal_url,
        status=AutomationJobStatus.queued,
        progress_pct=0,
        current_step="Queued",
        steps_log=[{"step": "queued", "ts": datetime.now(timezone.utc).isoformat()}],
        screenshots=[],
        # Credentials stored in result so the orchestrator can read them
        result={"credentials": {"username": username, "password": password or api_key}},
    )
    db.add(job)
    cred.last_login_status = "pending"
    await db.commit()
    await db.refresh(job)

    cred.last_job_id = job.id
    await db.commit()

    # Delegate to the shared automation runner — same path as renewal jobs
    async def _run(job_id: int):
        try:
            import sys as _s, os as _o
            _s.path.insert(0, _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.dirname(__file__))), "automation"))
            from orchestrator import run_job
            await run_job(job_id, {})
        except Exception as exc:
            from db.database import AsyncSessionLocal as _ASL
            from sqlalchemy.ext.asyncio import AsyncSession as _AS  # noqa
            async with _ASL() as sess:
                j = await sess.get(AutomationJob, job_id)
                if j:
                    j.status = AutomationJobStatus.failed
                    j.error_message = f"{type(exc).__name__}: {exc}"
                    j.progress_pct = 100
                    await sess.commit()

    background_tasks.add_task(_run, job.id)
    return {"ok": True, "job_id": job.id, "message": f"Login job #{job.id} started for {portal_key}"}


@router.post("/jobs/{job_id}/2fa")
async def submit_2fa(
    job_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Send a TOTP/2FA code to a waiting login job."""
    code = (payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    # Import the shared queue dict from the orchestrator
    try:
        import sys as _s, os as _o
        _s.path.insert(0, _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.dirname(__file__))), "automation"))
        from orchestrator import _two_factor_queues
    except ImportError:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    queue = _two_factor_queues.get(job_id)
    if not queue:
        raise HTTPException(status_code=404, detail="No 2FA session waiting for this job. It may have timed out or already completed.")

    await queue.put(code)
    return {"ok": True, "message": "2FA code sent to waiting job"}


@router.delete("/{portal_key}")
async def delete_provider(
    portal_key: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Remove saved credentials for a portal."""
    result = await db.execute(
        select(PortalCredential).where(PortalCredential.portal_key == portal_key)
    )
    cred = result.scalar_one_or_none()
    if cred:
        await db.delete(cred)
        await db.commit()
    return {"ok": True}
