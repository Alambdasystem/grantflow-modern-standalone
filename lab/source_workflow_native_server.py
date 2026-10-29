"""Isolated native-auth test server; no identity overrides, no existing installation access."""
import os,sys,json,secrets,asyncio
from pathlib import Path
from contextlib import asynccontextmanager
repo=Path(__file__).resolve().parents[1]
root=repo/'.private/source-workflow-native';root.mkdir(parents=True,exist_ok=True)
marker=root/'SYNTHETIC-TEST-ONLY'
if (root/'isolated.db').exists() and not marker.exists():raise RuntimeError('Refusing an unmarked database')
marker.write_text('Synthetic local workflow test only')
credentials=root/'credentials.json'
if not credentials.exists():credentials.write_text(json.dumps({'username':'synthetic_workflow_admin','password':secrets.token_urlsafe(24),'bootstrap':secrets.token_urlsafe(40)}))
c=json.loads(credentials.read_text())
os.environ.update(AUTH_MODE='standalone',ENVIRONMENT='development',PUBLIC_ORIGIN='http://127.0.0.1:3109',ALLOWED_ORIGINS='["http://127.0.0.1:3109"]',
    SESSION_SECURE='false',DATABASE_URL='sqlite+aiosqlite:///'+str(root/'isolated.db'),UPLOAD_DIR=str(root/'uploads'),SCREENSHOT_DIR=str(root/'screenshots'),
    INGESTION_STORAGE_DIR=str(root/'documents'),GFM_DATA_ROOT=str(root),GFM_REQUIRE_PERSISTENT_STORAGE='false',
    GFM_BOOTSTRAP_TOKEN=c['bootstrap'],AI_ENABLED='true',AI_PROVIDER='alambda',RUN_LEGACY_STARTUP_IMPORTS='false',INGESTION_SOURCE_MANIFEST='',DEBUG='false')
sys.path.insert(0,str(repo/'source/backend'))
from fastapi import FastAPI
from db import database
from auth.standalone import router as auth
from routers import applications,grants,organizations,application_sources,ingestion,users
from models.models import AutomationJob,AutomationJobStatus,Grant
from sqlalchemy import select
from services import document_ingestion,application_sources as service

async def ingest_loop():
    while True:
        async with database.AsyncSessionLocal() as db:
            id=(await db.execute(select(AutomationJob.id).where(AutomationJob.job_type=='ingest',AutomationJob.status==AutomationJobStatus.queued).limit(1))).scalar_one_or_none()
        if id:await document_ingestion.process(id)
        await asyncio.sleep(.5)

@asynccontextmanager
async def lifespan(app):
    await database.init_db()
    async with database.AsyncSessionLocal() as db:
        if not await db.get(Grant,1):db.add(Grant(id=1,title='SYNTHETIC WORKFLOW QA ONLY',funding_agency='Synthetic funder',amount_max=100000))
        await db.commit()
    await service.recover();tasks=[asyncio.create_task(ingest_loop()),asyncio.create_task(service.worker())]
    yield
    for task in tasks:task.cancel()
    await asyncio.gather(*tasks,return_exceptions=True)

app=FastAPI(lifespan=lifespan)
for r in (auth,users.auth_router,applications.router,grants.router,organizations.router,ingestion.router,application_sources.router):app.include_router(r)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8311,access_log=False)
