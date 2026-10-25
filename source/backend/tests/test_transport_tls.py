"""Actual loopback HTTPS/mTLS using throwaway certificates, no real service."""
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import ssl
import subprocess
import threading
import httpx
import pytest
from config import settings
from services.secure_transport import model_client, anthesis_client


def test_verified_tls_and_remote_model_client_certificate(tmp_path, monkeypatch):
    def openssl(*args):
        subprocess.run(['openssl',*args],cwd=tmp_path,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-days','1','-subj','/CN=Synthetic Test CA')
    (tmp_path/'server.ext').write_text('subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth\n')
    (tmp_path/'client.ext').write_text('extendedKeyUsage=clientAuth\n')
    for kind in ['server','client']:
        openssl('req','-newkey','rsa:2048','-nodes','-keyout',kind+'.key','-out',kind+'.csr','-subj','/CN=localhost')
        openssl('x509','-req','-in',kind+'.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out',kind+'.pem','-days','1','-extfile',kind+'.ext')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"synthetic":true}')
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp_path/'server.pem',tmp_path/'server.key')
    context.load_verify_locations(tmp_path/'ca.pem'); context.verify_mode=ssl.CERT_REQUIRED
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    monkeypatch.setattr(settings,'AI_CA_BUNDLE',str(tmp_path/'ca.pem'))
    monkeypatch.setattr(settings,'AI_CLIENT_CERT_FILE',str(tmp_path/'client.pem'))
    monkeypatch.setattr(settings,'AI_CLIENT_KEY_FILE',str(tmp_path/'client.key'))
    monkeypatch.setattr(settings,'ANTHESIS_CA_BUNDLE',str(tmp_path/'ca.pem'))
    async def run():
        url=f'https://localhost:{server.server_port}'
        async with model_client(3) as client:
            assert (await client.get(url)).status_code==200
            # Certificate is valid for localhost, never bypass hostname checks.
            with pytest.raises(httpx.HTTPError): await client.get(url.replace('localhost','127.0.0.1'))
        # An Anthesis TLS client does not inherit model mTLS credentials.
        async with anthesis_client(3) as client:
            with pytest.raises((httpx.HTTPError, ssl.SSLError)): await client.get(url)
    try: asyncio.run(run())
    finally: server.shutdown(); server.server_close(); thread.join(timeout=5)
