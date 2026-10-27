"""Disposable beta browser acceptance. Mount only a protected /private test manifest; never production account credentials. See docs/BETA-SOURCE-VERIFICATION-2026-10-27.md. External submissions and email are not exercised."""
import json,time,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
p=Path('/private');d=json.loads((p/'credentials.json').read_text());base=d['base'];out=[]
assert base in {'https://grantflow-modern-staging.onrender.com','http://127.0.0.1:5210'}
assert d['prefix'].startswith('beta_verify_') and all(a['username'].startswith(d['prefix']+'_') for a in d['accounts'].values())
with sync_playwright()as pw:
 b=pw.chromium.launch(headless=True,args=['--no-sandbox']);c=b.new_context();page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 a=d['accounts']['grant_writer'];page.goto(base+'/auth/login');page.get_by_label('Username',exact=True).fill(a['username']);page.get_by_label('Password',exact=True).fill(a['password']);page.get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('heading',name='Mission Control Dashboard').wait_for(timeout=30000)
 for width in (1440,390):
  page.set_viewport_size({'width':width,'height':900})
  for route in ('/dashboard','/grants','/applications','/documents','/operations','/renewals','/analytics','/settings'):
   page.goto(base+'/gfm-app'+route);page.wait_for_load_state('networkidle',timeout=20000);page.wait_for_timeout(300)
   if page.evaluate('document.documentElement.scrollWidth > window.innerWidth+2'):
    page.screenshot(path=str(p/'mobile-failure.png'),full_page=True);print(json.dumps({'result':'FAIL','width':width,'route':route,'scrollWidth':page.evaluate('document.documentElement.scrollWidth')}));sys.exit(1)

  if width==390:
   page.get_by_role('button',name='Open navigation',exact=True).click();page.get_by_role('link',name='Renewals',exact=True).click();page.wait_for_url('**/renewals');page.wait_for_load_state('networkidle',timeout=20000);page.get_by_text('No overdue renewals or renewals due in the next 90 days.',exact=True).wait_for();assert page.get_by_role('button',name='Open navigation',exact=True).is_visible()

  if width==390:
   assert page.get_by_role('heading',name='Renewals Due',exact=True).bounding_box()['y']>=56,'Mobile toolbar covers heading'
  page.screenshot(path=str(p/f'ui-{width}.png'),full_page=True);out.append({'test':'Route rendering without horizontal overflow','width':width,'routes':8,'result':'PASS'})
 print(json.dumps({'test':'desktop/mobile layouts','result':'PASS','viewports':2,'route_checks':16}))
 print(json.dumps({'test':'browser runtime errors','result':'PASS'if not errors else'FAIL','count':len(errors)}))
 old=next(x['value']for x in c.cookies()if x['name']=='__Host-gfm_session');page.set_viewport_size({'width':1440,'height':900});page.get_by_role('button',name='Sign Out',exact=True).first.click();page.get_by_role('button',name='Sign in',exact=True).wait_for(timeout=20000)

 def denied(request):
  for attempt in range(3):
   try:return request.get(base+'/gfm-app/api/auth/me').status
   except Exception:
    if attempt==2:raise
    time.sleep(1)
 assert denied(c.request)==401
 replay=pw.request.new_context(extra_http_headers={'Cookie':'__Host-gfm_session='+old});assert denied(replay)==401;replay.dispose();print(json.dumps({'test':'Visible logout/replay denial','result':'PASS'}))
 (p/'ui-results.json').write_text(json.dumps(out,indent=2));b.close()
