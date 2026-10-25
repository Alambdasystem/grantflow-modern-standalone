"""Synthetic, loopback-published Docker test identity contract. Never production auth.

No real accounts/credentials are loaded. Tokens live only in this process and the
lab browser, expire after one hour, and disappear when this fixture restarts.
"""
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SESSIONS = {}
LOCK = threading.Lock()
SERVICE_KEY = os.environ['LAB_SERVICE_KEY']


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log authorization headers, body or session values.

    def send(self, status, body, content_type='application/json'):
        data = json.dumps(body).encode() if content_type == 'application/json' else body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.send(200, {'status': 'ok', 'synthetic_identity': True})
        if path in {'/', '/auth/login'}:
            return self.send(200, '''<!doctype html><html><head><meta charset="utf-8"><title>Synthetic Grantflow Docker lab</title></head>
<body style="font:18px system-ui;max-width:700px;margin:60px auto;padding:20px"><h1>Grantflow Docker lab</h1>
<p><strong>Synthetic identity and fresh test data.</strong> This login does not use Anthesis accounts.</p>
<p>The application containers have no external network access. Local workers and the local AI model use synthetic test data; this is not production integration access.</p>
<button onclick="enter('admin')">Enter as synthetic administrator</button>
<button onclick="enter('viewer')">Enter as synthetic viewer</button><p id="status"></p>
<script>async function enter(role){const r=await fetch('/lab/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})});
if(!r.ok){document.getElementById('status').textContent='Lab login unavailable';return;}
const s=await r.json();localStorage.setItem('authToken',s.token);location.replace('/gfm-app/dashboard');}</script></body></html>''', 'text/html; charset=utf-8')
        return self.send(404, {'detail': 'Synthetic lab route not found'})

    def do_POST(self):
        path = urlsplit(self.path).path
        size = int(self.headers.get('Content-Length', '0'))
        if size > 4096:
            return self.send(413, {'detail': 'Request too large'})
        try:
            body = json.loads(self.rfile.read(size) or b'{}')
        except (ValueError, TypeError):
            return self.send(400, {'detail': 'JSON required'})
        if path == '/lab/session':
            # Deliberately unauthenticated synthetic entry; never deploy this as an IdP.
            role = body.get('role', 'viewer')
            if role not in {'admin', 'viewer', 'grant_writer', 'reviewer', 'other_writer'}:
                return self.send(422, {'detail': 'Unsupported synthetic role'})
            value = secrets.token_urlsafe(32)
            with LOCK:
                SESSIONS[value] = (role, time.monotonic() + 3600)
            return self.send(200, {'token': value, 'synthetic': True})
        if path not in {'/api/gfm/introspect', '/api/gfm/revoke'}:
            return self.send(404, {'detail': 'Synthetic lab route not found'})
        if not secrets.compare_digest(self.headers.get('X-Anthesis-Service-Key', ''), SERVICE_KEY):
            return self.send(401, {'detail': 'Service authentication required'})
        header = self.headers.get('Authorization', '')
        value = header[7:] if header.startswith('Bearer ') else ''
        with LOCK:
            session = SESSIONS.get(value)
        if not session or session[1] <= time.monotonic():
            return self.send(401, {'detail': 'Synthetic session expired or invalid'})
        role = session[0]
        if path.endswith('/revoke'):
            with LOCK:
                # Central Anthesis increments the identity's auth_version:
                # revoke every session for this synthetic identity, not only
                # the presented token. Other identities are unaffected.
                for key in [key for key, item in SESSIONS.items() if item[0] == role]:
                    SESSIONS.pop(key, None)
            return self.send(200, {'success': True})
        return self.send(200, {'identity_id': 'docker-lab-' + role,
                              'username': 'synthetic_' + role,
                              'email': role + '@grantflow-lab.invalid',
                              'grantflow_role': 'grant_writer' if role == 'other_writer' else role,
                              'grantflow_access': ['all'] if role == 'admin' else ['read'] if role == 'viewer' else ['read', 'write']})


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
