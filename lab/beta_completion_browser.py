"""Disposable beta browser acceptance. Mount only a protected /private test manifest; never production account credentials. See docs/BETA-SOURCE-VERIFICATION-2026-10-27.md. External submissions and email are not exercised."""
import json,time,hashlib,secrets,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('/private');data=json.loads((root/'credentials.json').read_text());base=data['base'];mode=sys.argv[1];out=[]
assert base in {'https://grantflow-modern-staging.onrender.com','http://127.0.0.1:5210'}
assert data['prefix'].startswith('beta_verify_') and all(a['username'].startswith(data['prefix']+'_') for a in data['accounts'].values())
def record(label,fn):
 start=time.monotonic()
 try:fn()
 except Exception as e:
  (root/'live-failure.txt').write_text(__import__('traceback').format_exc());print(json.dumps({'test':label,'result':'FAIL','type':type(e).__name__}),flush=True);raise SystemExit(1)
 out.append({'test':label,'result':'PASS','seconds':round(time.monotonic()-start,3)});(root/('live-'+mode+'.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out[-1]),flush=True)
with sync_playwright()as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);contexts={};page=None;context=None
 def login(role):
  global page,context
  context=browser.new_context();contexts[role]=context;page=context.new_page();a=data['accounts'][role]
  page.goto(base+'/auth/login');page.get_by_label('Username',exact=True).fill(a['username']);page.get_by_label('Password',exact=True).fill(a['password']);page.get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('heading',name='Mission Control Dashboard').wait_for(timeout=40000)
 def h(c=None):return {'Origin':base,'X-CSRF-Token':next(x['value']for x in (c or context).cookies()if x['name']=='__Host-gfm_csrf')}
 def req(method,path,body=None,status=200,c=None,**kw):
  c=c or context;r=c.request.fetch(base+'/gfm-app'+path,method=method,headers=h(c)if method!='GET'else{},data=body,timeout=120000,**kw)
  assert r.status==status,(path,r.status,r.text()[:300]);return r.json()if r.body()else None
 if mode=='pre':
  record('Visible native writer login before deployment',lambda:login('grant_writer'));state={'title':'QA TEST - beta completion - DO NOT SUBMIT '+data['nonce']}
  def create():
   page.goto(base+'/gfm-app/applications');page.get_by_role('button',name='New Application',exact=True).click();page.locator('select').first.select_option('35');page.get_by_placeholder('Application Title',exact=True).fill(state['title']);page.get_by_role('button',name='Create',exact=True).click();page.get_by_text(state['title'],exact=True).first.wait_for(timeout=30000)
   state['application_id']=next(a['id']for a in req('GET','/api/applications/')if a['title']==state['title'])
   req('PATCH','/api/applications/'+str(state['application_id']),{'amount_requested':100,'proposal_text':'Synthetic human draft retained across deployment.','budget_narrative':'[information needed] Document the requested costs.'})
  record('Visible synthetic application creation and saved human draft',create)
  raw=b'SYNTHETIC beta completion education evidence. No real participant data.'
  def upload():
   page.goto(base+f'/gfm-app/documents?application_id={state["application_id"]}');select=page.locator('select:has(option[value="'+str(state['application_id'])+'"])');select.wait_for();assert select.input_value()==str(state['application_id']);page.locator('input[type=file]').set_input_files({'name':'synthetic-beta-completion.txt','mimeType':'text/plain','buffer':raw});page.get_by_role('button',name='Upload and process',exact=True).click()
   until=time.monotonic()+90
   while time.monotonic()<until:
    docs=req('GET','/api/ingestion/documents');doc=next((d for d in docs if d['name']=='synthetic-beta-completion.txt'),None)
    if doc and doc['status']=='ready':break
    time.sleep(1)
   assert doc and doc['status']=='ready';state['document_id']=doc['id'];state['sha256']=hashlib.sha256(raw).hexdigest()
  record('Visible application-selected TXT upload and actual extraction worker',upload)
  context.storage_state(path=str(root/'browser-state.json'));(root/'state.json').write_text(json.dumps(state))
 else:
  state=json.loads((root/'state.json').read_text());context=browser.new_context(storage_state=str(root/'browser-state.json'));contexts['grant_writer']=context;page=context.new_page();app='/api/applications/'+str(state['application_id'])
  def persistence():
   assert req('GET','/api/auth/me')['role']=='grant_writer';a=req('GET',app);assert a['title']==state['title'] and a['proposal_text']=='Synthetic human draft retained across deployment.'
   response=context.request.get(base+f'/gfm-app/api/ingestion/documents/{state["document_id"]}/original');assert response.ok and hashlib.sha256(response.body()).hexdigest()==state['sha256']
   assert req('GET','/api/ingestion/search?q=education')
  record('Persisted session, application, extracted search and exact download after deployment',persistence)
  def sources():
   rows=req('GET','/api/grants/');assert next(x for x in rows if x['id']==35)['source_review']['status']=='verified'
   bad=req('GET','/api/grants/1/requirements');assert bad['status']=='error' and not bad['requirements'] and 'Needs source verification' in bad['error']
   good=req('GET','/api/grants/35/requirements');assert good['requirements']['opp_id']==360851 and good['requirements']['package_complete'] is False
   assert req('GET',app+'/readiness')['ready'] is False
  record('Repaired exact source, withheld County package and truthful incomplete readiness',sources)
  def validation():
   req('PATCH',app,{'budget_narrative':'- Staff: $1\n- Supplies: $2\nTotal Requested: $100'},422)
   req('POST','/api/operations/records',{'kind':'draft','title':'QA TEST invalid','category':'arbitrary','application_id':state['application_id'],'body':'Total Requested: $200'},422)
   assert req('GET',app)['proposal_text']=='Synthetic human draft retained across deployment.'
  record('Alternate save routes reject invalid budget without overwriting human text',validation)
  def worker_retry():
   raw=b'SYNTHETIC beta completion education evidence. No real participant data.'
   r=context.request.post(base+'/gfm-app/api/ingestion/upload',headers=h(),multipart={'file':{'name':'synthetic-beta-completion.txt','mimeType':'text/plain','buffer':raw},'application_id':str(state['application_id'])});assert r.ok and r.json()['duplicate']
   r=context.request.post(base+'/gfm-app/api/ingestion/upload',headers=h(),multipart={'file':{'name':'synthetic-failure.pdf','mimeType':'application/pdf','buffer':b'not a PDF'},'application_id':str(state['application_id'])});assert r.ok;did=r.json()['id']
   def failed():
    until=time.monotonic()+60
    while time.monotonic()<until:
     item=req('GET','/api/ingestion/documents/'+str(did))
     if item['status']=='failed':return item
     time.sleep(1)
    raise AssertionError('Parser failure was not recorded')
   assert failed()['retry_at'];req('POST','/api/ingestion/documents/'+str(did)+'/retry')
   item=failed();assert sum(x.get('action')=='failed' for x in item['history'])>=2
  record('Actual worker parser failure/retry and duplicate upload prevention',worker_retry)

  writer=context
  record('Visible standalone administrator login',lambda:login('admin'));admin=context
  def account_admin():
   page.goto(base+'/gfm-app/accounts');page.get_by_role('heading',name='Accounts and invitations').wait_for(timeout=30000)
   name=data['prefix']+'_invited_'+secrets.token_hex(3)
   payload={'email':name+'@example.com','organization_id':data['organizations'][0],'role':'viewer'}
   invite=req('POST','/api/auth/invitations',payload,c=admin);token=invite['url'].split('#invite=')[1];c=browser.new_context();password=secrets.token_urlsafe(32)
   r=c.request.post(base+'/gfm-app/api/auth/accept',headers={'Origin':base},data={'token':token,'username':name,'password':password});assert r.ok
   assert c.request.post(base+'/gfm-app/api/auth/accept',headers={'Origin':base},data={'token':token,'username':name,'password':password}).status==403
   r=c.request.post(base+'/gfm-app/api/auth/login',headers={'Origin':base},data={'username':name,'password':password});assert r.ok
   user=next(u for u in req('GET','/api/users/',c=admin)if u['username']==name);req('PATCH','/api/auth/accounts/'+str(user['id']),{'is_active':False,'role':'viewer'},c=admin)
   assert c.request.get(base+'/gfm-app/api/auth/me').status==401
   req('PATCH','/api/auth/accounts/'+str(user['id']),{'is_active':True,'role':'viewer'},c=admin);c.close()
  record('Admin invitation, one-use acceptance, disable/revocation and reenable of disposable account',account_admin)
  def providers():
   rows=req('GET','/api/providers',c=admin);target=next((r for r in rows if r['key']=='fluxx' and r.get('credential') is None),None)
   assert target is not None,'Unused sandbox-only provider slot unavailable'
   value=req('PUT','/api/providers/fluxx',{'username':data['prefix'],'password':'Synthetic fixture only - never connect','notes':'QA TEST disposable configuration; do not connect'},c=admin);assert value['has_credentials'] and 'Synthetic fixture only'not in str(value)
   response=admin.request.delete(base+'/gfm-app/api/providers/fluxx',headers=h(admin));assert response.status in (200,204)
  record('Provider settings create/redaction/delete; no external login attempted',providers)
  def review_renewal():
   req('POST',app+'/reviews',{'decision':'accepted','feedback':'QA TEST internal human review, no funder submission'},201,c=admin)
   req('PATCH',app,{'status':'in_review'},c=writer);req('PATCH',app,{'status':'approved','renewal_due_date':'2026-10-25T12:00:00Z'},c=admin)
   child=req('POST',f'/api/renewals/{state["application_id"]}/draft',c=writer);assert req('POST',f'/api/renewals/{state["application_id"]}/draft',c=writer)['id']==child['id']
   req('PATCH','/api/applications/'+str(child['id']),{'proposal_text':'QA TEST reviewed internal renewal preparation.'},c=writer)
   req('POST','/api/applications/'+str(child['id'])+'/reviews',{'decision':'accepted','feedback':'QA TEST renewal preparation only'},201,c=admin)
   req('POST',f'/api/renewals/{state["application_id"]}/complete',c=writer,status=403)
   assert req('POST',f'/api/renewals/{state["application_id"]}/complete',c=admin)['completed']
   assert req('GET',app,c=writer)['renewal_due_date']is None
   assert all(j['job_type']=='ingest' for j in req('GET','/api/automation/jobs',c=writer))
  record('Internal review/status changes and idempotent manual renewal creation/completion',review_renewal)
  record('Visible viewer login',lambda:login('viewer'));viewer=context
  def permissions():
   req('GET',app,c=viewer,status=404);req('POST','/api/applications/',{'grant_id':35,'title':'forbidden'},403,c=viewer);req('GET','/api/providers',c=viewer,status=403)
   page.goto(base+'/gfm-app/providers');page.get_by_role('alert').filter(has_text='administrator access').wait_for(timeout=20000)
   login('other_writer');req('GET',app,status=404);req('GET',f'/api/ingestion/documents/{state["document_id"]}/original',status=404)
  record('Writer/viewer permissions and cross-organization application/file denial',permissions)
  context=writer;page=writer.new_page()
  def ai():
   result=req('POST','/api/ai/generate',{'application_id':state['application_id'],'task':'budget','stream':False,'context':'QA TEST. Use information-needed placeholders only. Do not invent costs, outcomes or eligibility. Preserve the saved requested amount exactly.'},c=writer)
   assert result['draft_id'] and result['saved_to_application']is False
   rows=req('GET','/api/operations/records?kind=draft',c=writer);r=next(r for r in rows if r['id']==result['draft_id']);assert r['body']==result['result']
   updated=req('PUT','/api/operations/records/'+str(r['id']),{'kind':'draft','title':r['title'],'body':r['body']+'\n\nQA TEST human review pending.','revision':r['revision'],**{k:v for k,v in r['data'].items()if k not in ('quality_review',)}},c=writer)
   assert updated['revision']==r['revision']+1 and len(updated['history'])>=2
   export=writer.request.get(base+'/gfm-app/api/operations/records/'+str(r['id'])+'/export');assert export.ok and result['result']in export.text()
   assert req('GET',app,c=writer)['proposal_text']=='Synthetic human draft retained across deployment.'
  record('Real Alambda generation, validation, candidate persistence/history/export and human-draft preservation',ai)
  def mobile():
   for width in (1440,390):
    page.set_viewport_size({'width':width,'height':900})
    for route in ('','/grants','/applications','/documents','/operations','/renewals','/analytics','/settings'):
     page.goto(base+'/gfm-app'+route);page.wait_for_timeout(1000);assert page.locator('body').inner_text().strip();assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'),(width,route)
    page.screenshot(path=str(root/f'ui-{width}.png'),full_page=True)
  record('Desktop and mobile route rendering with no horizontal overflow',mobile)
  def logout():
   old=next(c['value']for c in writer.cookies()if c['name']=='__Host-gfm_session');req('POST','/api/auth/logout',c=writer)
   assert writer.request.get(base+'/gfm-app/api/auth/me').status==401
   replay=p.request.new_context(extra_http_headers={'Cookie':'__Host-gfm_session='+old});assert replay.get(base+'/gfm-app/api/auth/me').status==401;replay.dispose()
  record('Logout and invalid/replayed session rejection',logout)
 browser.close()
