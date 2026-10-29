"""Real local UI → native auth → parser/queue → Alambda → downloads. No response fixtures."""
import json,hashlib,time,zipfile
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
from docx import Document
out=Path(__file__).resolve().parents[1]/'.private/source-workflow-native';cdata=json.loads((out/'credentials.json').read_text())
backend='http://127.0.0.1:8311';frontend='http://127.0.0.1:3109'
status=httpx.get(backend+'/api/auth/status').json()
if status['setup_required']:
    r=httpx.post(backend+'/api/auth/setup',headers={'Origin':frontend},json={'username':cdata['username'],'password':cdata['password'],'email':'workflow.qa@example.org','organization':'SYNTHETIC WORKFLOW QA ONLY','bootstrap_token':cdata['bootstrap']});assert r.status_code==200,r.status_code
source=b'Question: Describe the project activities. Under 2,000 Characters\nDraft planning facts: This synthetic pilot proposes four supervised robotics workshops for twenty students in total. Outcomes have not been measured.\nProposed funding plan: Overall program total $425,000; funder request $100,000; unmet funding $325,000, not committed.'
with sync_playwright() as p:
    b=p.chromium.launch(channel='chrome',headless=True);context=b.new_context(accept_downloads=True)
    def proxy(route):
        # Actual HTTP forwarding only: preserve backend status/body/cookies unchanged.
        target=backend+route.request.url.split('/gfm-app',1)[1]
        response=route.fetch(url=target);route.fulfill(response=response)
    context.route('**/gfm-app/api/**',proxy)
    page=context.new_page();page.on('pageerror',lambda e:print('Frontend exception:',str(e),flush=True));page.goto(frontend+'/gfm-app/login');page.get_by_label('Username',exact=True).fill(cdata['username']);page.get_by_label('Password',exact=True).fill(cdata['password']);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url('**/gfm-app/dashboard',timeout=30000)
    def headers():return {'Origin':frontend,'X-CSRF-Token':next(x['value'] for x in context.cookies() if x['name']=='gfm_csrf')}
    def api(method,path,**kwargs):
        r=context.request.fetch(backend+path,method=method,headers=headers(),**kwargs);assert r.ok,f'{method} {path}: {r.status}';return r
    me=api('GET','/api/auth/me').json();assert me['role']=='admin'
    app=api('POST','/api/applications/',data={'grant_id':1,'title':'SYNTHETIC NATIVE WORKFLOW QA - DO NOT SUBMIT','amount_requested':100000,'form_data':{'funding_plan':{'program_total':425000,'unmet_funding':325000}}}).json();aid=app['id']
    uploaded=api('POST','/api/ingestion/upload',multipart={'file':{'name':'synthetic-outline.txt','mimeType':'text/plain','buffer':source},'category':'financials','application_id':str(aid),'grant_id':'1'}).json()
    def wait_run(kind):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            rows=api('GET',f'/api/applications/{aid}/sources').json()['runs'];r=next((x for x in rows if x['kind']==kind),None)
            if r and r['status']=='completed':return r
            if r and r['status']=='failed':
                if r['attempts']>=3:raise AssertionError('Real '+kind+' job failed: '+r['error'])
                api('POST',f'/api/applications/{aid}/sources/runs/{r["id"]}/retry',data={})
            page.wait_for_timeout(1000)
        raise AssertionError('Real '+kind+' job timed out')
    inv=wait_run('inventory')
    assert inv['provider']=='alambda' and inv['output']['items']
    page.goto(frontend+f'/gfm-app/applications/{aid}');page.wait_for_load_state('networkidle');work=page.get_by_role('region',name='Document to application workflow');expect(work).to_be_visible()
    work.get_by_label('Select synthetic-outline.txt',exact=True).check();work.get_by_role('button',name='Analyze selected sources with AI').click();page.wait_for_timeout(500)
    rows=api('GET',f'/api/applications/{aid}/sources').json()['runs'];assert len([r for r in rows if r['kind']=='inventory'])==1,'Automatic and manual requests duplicated the same inventory'
    work.get_by_role('button',name='Generate separate draft',exact=True).first.click();draft=wait_run('draft')
    page.reload();page.wait_for_load_state('networkidle');work=page.get_by_role('region',name='Document to application workflow')
    work.get_by_text(f'Draft #{draft["id"]} ·',exact=False).click()
    downloaded=[]
    for fmt in ('TXT','DOCX'):
        with page.expect_download() as download:work.get_by_role('button',name=f'Download labelled {fmt} draft').click()
        path=out/f'actual-ui-draft.{fmt.lower()}';download.value.save_as(path)
        text=path.read_text(encoding='utf-8') if fmt=='TXT' else '\n'.join(p.text for p in Document(path).paragraphs)
        assert 'UNAPPROVED DRAFT' in text and draft['output']['body'] in text;downloaded.append(fmt)
    with page.expect_download() as download:work.get_by_role('button',name='Download review package',exact=True).click()
    path=out/'actual-ui-package.zip';download.value.save_as(path)
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('manifest.json'));assert manifest['package_status']=='INCOMPLETE' and not any(n.startswith('answers/') for n in z.namelist())
    viewports=[]
    for width in (1440,390):
        page.set_viewport_size({'width':width,'height':960});page.screenshot(path=str(out/f'actual-ui-{width}.png'),full_page=True)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+2');viewports.append(width)
    after=api('GET',f'/api/applications/{aid}').json();assert not after['proposal_text'] and after['amount_requested']==100000 and after['status']=='draft'
    original=api('GET',f'/api/ingestion/documents/{uploaded["id"]}/original').body();assert hashlib.sha256(original).hexdigest()==hashlib.sha256(source).hexdigest()
    doc=api('GET',f'/api/ingestion/documents/{uploaded["id"]}').json();assert doc['status']=='needs_review' and doc['reviewed_at'] is None
    api('POST','/api/auth/logout',data={});assert context.request.get(backend+f'/api/applications/{aid}/sources').status==401
    result={'native_login_logout':True,'real_http_backend_no_response_fixtures':True,'real_alambda':True,'application_id':aid,'inventory_id':inv['id'],'inventory_items':len(inv['output']['items']),
        'draft_id':draft['id'],'draft_characters':len(draft['output']['body']),'draft_validation':draft['output']['validation'],'unapproved_downloads_reopened':downloaded,
        'package_status':manifest['package_status'],'viewports':viewports,'automatic_manual_dedup':True,'source_still_unreviewed':True,'main_proposal_unchanged':True,'original_hash_unchanged':True,'invalid_session_rejected':True}
    (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));b.close()
