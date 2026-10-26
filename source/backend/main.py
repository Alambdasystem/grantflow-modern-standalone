"""GrantFlow Modern — FastAPI backend entry point."""
import asyncio
import os
import sys
from contextlib import asynccontextmanager

# Ensure stdout/stderr can emit non-ASCII (e.g. emoji in startup logs) when the
# process is spawned with a piped stdout on Windows (cp1252 default), as the
# NovaClaw watchdog does. Without this the lifespan startup print can raise
# UnicodeEncodeError and crash the app, causing a tight restart loop.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from fastapi import FastAPI, Depends
from auth.jwt_handler import get_current_user_token
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# Ensure package root is on path
sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from db.database import init_db

# Routers
from routers.users import router as users_router, auth_router
from routers.grants import router as grants_router
from routers.applications import router as applications_router
from routers.automation import router as automation_router
from routers.ai_router import router as ai_router
from routers.analytics import router as analytics_router
from routers.organizations import router as organizations_router
from routers.renewals import router as renewals_router
from routers.grant_planning import router as grant_planning_router
from routers.grant_enrichment import router as grant_enrichment_router
from routers.providers import router as providers_router
from routers.workspace import router as workspace_router
from routers.foundations import router as foundations_router
from routers.donors import router as donors_router, public_router as give_router
from routers.admin import router as admin_router
from routers.operations import router as operations_router
from routers.ingestion import router as ingestion_router
from routers.ingestion_workers import router as ingestion_workers_router
from routers.email_safety import router as email_safety_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    await init_db()
    if settings.AUTH_MODE=='standalone':
        from db.database import AsyncSessionLocal
        from models.auth_models import AuthControl
        from pathlib import Path
        async with AsyncSessionLocal() as db:
            control=await db.get(AuthControl,1)
            if not control or not control.bootstrapped:
                secret=Path(settings.GFM_BOOTSTRAP_TOKEN_FILE).read_text().strip() if settings.GFM_BOOTSTRAP_TOKEN_FILE else settings.GFM_BOOTSTRAP_TOKEN
                if len(secret)<32:
                    raise RuntimeError('Set a private one-time GFM_BOOTSTRAP_TOKEN of at least 32 characters before first startup')

    # Seed admin user + portal credentials from env vars
    try:
        from startup_seed import run_all_seeds
        if settings.RUN_LEGACY_STARTUP_IMPORTS:
            await run_all_seeds()
    except Exception as exc:
        print(f"[startup] Seed skipped: {exc}")

    # Run migration to import legacy data
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "migration"))
        from adapter import run_full_migration  # noqa
        if settings.RUN_LEGACY_STARTUP_IMPORTS:
            await run_full_migration()
    except Exception as exc:
        print(f"[startup] Migration skipped or failed: {exc}")

    print(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} started on port 8001")
    from services import job_queue
    worker = None
    if settings.AUTOMATION_WORKER_ENABLED:
        await job_queue.recover()
        worker = asyncio.create_task(job_queue.worker())
    app.state.automation_worker = worker
    yield
    if worker:
        await job_queue.shutdown(worker)
    # ── Shutdown ─────────────────────────────────────────────────────────────
    print("Shutting down GrantFlow Modern API...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-native grant management and renewal operating system.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
from auth.standalone import router as standalone_auth_router
app.include_router(standalone_auth_router)
app.include_router(users_router)
app.include_router(grants_router)
app.include_router(applications_router)
app.include_router(automation_router)
app.include_router(ai_router)
app.include_router(analytics_router)
app.include_router(organizations_router)
app.include_router(renewals_router)
app.include_router(grant_planning_router)
app.include_router(grant_enrichment_router)
app.include_router(providers_router)
app.include_router(workspace_router)
app.include_router(foundations_router)
app.include_router(donors_router)
app.include_router(give_router)
app.include_router(admin_router)
app.include_router(operations_router)
app.include_router(ingestion_router)
app.include_router(ingestion_workers_router)
app.include_router(email_safety_router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    from sqlalchemy import text
    from db.database import AsyncSessionLocal
    from services import job_queue
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text('SELECT 1'))
    except Exception:
        return JSONResponse(status_code=503, content={'status':'unavailable','database':'unavailable'})
    worker = getattr(app.state, 'automation_worker', None)
    running = worker is not None and not worker.done()
    healthy = not settings.AUTOMATION_WORKER_ENABLED or running
    result = {"status":"ok" if healthy else "degraded", "service":settings.APP_NAME,
              "version":settings.APP_VERSION, "database":"ok", "worker_enabled":settings.AUTOMATION_WORKER_ENABLED,
              "worker_running":running, "last_poll_at":job_queue.last_poll_at}
    return JSONResponse(status_code=200 if healthy else 503, content=result)


# ── 404 catch-all ─────────────────────────────────────────────────────────────
@app.get('/ready')
async def ready():
    from services.model_readiness import model_status
    core = await health()
    model = await model_status() if settings.AUTH_MODE!='standalone' or settings.AI_ENABLED else {'ready':False,'reason':'not_configured'}
    ok = core.status_code == 200 and model['ready']
    return JSONResponse(status_code=200 if ok else 503,
                        content={'ready': ok, 'core_ready': core.status_code == 200, 'model': model})


@app.get('/api/runtime')
async def runtime(identity:dict=Depends(get_current_user_token)):
    from services.model_readiness import model_status
    model=await model_status() if settings.AI_ENABLED else {'ready':False,'reason':'not_configured'}
    from models.auth_models import MigrationSafety
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        migration=await db.get(MigrationSafety,1)
        state={'external_jobs_paused':migration.external_jobs_paused,'source_cutoff':migration.source_cutoff} if migration else None
    return {'authentication':settings.AUTH_MODE,'ai':model,'email_safety_connected':settings.AUTH_MODE=='anthesis','migration':state}


@app.exception_handler(404)
async def not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=False)
