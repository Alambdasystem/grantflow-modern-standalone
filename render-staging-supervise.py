"""Supervise the real app; operator maintenance quiesces all DB/file writers."""
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


def terminate_children():
    for child in children:
        if child.poll() is None: child.terminate()
    deadline=time.monotonic()+20
    for child in children:
        try: child.wait(timeout=max(.1,deadline-time.monotonic()))
        except subprocess.TimeoutExpired: child.kill();child.wait()
    children.clear()


def maintenance(port,marker):
    from http.server import BaseHTTPRequestHandler,HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'{"maintenance":true,"ready":false}'
            self.send_response(200 if self.path=='/health' else 503)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        do_POST=do_GET;do_PUT=do_GET;do_PATCH=do_GET;do_DELETE=do_GET
        def log_message(self,*args): pass
    class Server(HTTPServer): allow_reuse_address=True
    with Server(('0.0.0.0',port),Handler) as server:
        server.timeout=1
        while marker.exists() and not stopping: server.handle_request()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

try:
    data_root=Path(os.environ.get('GFM_DATA_ROOT','/var/data'))
    if not data_root.is_absolute() or data_root==Path('/'):
        raise RuntimeError('Invalid data root')
    for path in [data_root,*[data_root/sub for sub in ('uploads','private_documents','screenshots','browser-profile')]]:
        if path.is_symlink(): raise RuntimeError('Data directory symlinks are not permitted')
        path.mkdir(parents=True,exist_ok=True)
        if os.geteuid()==0:
            os.chown(path,10001,10001);os.chmod(path,0o750)
    # Only persistent-directory initialization runs as root. App processes do not.
    if os.geteuid()==0:
        os.setgroups([]);os.setgid(10001);os.setuid(10001)
    port = int(os.environ.get('PORT', '10000'))
    if not 1024 <= port <= 65535:
        raise RuntimeError('Invalid PORT')
    template = Path('/opt/staging/nginx.conf').read_text()
    Path('/tmp/staging-nginx.conf').write_text(template.replace('__PORT__', str(port)))
    marker=data_root/'.maintenance'
    while not stopping:
        if marker.exists():
            maintenance(port,marker)
            continue
        children.append(subprocess.Popen(['python','-m','uvicorn','render_app:app','--host','127.0.0.1','--port','8001','--no-access-log'],cwd='/app/backend'))
        children.append(subprocess.Popen(['node','node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3002'],cwd='/frontend'))
        deadline=time.monotonic()+120
        while not stopping:
            if any(child.poll() is not None for child in children): raise RuntimeError('An application process exited during startup')
            try:
                for url in ('http://127.0.0.1:8001/health','http://127.0.0.1:3002/gfm-app/login'):
                    with urllib.request.urlopen(url,timeout=2) as response:
                        if response.status!=200: raise RuntimeError('Application not healthy')
                break
            except Exception:
                if time.monotonic()>=deadline: raise RuntimeError('Application startup deadline exceeded')
                time.sleep(1)
        if not stopping: children.append(subprocess.Popen(['nginx','-c','/tmp/staging-nginx.conf','-g','daemon off;']))
        while not stopping and not marker.exists():
            if any(child.poll() is not None for child in children): raise RuntimeError('A supervised process exited')
            time.sleep(1)
        terminate_children()
finally:
    stop(None, None)
    terminate_children()
