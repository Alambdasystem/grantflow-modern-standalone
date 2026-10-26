"""Unconnected Render staging: schema initialization without user/API access."""
import os

# This entry point deliberately cannot be enabled as a connected application.
if os.environ.get('ENVIRONMENT') != 'render-staging':
    raise RuntimeError('Staging entry point requires ENVIRONMENT=render-staging')
for key in ('DEBUG', 'RUN_LEGACY_STARTUP_IMPORTS', 'AUTOMATION_WORKER_ENABLED', 'INGESTION_LOCAL_WORKER_ENABLED'):
    if os.environ.get(key, '').lower() != 'false':
        raise RuntimeError(f'{key} must be false for unconnected staging')
for key in ('DEFAULT_ADMIN_PASSWORD', 'ANTHESIS_GFM_INTROSPECTION_SECRET', 'ANTHESIS_GFM_INTROSPECTION_SECRET_FILE'):
    if os.environ.get(key):
        raise RuntimeError(f'{key} must be unset for unconnected staging')

from main import app
from fastapi.responses import JSONResponse

@app.middleware('http')
async def staging_boundary(request, call_next):
    if request.url.path != '/health':
        return JSONResponse(status_code=503, content={
            'detail': 'Staging deployment only. Authentication and integrations are not configured.',
            'authentication_ready': False,
        }, headers={'Cache-Control': 'no-store'})
    return await call_next(request)
