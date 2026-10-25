"""Actual financial upload/review/index/delete and parser-failure/retry over lab HTTP."""
import json
from pathlib import Path
import time
import uuid
import requests

base='http://gateway:8080/gfm-app';out=Path('/evidence/parity/document-lifecycle.json');checks=[];tokens={}
for role in ['grant_writer','reviewer','viewer','admin']:
    tokens[role]=requests.post('http://identity:8000/lab/session',json={'role':role}).json()['token']
def request(method,path,role='grant_writer',**kwargs):
    return requests.request(method,base+path,headers={'Authorization':'Bearer '+tokens[role]},timeout=15,**kwargs)
def check(name,value):
    checks.append({'feature':name,'result':'PASS' if value else 'FAIL'});out.write_text(json.dumps(checks,indent=2));assert value,name
def poll(id):
    for _ in range(35):
        r=request('GET',f'/api/ingestion/documents/{id}');assert r.status_code==200
        result=r.json()
        if result['status'] not in {'queued','processing'}:return result
        time.sleep(1)
    raise AssertionError('Extraction timeout')
suffix=uuid.uuid4().hex[:8]
raw=b'Account,Amount\nSYNTHETIC revenue,1234.50\n'
filename='financial-'+suffix+'.csv'
r=request('POST','/api/ingestion/upload',files={'file':(filename,raw,'text/csv')},data={'category':'financials'});assert r.status_code==202
item=poll(r.json()['id']);id=item['id']
check('Real CSV worker extraction requires review',item['status']=='needs_review' and '1234.50' in item['extracted']['text'])
check('Viewer cannot approve',request('POST',f'/api/ingestion/documents/{id}/review','viewer',json={'confirmed':True,'sha256':item['sha256']}).status_code==403)
r=request('POST',f'/api/ingestion/documents/{id}/corrections','reviewer',json={'text':item['extracted']['text']+'\nSynthetic reviewer confirmed source.', 'reason':'Synthetic source verification','revision':item['extraction_revision']})
check('Reviewer correction saves audit revision',r.status_code==200)
item=request('GET',f'/api/ingestion/documents/{id}').json()
r=request('POST',f'/api/ingestion/documents/{id}/review','reviewer',json={'confirmed':True,'sha256':item['sha256'],'revision':item['extraction_revision']})
check('Reviewer approves current corrected extraction',r.status_code==200 and r.json()['status']=='ready')
r=request('POST','/api/ingestion/upload',files={'file':(filename,raw,'text/csv')},data={'category':'financials'})
check('Duplicate upload is deduplicated',r.status_code==202 and r.json()['duplicate'] is True)
check('Approved financial evidence searchable',any(x['document']['id']==id for x in request('GET','/api/ingestion/search?q=1234.50').json()))
check('Non-admin source deletion denied',request('DELETE',f'/api/ingestion/documents/{id}').status_code==403)
check('Administrator source deletion supported',request('DELETE',f'/api/ingestion/documents/{id}','admin').status_code==200)
check('Deleted original download blocked',request('GET',f'/api/ingestion/documents/{id}/original').status_code==410)
bad=request('POST','/api/ingestion/upload',files={'file':('broken-'+suffix+'.pdf',b'not-a-pdf','application/pdf')});assert bad.status_code==202
failed=poll(bad.json()['id'])
check('Malformed PDF records actual worker failure',failed['status']=='failed')
check('Failed extraction permits explicit retry',request('POST',f'/api/ingestion/documents/{failed["id"]}/retry').status_code==200)
response=request('POST','/api/auth/logout','viewer')
check('Backend logout revokes fixture session',response.status_code==200 and request('GET','/api/auth/me','viewer').status_code==401)
print(json.dumps({'checks':len(checks),'failed':sum(x['result']=='FAIL' for x in checks)}))

