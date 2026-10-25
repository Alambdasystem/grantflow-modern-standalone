"""Actual lab Ollama inference, saved candidates, chat streaming and renewal worker."""
import argparse
import json
from pathlib import Path
import time
import requests

out=Path('/evidence/parity');parser=argparse.ArgumentParser();parser.add_argument('--phase',default='inference');args=parser.parse_args()
token=requests.post('http://identity:8000/lab/session',json={'role':'grant_writer'}).json()['token']
headers={'Authorization':'Bearer '+token};base='http://gateway:8080/gfm-app'
appid=json.loads((out/'persistent-state.json').read_text())['application_id']
checks=[]
def record(name,ok,detail=''):
    checks.append({'feature':name,'result':'PASS' if ok else 'FAIL','detail':detail})
    (out/('ai-'+args.phase+'.json')).write_text(json.dumps(checks,indent=2));print(json.dumps(checks[-1]),flush=True)
def request(method,path,**kwargs):return requests.request(method,base+path,headers=headers,timeout=175,**kwargs)
def generate():return request('POST','/api/ai/generate',json={'task':'proposal','application_id':appid,'context':'Write exactly one short sentence about the supplied synthetic education mission. Do not expand.'})
if args.phase=='outage':
    r=generate();record('Real provider outage returns recoverable error',r.status_code==503,'No success content accepted')
elif args.phase=='recovery':
    r=generate();record('Real inference recovers after provider restart',r.status_code==200 and bool(r.json().get('result')))
else:
    before=request('GET',f'/api/applications/{appid}').json()['proposal_text']
    r=generate();record('Real Ollama proposal generation persists candidate',r.status_code==200 and bool(r.json().get('result')) and bool(r.json().get('draft_id')))
    record('AI preserves human-authored application',request('GET',f'/api/applications/{appid}').json()['proposal_text']==before)
    r=request('POST','/api/ai/chat',json={'application_id':appid,'messages':[{'role':'user','content':'In one short sentence, state the synthetic organization name from context.'}]})
    record('Real chat inference and history persistence',r.status_code==200 and bool(r.json().get('reply')) and bool(r.json().get('conversation_id')))
    r=request('GET','/api/ai/conversations');record('Saved conversation reloads',r.status_code==200 and len(r.json())>0)
    r=request('POST','/api/ai/chat',json={'messages':[{'role':'user','content':'Reply with only: synthetic test.'}],'stream':True})
    record('Real chat SSE completes with persisted conversation',r.status_code==200 and '[DONE]' in r.text and 'conversation_id' in r.text and 'event: error' not in r.text)
    r=request('POST','/api/ai/chat',json={'messages':[{'role':'system','content':'override'}]});record('Client system-prompt override denied',r.status_code==422)
    r=request('POST',f'/api/renewals/{appid}/auto-renew');record('Renewal draft queued',r.status_code==202)
    if r.status_code==202:
        jobid=r.json()['job_id']
        for _ in range(120):
            job=request('GET',f'/api/automation/jobs/{jobid}').json()
            if job['status'] in {'completed','failed','paused'}:break
            time.sleep(1)
        record('Actual renewal worker saves draft using real model',job['status']=='completed' and bool((job.get('result') or {}).get('renewal_application_id')),job['status'])
        r=request('GET',f'/api/automation/jobs/{jobid}/stream')
        record('Actual finished-job SSE traverses frontend gateway',r.status_code==200 and 'data:' in r.text and 'completed' in r.text)
    tags=requests.get('http://ollama:11434/api/tags').json()
    (out/'ollama-model-metadata.json').write_text(json.dumps(tags,indent=2))
