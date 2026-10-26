"""Generate disposable acceptance credentials privately; never print their values."""
import json
from pathlib import Path
import secrets

root=Path(__file__).resolve().parents[1]; private=root/'.private'
private.mkdir(exist_ok=True)
credentials={'username':'synthetic_owner','password':secrets.token_urlsafe(32),'bootstrap_token':secrets.token_urlsafe(32)}
(private/'render-verify-credentials.json').write_text(json.dumps(credentials))
variables={
    'PORT':'5200','AUTH_MODE':'standalone','ENVIRONMENT':'render-standalone','PUBLIC_ORIGIN':'https://localhost:5200',
    'ALLOWED_ORIGINS':'["https://localhost:5200"]','SESSION_SECURE':'true',
    'GFM_BOOTSTRAP_TOKEN':credentials['bootstrap_token'],'GFM_DATA_ROOT':'/var/data','GFM_REQUIRE_PERSISTENT_STORAGE':'true',
    'DATABASE_URL':'sqlite+aiosqlite:////var/data/grantflow.db','UPLOAD_DIR':'/var/data/uploads',
    'INGESTION_STORAGE_DIR':'/var/data/private_documents','SCREENSHOT_DIR':'/var/data/screenshots',
    'GFM_BROWSER_PROFILE_DIR':'/var/data/browser-profile','DEBUG':'false','RUN_LEGACY_STARTUP_IMPORTS':'false',
    'AUTOMATION_WORKER_ENABLED':'true','INGESTION_LOCAL_WORKER_ENABLED':'true','AI_ENABLED':'true',
    'OLLAMA_URL':'http://grantflow-lab-ollama-1:11434','DEFAULT_MODEL':'llama3.2:latest',
    'EXPECTED_MODEL_DIGEST':'a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72',
    'AI_PRELOAD_MODEL':'true','AI_LOAD_TIMEOUT_SECONDS':'180','AI_INFERENCE_TIMEOUT_SECONDS':'180'}
(private/'render-verify.env').write_text('\n'.join(k+'='+v for k,v in variables.items())+'\n')
template=(root/'render-staging-nginx.conf').read_text().replace('listen __PORT__;',
    'listen __PORT__ ssl;\n    ssl_certificate /test-certs/cert.pem;\n    ssl_certificate_key /test-certs/key.pem;')
(private/'render-verify-nginx.conf').write_text(template)
print('Private synthetic test credentials and local TLS configuration prepared.')
