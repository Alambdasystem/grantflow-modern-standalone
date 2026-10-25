"""Fill safe positive HTTP-contract coverage gaps with synthetic lab data only."""
import json
from pathlib import Path
import uuid
import requests
out=Path('/evidence/parity');base='http://gateway:8080/gfm-app';events=[];checks=[]
seed=json.loads((out/'seed.json').read_text(encoding='utf-8-sig'));state=json.loads((out/'persistent-state.json').read_text());appid=state['application_id'];grantid=seed['grant_id']
tokens={role:requests.post('http://identity:8000/lab/session',json={'role':role}).json()['token'] for role in ['grant_writer','admin','viewer']}
def call(method,path,expected=200,role='grant_writer',**kwargs):
    r=requests.request(method,base+path,headers={'Authorization':'Bearer '+tokens[role]},timeout=25,**kwargs)
    events.append({'method':method,'path':path.split('?')[0],'status':r.status_code})
    checks.append({'feature':method+' '+path,'result':'PASS' if r.status_code==expected else 'FAIL','expected':expected,'actual':r.status_code})
    (out/'route-contracts.json').write_text(json.dumps({'checks':checks,'calls':events},indent=2))
    return r
r=requests.get('http://backend:8001/health');events.append({'method':'GET','path':'/health','status':r.status_code})
call('POST','/api/grant-planning',json={'grant_id':grantid})
for path in [f'/api/applications/{appid}/reviews',f'/api/applications/{appid}/documents','/api/grants/',f'/api/grants/{grantid}',
             '/api/grants/categories/list',f'/api/grants/{grantid}/requirements',f'/api/grant-planning?grant_id={grantid}',
             '/api/operations/alignment-runs','/api/renewals/due','/api/auth/me']:
    call('GET',path)
for path in ['/api/donors','/api/donors/campaigns/list','/api/foundations','/api/providers','/api/organizations/','/api/users/']:
    call('GET',path,role='admin')
foundation=call('POST','/api/foundations',201,'admin',json={'name':'SYNTHETIC route-contract '+uuid.uuid4().hex[:8]})
if foundation.status_code==201:call('GET',f'/api/foundations/{foundation.json()["id"]}/grants',role='admin')
call('POST','/api/organizations/',201,'admin',json={'name':'SYNTHETIC route-contract organization '+uuid.uuid4().hex[:8]})
call('POST','/api/ai/match-grants')
call('POST',f'/api/applications/{appid}/workflow/advance')
call('POST',f'/api/applications/{appid}/documents',files={'file':('synthetic-associated.txt',b'Synthetic associated evidence','text/plain')})
call('POST','/api/auth/logout',role='viewer')
print(json.dumps({'checks':len(checks),'failed':sum(c['result']=='FAIL' for c in checks)}))
