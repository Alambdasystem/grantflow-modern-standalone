"""Supervise the staging processes, propagate signals, fail on child exit."""
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

children = []
stopping = False

def stop(signum, frame):
    global stopping
    stopping = True
    for child in children:
        if child.poll() is None:
            child.terminate()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

try:
    for sub in ('uploads', 'private_documents', 'screenshots', 'browser-profile'):
        Path('/data', sub).mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get('PORT', '10000'))
    if not 1024 <= port <= 65535:
        raise RuntimeError('Invalid PORT')
    template = Path('/opt/staging/nginx.conf').read_text()
    Path('/tmp/staging-nginx.conf').write_text(template.replace('__PORT__', str(port)))
    children.append(subprocess.Popen(['python', '-m', 'uvicorn', 'staging_entry:app', '--host', '127.0.0.1', '--port', '8001', '--no-access-log'], cwd='/app/backend'))
    children.append(subprocess.Popen(['node', 'node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3002'], cwd='/frontend'))
    # Do not open the public listener until both the schema and frontend are ready.
    deadline = time.monotonic() + 120
    while not stopping:
        if any(child.poll() is not None for child in children):
            raise RuntimeError('An application process exited during startup')
        try:
            for url in ('http://127.0.0.1:8001/health', 'http://127.0.0.1:3002/gfm-app/login'):
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status != 200:
                        raise RuntimeError('Application not healthy')
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError('Application startup deadline exceeded')
            time.sleep(1)
    if not stopping:
        children.append(subprocess.Popen(['nginx', '-c', '/tmp/staging-nginx.conf', '-g', 'daemon off;']))
    while not stopping:
        if any(child.poll() is not None for child in children):
            raise RuntimeError('A supervised process exited')
        time.sleep(1)
finally:
    stop(None, None)
    deadline = time.monotonic() + 20
    for child in children:
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
