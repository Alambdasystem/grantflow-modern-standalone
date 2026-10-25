"""Real UI route scan plus visible application creation/upload; fixture identity only."""
import json
from pathlib import Path
import uuid
from playwright.sync_api import sync_playwright

out=Path('/evidence/parity');routes=json.loads((out/'page-inventory.json').read_text());seed=json.loads((out/'seed.json').read_text(encoding='utf-8-sig'))
state=json.loads((out/'persistent-state.json').read_text());results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1000})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)[:180]))
    page.goto('http://gateway:8080/auth/login')
    page.get_by_role('button',name='Enter as synthetic administrator').click()
    page.get_by_role('heading',name='Mission Control Dashboard').wait_for()
    for item in routes:
        route=item['route'].replace('[id]',str(state['application_id'])).replace('[slug]','nonexistent-synthetic-campaign')
        before=len(errors)
        try:
            response=page.goto('http://gateway:8080'+route,wait_until='domcontentloaded',timeout=30000)
            page.wait_for_timeout(500)
            results.append({'route':item['route'],'result':'FAIL' if len(errors)>before or (response and response.status>=500) else 'PASS',
                            'scope':'UI render only; integration behavior assessed separately','errors':errors[before:]})
        except Exception as exc:
            results.append({'route':item['route'],'result':'FAIL','detail':str(exc)[:180]})
        (out/'browser-routes.json').write_text(json.dumps(results,indent=2))
    # Login route may redirect; return to application board and perform visible mutation.
    page.goto('http://gateway:8080/gfm-app/applications')
    page.get_by_role('button',name='New Application').click()
    page.locator('select').first.select_option(str(seed['grant_id']))
    title='SYNTHETIC visible UI '+uuid.uuid4().hex[:8]
    page.get_by_placeholder('Application Title').fill(title)
    page.get_by_placeholder('Requested Amount ($)').fill('2000')
    with page.expect_response(lambda r:'/api/applications/' in r.url and r.request.method=='POST',timeout=15000) as created:
        page.get_by_role('button',name='Create',exact=True).click()
    assert created.value.status==201
    page.get_by_text(title,exact=True).wait_for()
    app=created.value.json()
    page.goto('http://gateway:8080/gfm-app/applications/'+str(app['id']))
    page.wait_for_timeout(1000)
    page.screenshot(path=str(out/'visible-created-application.png'),full_page=True)
    page.goto('http://gateway:8080/gfm-app/documents')
    page.locator('input[type=file]').set_input_files({'name':'visible-synthetic.txt','mimeType':'text/plain','buffer':b'SYNTHETIC browser upload education evidence'})
    with page.expect_response(lambda r:'/api/ingestion/upload' in r.url and r.request.method=='POST') as uploaded:
        page.get_by_role('button',name='Upload and process').click()
    assert uploaded.value.status==202
    page.get_by_text('visible-synthetic.txt',exact=False).first.wait_for()
    page.screenshot(path=str(out/'visible-upload.png'),full_page=True)
    (out/'browser-workflows.json').write_text(json.dumps([
        {'feature':'Visible application form -> saved board result -> detail','result':'PASS','application_id':app['id']},
        {'feature':'Visible document selection -> server-accepted upload','result':'PASS','scope':'202 acceptance; worker completion tested separately'}],indent=2))
    browser.close()
print(json.dumps({'routes':len(results),'render_failures':sum(r['result']=='FAIL' for r in results),'visible_saved_workflows':2}))
