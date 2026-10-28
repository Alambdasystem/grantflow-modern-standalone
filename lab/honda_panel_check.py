"""Read-only browser presentation fixtures. No live records or proposal actions."""
from playwright.sync_api import sync_playwright,expect
base='http://127.0.0.1:5213'
names=['Honda_and_Honda_USA_Foundation_2027_Programmatic_Pillar_Awards.pdf','Grant Outline.docx','WYF_ThriveForce_Honda_2027_Budget_Final_With_Notes.xlsx','official-faq.pdf']
data={'total_program_budget':425000,'other_funding_needed_not_secured':325000,'deadline_local':'2026-10-31 23:59 Pacific Time','deadline_timezone_caveat':'FAQ also uses PST; confirm exact offset.','character_checks':[{'section':title,'characters_in_supplied_draft':count,'outline_limit_under':2000,'exceeds_outline_limit':True} for title,count in [('Short-term goals',2169),('Long-term goals',2160),('Top three benefits',2011)]]}
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome');context=browser.new_context();context.add_init_script("localStorage.setItem('gfm_session_hint','1')");page=context.new_page();mutations=[];errors=[];fail_files=False
 page.on('pageerror',lambda e:errors.append(str(e)))
 def fixture(route):
  path=route.request.url.split('/api/',1)[-1].split('?')[0];result={}
  if route.request.method not in ('GET','HEAD'):mutations.append((route.request.method,path))
  if path=='auth/me':result={'role':'grant_writer','username':'synthetic'}
  elif path in ('applications/47','applications/48'):
   honda=path.endswith('47');result={'id':47 if honda else 48,'organization_id':1,'applicant_id':5,'grant_id':72 if honda else 1,'title':'Synthetic onboarding' if honda else 'Synthetic other funder','status':'draft','amount_requested':100000,'proposal_text':'','form_data':{'honda_2027_onboarding':data} if honda else {}}
  elif path.endswith('/workflow'):result=[]
  elif path.endswith('/reviews'):result=[]
  elif path.endswith('/readiness'):result={'ready':False,'completed':4,'total':15,'warnings':[],'note':'Synthetic saved-data check','latest_review':None,'checks':[{'key':'requirements_known','label':'Funder requirements available','passed':True,'detail':'Synthetic guidance only'},{'key':'proposal','label':'Saved proposal','passed':False,'detail':'Blank'}]}
  elif path in ('grants/72','grants/1'):result={'id':72 if path.endswith('72') else 1,'title':'Synthetic source','funding_agency':'Synthetic funder','requirements':[],'meta':{}}
  elif path.endswith('/requirements'):result={'status':'none'}
  elif path=='ingestion/documents':
   if fail_files:route.fulfill(status=503,json={'detail':'Synthetic unavailable'});return
   result=[{'id':21+i,'name':name,'status':'ready' if name.endswith('.pdf') else 'needs_review','application_id':47,'grant_id':72,'current':True,'error':None} for i,name in enumerate(names)]
  elif path=='operations/records':result=[{'data':{'application_id':47,'grant_id':72,'category':'grant_onboarding','checklist':[{'label':'Verify complete official questions and required uploads','done':False,'evidence':'Portal confirmation missing','owner':'Synthetic reviewer'}]}}]
  route.fulfill(status=200,json=result)
 page.route('**/api/**',fixture)
 for width in (1440,390):
  page.set_viewport_size({'width':width,'height':900});page.goto(base+'/gfm-app/applications/47');page.wait_for_load_state('networkidle')
  panel=page.get_by_role('region',name='Honda onboarding',exact=True)
  expect(panel).to_be_visible();expect(panel).to_contain_text('Onboarding draft — verification pending.')
  for amount in ('$100,000','$425,000','$325,000'):expect(panel).to_contain_text(amount)
  expect(panel).to_contain_text('not committed funding')
  expect(panel.get_by_text('Ready',exact=True)).to_have_count(2)
  expect(panel.get_by_text('Awaiting extraction review',exact=True)).to_have_count(2)
  for name in names:expect(panel.get_by_text(name,exact=True)).to_be_visible()
  for count in ('2,169','2,160','2,011'):expect(panel).to_contain_text(count)
  expect(panel).to_contain_text('60 earned credentials');expect(panel).to_contain_text('85 pursuing or earning')
  expect(page.get_by_role('heading',name='Onboarding completeness',exact=True)).to_be_visible()
  expect(page.get_by_text('4/15 saved-data checks passed',exact=False)).to_be_visible()
  expect(page.get_by_role('button',name='Scan grants.gov',exact=True)).to_have_count(0)
  expect(page.locator('textarea')).to_have_count(0)
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
  print('PASS: Honda panel, four live-status fixture files, funding, caveats and collapsed blank editor at',width,flush=True)
 page.get_by_role('button',name='Open blank proposal editor',exact=True).click();expect(page.locator('textarea')).to_have_value('')
 page.goto(base+'/gfm-app/applications/48');expect(page.get_by_role('button',name='Scan grants.gov',exact=True)).to_be_visible();expect(page.get_by_role('heading',name='Application readiness',exact=True)).to_be_visible();expect(page.locator('textarea')).to_be_visible()
 print('PASS: other funder retains ordinary editor, readiness and requirements controls',flush=True)
 fail_files=True;page.goto(base+'/gfm-app/applications/47');expect(page.get_by_text('Attachment status unavailable.',exact=False)).to_be_visible(timeout=10000);expect(page.get_by_role('region',name='Honda onboarding').get_by_text('Ready',exact=True)).to_have_count(0)
 assert not mutations,mutations
 assert not errors,errors
 print('PASS: failed status request stays unknown; no API mutations or browser errors',flush=True)
 browser.close()
