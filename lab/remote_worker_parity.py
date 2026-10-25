"""Real worker CLI against an ephemeral loopback coordinator, synthetic records only."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import requests

with tempfile.TemporaryDirectory(prefix='gfm-remote-') as tmp:
    root=Path(tmp);secret=secrets.token_urlsafe(32)
    registry=root/'workers.json'
    registry.write_text(json.dumps([{'id':'synthetic-worker','enabled':True,'token_sha256':hashlib.sha256(secret.encode()).hexdigest(),'organization_ids':[1]}]))
    env={**os.environ,'DATABASE_URL':'sqlite+aiosqlite:///'+(root/'test.db').as_posix(),'AUTOMATION_WORKER_ENABLED':'true',
         'INGESTION_LOCAL_WORKER_ENABLED':'false','INGESTION_WORKER_REGISTRY':str(registry),
         'INGESTION_STORAGE_DIR':str(root/'files'),'UPLOAD_DIR':str(root/'uploads'),'SCREENSHOT_DIR':str(root/'shots')}
    os.environ.update(env)
    from db.database import engine,AsyncSessionLocal,Base
    from models.models import User,UserRole,Organization
    async def seed():
        async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            db.add(Organization(id=1,name='Synthetic remote worker organization'));await db.flush()
            db.add(User(identity_id='docker-lab-grant_writer',username='synthetic_remote_writer',email='remote@example.test',hashed_password='!disabled!',role=UserRole.grant_writer,organization_id=1,is_active=True,is_approved=True));await db.commit()
        await engine.dispose()
    asyncio.run(seed())
    with (root/'coordinator.log').open('w') as log:
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port','18001','--no-access-log'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                try:
                    if requests.get('http://127.0.0.1:18001/health',timeout=1).status_code==200:break
                except requests.RequestException:pass
                time.sleep(.5)
            token=requests.post('http://identity:8000/lab/session',json={'role':'grant_writer'}).json()['token']
            headers={'Authorization':'Bearer '+token}
            r=requests.post('http://127.0.0.1:18001/api/ingestion/upload',headers=headers,files={'file':('synthetic-worker.txt',b'Synthetic remote extraction education evidence')});assert r.status_code==202
            item=r.json()
            config=root/'config.json';config.write_text(json.dumps({'base_url':'http://127.0.0.1:18001','token':secret,'worker_id':'synthetic-worker'}))
            worker=subprocess.run([sys.executable,'/app/scripts/ingestion_worker.py','--config',str(config),'--once'],env=env,capture_output=True,timeout=90)
            assert worker.returncode==0,'Worker CLI failed'
            result=requests.get(f'http://127.0.0.1:18001/api/ingestion/documents/{item["id"]}',headers=headers).json()
            assert result['status'] in {'ready','needs_review'}
            assert 'Synthetic remote extraction' in result['extracted']['text']
            assert requests.post('http://127.0.0.1:18001/api/ingestion-workers/claim',headers={'Authorization':'Bearer invalid'}).status_code==401
            output={'feature':'Separate extraction-worker CLI -> claim -> download/hash -> subprocess extraction -> completion -> saved result','result':'PASS','checks':3,'scope':'Actual loopback HTTP and worker processes; synthetic identity and worker enrollment; no cloud provider'}
            Path('/evidence/parity/remote-worker.json').write_text(json.dumps(output,indent=2));print(json.dumps(output))
        finally:
            proc.terminate();proc.wait(timeout=20)
