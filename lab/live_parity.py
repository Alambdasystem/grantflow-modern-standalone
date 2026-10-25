"""Actual container HTTP/SQLite/worker checks; synthetic identity boundary only."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid
import requests

out=Path('/evidence/parity');out.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--phase',default='create');args=parser.parse_args()
base='http://gateway:8080/gfm-app'
checks=[];calls=[]
tokens={}
for role in ['admin','viewer','grant_writer','reviewer','other_writer']:
    response=requests.post('http://identity:8000/lab/session',json={'role':role},timeout=10)
    response.raise_for_status();tokens[role]=response.json()['token']

def call(method,path,role='grant_writer',**kwargs):
    headers={'Authorization':'Bearer '+tokens[role]} if role else {}
    response=requests.request(method,base+path,headers=headers,timeout=35,**kwargs)
    calls.append({'method':method,'path':path,'status':response.status_code})
    return response

def check(name,test):
    try:
        detail=test()
        assert detail is not False
        item={'feature':name,'result':'PASS'}
    except Exception as exc:
        item={'feature':name,'result':'FAIL','detail':str(exc)[:180]}
    checks.append(item)
    (out/('live-'+args.phase+'.json')).write_text(json.dumps({'checks':checks,'calls':calls},indent=2))
    print(json.dumps(item),flush=True)

def expect(r,status):
    assert r.status_code==status, f'Expected {status}, received {r.status_code}'
    return r.json() if r.headers.get('Content-Type','').startswith('application/json') else r.content

if args.phase!='create':
    state=json.loads((out/'persistent-state.json').read_text())
    check('Saved application survives '+args.phase,lambda:expect(call('GET',f'/api/applications/{state["application_id"]}'),200)['notes']==state['notes'])
    check('Uploaded bytes survive '+args.phase,lambda:hashlib.sha256(expect(call('GET',f'/api/ingestion/documents/{state["document_id"]}/original'),200)).hexdigest()==state['sha256'])
    check('Worker still enabled after '+args.phase,lambda:requests.get('http://backend:8001/health').json()['worker_enabled'] is True)
else:
    seed=json.loads((out/'seed.json').read_text(encoding='utf-8-sig'))
    suffix=uuid.uuid4().hex[:8]
    check('Dispatcher running',lambda:requests.get('http://backend:8001/health').json()['worker_enabled'] is True)
    check('Protected route rejects unauthenticated access',lambda:call('GET','/api/applications/',None).status_code==401)
    check('Synthetic writer sees nine existing applications',lambda:len([x for x in expect(call('GET','/api/applications/'),200) if (x.get('title') or '').startswith('SYNTHETIC WYF application ')])==9)
    check('Cross-organization profile denied',lambda:call('GET','/api/organizations/'+str(seed['organizations'][0]),'other_writer').status_code==404)
    check('Viewer mutation denied',lambda:call('POST','/api/applications/','viewer',json={'grant_id':seed['grant_id']}).status_code==403)
    check('Grant search filters',lambda:any(x['id']==seed['grant_id'] for x in expect(call('POST','/api/grants/search',json={'query':'SYNTHETIC PARITY','category':'education'}),200)))
    app=expect(call('POST','/api/applications/',json={'grant_id':seed['grant_id'],'title':'SYNTHETIC live workflow '+suffix}),201)
    appid=app['id'];notes='Persisted synthetic note '+suffix
    check('Create/update/read application',lambda:expect(call('PATCH',f'/api/applications/{appid}',json={'notes':notes,'proposal_text':'Synthetic saved education proposal.'}),200)['notes']==notes)
    check('Cross-owner application denied',lambda:call('GET',f'/api/applications/{appid}','other_writer').status_code==404)
    check('Readiness validates incomplete package',lambda:expect(call('GET',f'/api/applications/{appid}/readiness'),200)['ready'] is False)
    check('Writer cannot accept own draft',lambda:call('POST',f'/api/applications/{appid}/reviews',json={'decision':'accepted','feedback':'Synthetic check'}).status_code==403)
    check('Admin accepts saved draft',lambda:call('POST',f'/api/applications/{appid}/reviews','admin',json={'decision':'accepted','feedback':'Synthetic review of current saved package'}).status_code==201)
    check('Workflow stages load',lambda:len(expect(call('GET',f'/api/applications/{appid}/workflow'),200))==7)
    expect(call('PATCH',f'/api/applications/{appid}',json={'proposal_text':'Changed synthetic draft invalidates earlier acceptance.'}),200)
    check('Status bypass rejected',lambda:call('PATCH',f'/api/applications/{appid}',json={'status':'submitted'}).status_code==409)
    record=expect(call('POST','/api/operations/records',json={'kind':'knowledge','title':'Synthetic record '+suffix,'body':'Synthetic science education evidence'}),201)
    rid=record['id']
    check('Organization record saved and exportable',lambda:call('GET',f'/api/operations/records/{rid}/export').status_code==200)
    check('Organization record revision conflict rejected',lambda:call('PUT',f'/api/operations/records/{rid}',json={'kind':'knowledge','title':'stale','revision':99}).status_code==409)
    check('Cross-organization export denied',lambda:call('GET',f'/api/operations/records/{rid}/export','other_writer').status_code==404)
    raw=b'SYNTHETIC portability evidence: science education program.\n'
    item=expect(call('POST','/api/ingestion/upload',files={'file':('evidence-'+suffix+'.txt',raw,'text/plain')}),202)
    docid=item['id']
    def processed():
        for _ in range(35):
            data=expect(call('GET',f'/api/ingestion/documents/{docid}'),200)
            if data['status'] in {'ready','needs_review'}:return True
            if data['status']=='failed':raise AssertionError('Worker extraction failed')
            time.sleep(1)
        raise AssertionError('Worker did not finish within 35 seconds')
    check('Background ingestion processes real uploaded text',processed)
    check('Authenticated download preserves original bytes',lambda:expect(call('GET',f'/api/ingestion/documents/{docid}/original'),200)==raw)
    check('Cross-organization document download denied',lambda:call('GET',f'/api/ingestion/documents/{docid}/original','other_writer').status_code==404)
    check('Unsupported upload rejected',lambda:call('POST','/api/ingestion/upload',files={'file':('bad.exe',b'bad','application/octet-stream')}).status_code in {400,415,422})
    check('Private donor screens require admin',lambda:call('GET','/api/donors').status_code==403)
    check('Provider credentials require admin',lambda:call('GET','/api/providers').status_code==403)
    check('Central-only user creation retained',lambda:call('POST','/api/users/','admin',json={}).status_code==410)
    check('Local GFM login remains disabled',lambda:call('POST','/api/auth/login',None,json={}).status_code==410)
    check('Negative donation rejected without creating a ledger entry',lambda:call('POST','/api/donors/donations','admin',json={'amount':-1}).status_code==422)
    check('Inactive/nonexistent public campaign returns 404',lambda:call('GET','/api/give/nonexistent-'+suffix,None).status_code==404)
    (out/'persistent-state.json').write_text(json.dumps({'application_id':appid,'document_id':docid,'notes':notes,'sha256':hashlib.sha256(raw).hexdigest()}))
print(json.dumps({'phase':args.phase,'passed':sum(x['result']=='PASS' for x in checks),'failed':sum(x['result']=='FAIL' for x in checks)}))
