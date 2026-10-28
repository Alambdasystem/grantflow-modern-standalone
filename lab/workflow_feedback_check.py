"""Isolated browser UI fixtures: errors, delayed upload response and status polling.
No production identity, network integration or grant submission is exercised.
"""
from playwright.sync_api import sync_playwright, expect

base='http://127.0.0.1:5213'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome')
    context=browser.new_context()
    context.add_init_script("localStorage.setItem('gfm_session_hint','1')")
    page=context.new_page();status='draft';creates=[];pending=[]
    def fixture(route):
        path=route.request.url.split('/api/',1)[-1].split('?')[0]
        data=[]
        if path=='auth/me':data={'role':'admin','username':'synthetic'}
        elif path=='grants/':data=[{'id':1,'title':'Synthetic opportunity','status':'active'}]
        elif path=='applications/' and route.request.method=='POST':
            creates.append(route.request.post_data_json)
            route.fulfill(status=422,json={'detail':[{'loc':['body','amount_requested'],'msg':'Synthetic amount validation error'}]});return
        elif path=='applications/':data=[{'id':1,'grant_id':1,'title':'Synthetic review application','status':status}]
        elif path=='ingestion/sources':data={'sources':[],'notice':'Synthetic sources'}
        elif path=='ingestion/monitor':
            data={'counts':{},'oldest_pending_seconds':0,'stale_documents':0,'coordinator_status':'idle',
                  'local_extraction_enabled':True,'alerts':[],'workers':[],'failures':[],'freshness_items':[]}
        elif path=='ingestion/upload':pending.append(route);return
        route.fulfill(status=200,json=data)
    page.route('**/api/**',fixture)
    page.goto(base+'/gfm-app/applications')
    page.get_by_role('button',name='New Application',exact=True).click()
    page.get_by_label('Grant',exact=True).select_option('1')
    page.get_by_label('Application title',exact=True).fill('Retain human entries')
    page.get_by_label('Requested amount',exact=True).fill('-1')
    page.get_by_role('button',name='Create',exact=True).click()
    expect(page.locator('#amount-error')).to_contain_text('zero or greater')
    assert not creates
    page.get_by_label('Requested amount',exact=True).fill('100.25')
    page.get_by_role('button',name='Create',exact=True).click()
    expect(page.locator('#amount-error')).to_contain_text('Synthetic amount validation error')
    expect(page.get_by_label('Application title',exact=True)).to_have_value('Retain human entries')
    expect(page.get_by_label('Requested amount',exact=True)).to_have_value('100.25')
    print('PASS: client amount error, server field mapping and entered values retained')
    status='in_review'
    expect(page.get_by_role('link',name='Synthetic review application',exact=False)).to_be_visible()
    card=page.get_by_role('link',name='Synthetic review application',exact=False).locator('..').locator('..')
    expect(card).to_contain_text('Under Review',timeout=10000)
    print('PASS: externally changed status moves board card without page reload')
    page.goto(base+'/gfm-app/documents')
    page.locator('input[type=file]').set_input_files({'name':'synthetic.txt','mimeType':'text/plain','buffer':b'SYNTHETIC'})
    page.get_by_role('button',name='Upload and process',exact=True).click()
    expect(page.get_by_role('progressbar',name='Document transfer')).to_be_visible()
    expect(page.get_by_role('button',name='Upload and process',exact=True)).to_be_disabled()
    expect(page.get_by_text('Still waiting for the network or server.',exact=False)).to_be_visible(timeout=20000)
    assert len(pending)==1
    pending[0].fulfill(status=503,json={'detail':'Synthetic upload failure; retry is safe'})
    expect(page.get_by_role('status').filter(has_text='Synthetic upload failure')).to_be_visible()
    expect(page.get_by_role('button',name='Upload and process',exact=True)).to_be_enabled()
    assert page.locator('input[type=file]').evaluate('(el)=>el.files[0].name')=='synthetic.txt'
    print('PASS: delayed response has progress/stall feedback, no duplicate request and preserves file after failure')
    browser.close()
