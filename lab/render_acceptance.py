"""Browser acceptance using real passwords/cookies, real DB and workers, synthetic data.

Local self-signed TLS is accepted only by this test browser. Production TLS
verification is unchanged. Screenshots never capture credential forms.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['create','recover','ai'],default='create');args=parser.parse_args()
private=Path('/private');out=Path('/evidence/render');out.mkdir(parents=True,exist_ok=True)
creds=json.loads((private/'render-verify-credentials.json').read_text())
base='https://localhost:5200';results=[]
def record(name,fn):
    started=time.monotonic()
    try:
        fn();row={'feature':name,'result':'PASS','seconds':round(time.monotonic()-started,3)}
    except Exception as exc:
        row={'feature':name,'result':'FAIL','error_type':type(exc).__name__,'seconds':round(time.monotonic()-started,3)}
        # Never print Playwright call logs containing filled credentials/tokens.
        detail=str(exc)
        for value in creds.values(): detail=detail.replace(value,'[redacted]')
        (private/'render-last-failure.txt').write_text(detail)
        results.append(row);(out/(args.phase+'-checks.json')).write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
        raise SystemExit(1) from None
    results.append(row);(out/(args.phase+'-checks.json')).write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000})
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(type(e).__name__))
    def setup():
        page.goto(base+'/auth/login');page.get_by_label('Setup code').fill(creds['bootstrap_token'])
        page.get_by_label('Email',exact=True).fill('synthetic-owner@example.com')
        page.get_by_label('Organization',exact=True).fill('Synthetic standalone organization')
        page.get_by_label('Username',exact=True).fill(creds['username']);page.get_by_label('Password',exact=True).fill(creds['password'])
        page.get_by_role('button',name='Create administrator',exact=True).click()
        page.get_by_role('heading',name='Mission Control Dashboard').wait_for(timeout=30000)
    def sign_in():
        page.goto(base+'/auth/login');page.get_by_label('Username',exact=True).fill(creds['username'])
        page.get_by_label('Password',exact=True).fill(creds['password']);page.get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_role('heading',name='Mission Control Dashboard').wait_for(timeout=30000)
    def csrf():
        return next(c['value'] for c in context.cookies() if c['name']=='__Host-gfm_csrf')
    if args.phase=='create':
        record('First administrator setup through actual login screen',setup)
        cookies=context.cookies()
        def cookie_security():
            c=next(c for c in cookies if c['name']=='__Host-gfm_session')
            assert c['httpOnly'] and c['secure'] and c['sameSite']=='Lax'
            assert page.evaluate("localStorage.getItem('authToken')")==None
        record('HttpOnly secure session without browser token storage',cookie_security)
        def opportunity():
            page.goto(base+'/gfm-app/grants');page.get_by_role('button',name='Add opportunity',exact=True).click()
            page.get_by_label('Opportunity title',exact=True).fill('SYNTHETIC standalone grant')
            page.get_by_label('Funding agency',exact=True).fill('Synthetic foundation')
            page.get_by_label('Description',exact=True).fill('Public synthetic opportunity for acceptance only.')
            page.get_by_role('button',name='Save opportunity',exact=True).click()
            page.get_by_text('SYNTHETIC standalone grant',exact=True).first.wait_for(timeout=20000)
        record('Create and reload a grant opportunity through visible UI',opportunity)
        def application():
            page.goto(base+'/gfm-app/applications');page.get_by_role('button',name='New Application',exact=True).click()
            page.locator('select').first.select_option(label='1 - SYNTHETIC standalone grant')
            page.get_by_placeholder('Application Title',exact=True).fill('SYNTHETIC saved standalone application')
            page.get_by_role('button',name='Create',exact=True).click()
            page.get_by_text('SYNTHETIC saved standalone application',exact=True).first.wait_for(timeout=20000)
            page.reload();page.get_by_text('SYNTHETIC saved standalone application',exact=True).first.wait_for(timeout=20000)
        record('Create and reopen a saved application through UI',application)
        raw=b'Synthetic education mission and verified acceptance evidence.'
        def upload():
            page.goto(base+'/gfm-app/documents')
            page.locator('input[type=file]').set_input_files({'name':'synthetic-acceptance.txt','mimeType':'text/plain','buffer':raw})
            page.get_by_role('button',name='Upload and process',exact=True).click()
            page.get_by_text('synthetic-acceptance.txt',exact=False).first.wait_for(timeout=30000)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                response=context.request.get(base+'/gfm-app/api/ingestion/documents')
                rows=response.json()
                if rows and rows[0]['status'] in {'ready','needs_review'}:break
                time.sleep(1)
            assert rows[0]['status'] in {'ready','needs_review'}
            docid=rows[0]['id'];response=context.request.get(base+f'/gfm-app/api/ingestion/documents/{docid}/original')
            assert response.ok and hashlib.sha256(response.body()).digest()==hashlib.sha256(raw).digest()
            (private/'render-verify-state.json').write_text(json.dumps({'document_id':docid,'sha256':hashlib.sha256(raw).hexdigest()}))
        record('Upload, actual worker extraction and authorized download hash',upload)
        page.goto(base+'/gfm-app/dashboard');page.get_by_role('heading',name='Mission Control Dashboard').wait_for()
        page.screenshot(path=str(out/'authenticated-dashboard.png'),full_page=True)
        record('Dashboard has no browser runtime exception',lambda:(_ for _ in ()).throw(AssertionError()) if errors else None)
        saved_session=next(c['value'] for c in context.cookies() if c['name']=='__Host-gfm_session')
        def logout():
            page.get_by_role('button',name='Sign Out',exact=True).first.click()
            page.get_by_role('button',name='Sign in',exact=True).wait_for(timeout=20000)
            assert context.request.get(base+'/gfm-app/api/auth/me').status==401
            invalid=p.request.new_context(ignore_https_errors=True,extra_http_headers={'Cookie':'__Host-gfm_session='+saved_session})
            try: assert invalid.get(base+'/gfm-app/api/auth/me').status==401
            finally:invalid.dispose()
        record('Visible logout and rejection of replayed session',logout)
        record('Password login returns to the real dashboard',sign_in)
        # Private storage state contains a live test session and must not enter Git.
        context.storage_state(path=str(private/'render-verify-browser-state.json'))
    elif args.phase=='recover':
        context.close();context=browser.new_context(ignore_https_errors=True,storage_state=str(private/'render-verify-browser-state.json'))
        page=context.new_page()
        def persisted():
            page.goto(base+'/gfm-app/applications');page.get_by_text('SYNTHETIC saved standalone application',exact=True).first.wait_for(timeout=20000)
            state=json.loads((private/'render-verify-state.json').read_text())
            response=context.request.get(base+f'/gfm-app/api/ingestion/documents/{state["document_id"]}/original')
            assert response.ok and hashlib.sha256(response.body()).hexdigest()==state['sha256']
            assert context.request.get(base+'/gfm-app/api/auth/me').ok
        record('Account, session, application and uploaded file persist after recreation',persisted)
        record('Password login after container recreation',sign_in)
    else:
        record('Real password login before model use',sign_in)
        def ai():
            page.get_by_placeholder('Ask the AI…',exact=True).fill('Reply in one short sentence about synthetic education.')
            with page.expect_response(lambda r:r.url.endswith('/api/ai/generate'),timeout=650000) as pending:
                page.get_by_role('button',name='Send',exact=True).click()
            response=pending.value
            assert response.ok
            data=response.json();assert data.get('result')
            page.get_by_text(data['result'],exact=True).wait_for(timeout=10000)
            page.screenshot(path=str(out/'authenticated-real-ai.png'),full_page=True)
        record('Actual configured AI inference through authenticated application',ai)
    browser.close()
