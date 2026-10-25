"""Real Playwright agents against a disposable local portal; no real submissions."""
import asyncio
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading

os.environ['GFM_BROWSER_PROFILE_DIR']='/tmp/synthetic-browser-profile'
from config import settings
settings.SCREENSHOT_DIR='/evidence/parity/portal-sandbox'
Path(settings.SCREENSHOT_DIR).mkdir(exist_ok=True)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_GET(self):
        html=b'<form method="POST" action="/login"><input id="username"><input id="password" type="password"><button type="submit">Sign in</button></form>' if self.path=='/login' else b'<form><input id="project"><select id="type"><option value="science">Science</option></select><input type="checkbox" id="confirmed"></form>'
        self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html)
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length','0')))
        self.send_response(303);self.send_header('Location','/portal-home');self.end_headers()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(server.server_port)
async def main():
    from automation.agents.form_filler import FormFillerAgent
    from automation.agents import portal_login,workspace_sync,grant_requirements,sf424_fill
    for module in [portal_login,workspace_sync,grant_requirements,sf424_fill]:assert module._OPENCLAW_PROFILE=='/tmp/synthetic-browser-profile'
    portal_login.PORTAL_CONFIGS['synthetic']={'url':base+'/login','flow':'direct','username_selector':'#username','password_selector':'#password','submit_selector':'button[type=submit]','post_login_url_fragment':'/portal-home'}
    login=await portal_login.PortalLoginAgent().login('synthetic','synthetic-only','not-a-real-password')
    assert login['success'],login.get('error')
    result=await FormFillerAgent().autofill(base+'/form',{'#project':'SYNTHETIC science','#type':'science','#confirmed':True})
    assert result['filled_count']==3 and not result['error']
    output={'feature':'Portal agent browser login and form autofill','result':'PASS','checks':3,'scope':'Actual Chromium agents; local synthetic portal/configuration only. No Login.gov/MFA/real portal acceptance.'}
    Path('/evidence/parity/portal-sandbox.json').write_text(json.dumps(output,indent=2));print(json.dumps(output))
try:asyncio.run(main())
finally:server.shutdown()
