"""Visible saved organization, foundation, donor, campaign and logout workflows."""
import json
from pathlib import Path
import uuid
from playwright.sync_api import sync_playwright,expect
out=Path('/evidence/parity');results=[];campaign={};suffix=uuid.uuid4().hex[:8]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox']);context=browser.new_context();page=context.new_page()
    page.on('dialog',lambda dialog:dialog.dismiss())
    page.goto('http://gateway:8080/auth/login');page.get_by_role('button',name='Enter as synthetic administrator').click();page.wait_for_url('**/gfm-app/dashboard')
    def run(name,fn):
        try:fn();result={'feature':name,'result':'PASS'}
        except Exception as exc:result={'feature':name,'result':'FAIL','detail':str(exc)[:180]}
        results.append(result);(out/'browser-extended.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
    def field(label):return page.locator('label').filter(has_text=label).first.locator('..').locator('input').first
    def settings():
        page.goto('http://gateway:8080/gfm-app/settings');expect(page.get_by_placeholder('Organization Name')).to_have_value('SYNTHETIC PARITY WYF');target=page.get_by_placeholder('Mission Statement');target.fill('SYNTHETIC visible mission '+suffix)
        with page.expect_response(lambda r:'/api/organizations/me' in r.url and r.request.method=='PATCH') as response:page.get_by_role('button',name='Save Profile').click()
        assert response.value.status==200,'Save profile returned '+str(response.value.status)
        assert response.value.json()['mission']=='SYNTHETIC visible mission '+suffix
        page.reload();expect(target).to_have_value('SYNTHETIC visible mission '+suffix)
    run('Visible organization edit -> save -> reload',settings)
    def foundation():
        page.goto('http://gateway:8080/gfm-app/foundations');page.get_by_role('button',name='Add',exact=True).click();field('Name *').fill('SYNTHETIC UI Foundation '+suffix)
        with page.expect_response(lambda r:r.url.endswith('/api/foundations') and r.request.method=='POST') as response:page.get_by_role('button',name='Add Foundation',exact=True).click()
        assert response.value.status==201
        page.get_by_text('SYNTHETIC UI Foundation '+suffix,exact=True).first.wait_for()
    run('Visible foundation creation -> saved detail',foundation)
    def donor():
        page.goto('http://gateway:8080/gfm-app/donors');page.get_by_role('button',name='Add',exact=True).click();field('First Name').fill('SYNTHETIC'+suffix);field('Last Name').fill('Review')
        with page.expect_response(lambda r:r.url.endswith('/api/donors') and r.request.method=='POST') as response:page.get_by_role('button',name='Add Donor',exact=True).click()
        assert response.value.status==201
    run('Visible donor creation -> stored record',donor)
    def create_campaign():
        page.goto('http://gateway:8080/gfm-app/donors');page.get_by_role('button',name='campaigns',exact=True).click();page.get_by_role('button',name='Add',exact=True).click();field('Campaign Name *').fill('SYNTHETIC UI Campaign '+suffix)
        with page.expect_response(lambda r:r.url.endswith('/api/donors/campaigns') and r.request.method=='POST') as response:page.get_by_role('button',name='Create Campaign',exact=True).click()
        assert response.value.status==201
        campaign.update(response.value.json());(out/'public-campaign.json').write_text(json.dumps({'slug':campaign['slug']}))
    run('Visible campaign creation -> public share slug',create_campaign)
    def public():
        anonymous=browser.new_context();visitor=anonymous.new_page()
        visitor.goto('http://gateway:8080/gfm-app/give/'+campaign['slug']);visitor.wait_for_timeout(1500)
        assert '/gfm-app/give/' in visitor.url,'Public giving incorrectly redirects to sign-in'
        visitor.get_by_text(campaign['name'],exact=True).first.wait_for(timeout=5000);anonymous.close()
    run('Anonymous public campaign remains accessible',public)
    def logout():
        page.goto('http://gateway:8080/gfm-app/dashboard')
        with page.expect_response(lambda r:'/api/auth/logout' in r.url and r.request.method=='POST') as response:page.get_by_role('button',name='Sign Out',exact=True).click()
        assert response.value.status==200,'Logout returned '+str(response.value.status)
        page.wait_for_url('**/auth/login?**',timeout=10000)
        assert not page.evaluate("localStorage.getItem('authToken')")
    run('Visible sign-out -> revoked session -> login',logout)
    browser.close()
