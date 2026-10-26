"""Production Render entry point. Refuse application startup without durable data."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from config import settings

if settings.AUTH_MODE!='standalone' or settings.ENVIRONMENT!='render-standalone':
    raise RuntimeError('Render application requires explicit standalone authentication')
root=Path(settings.GFM_DATA_ROOT).resolve()
if settings.GFM_REQUIRE_PERSISTENT_STORAGE and not os.path.ismount(root):
    raise RuntimeError('Attach a persistent disk at GFM_DATA_ROOT before enabling the application')
db_path=Path(urlsplit(settings.DATABASE_URL).path).resolve()
for raw in [str(db_path),settings.UPLOAD_DIR,settings.INGESTION_STORAGE_DIR,settings.SCREENSHOT_DIR,os.environ.get('GFM_BROWSER_PROFILE_DIR','')]:
    target=Path(raw).resolve()
    if target==root or root not in target.parents:
        raise RuntimeError('All database and user files must be beneath the persistent data root')
root.mkdir(parents=True,exist_ok=True)
probe=root/'.write-check'
try:
    probe.write_text('storage-check'); probe.unlink()
except OSError:
    raise RuntimeError('Persistent disk must be writable by service UID 10001') from None

from main import app
