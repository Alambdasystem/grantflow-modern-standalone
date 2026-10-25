"""Actual HTTP multipart boundary, synthetic bytes, then delete the synthetic source."""
import json
from pathlib import Path
import uuid
import requests
base='http://gateway:8080/gfm-app'
tokens={r:requests.post('http://identity:8000/lab/session',json={'role':r}).json()['token'] for r in ['grant_writer','admin']}
size=20*1024*1024;raw=b'SYNTHETIC\n'*(size//10)+b'x'*(size%10)
assert len(raw)==size
header={'Authorization':'Bearer '+tokens['grant_writer']}
r=requests.post(base+'/api/ingestion/upload',headers=header,files={'file':('boundary-'+uuid.uuid4().hex+'.txt',raw)},timeout=60)
result=[{'feature':'20 MiB file plus multipart overhead accepted','result':'PASS' if r.status_code==202 else 'FAIL','status':r.status_code}]
if r.status_code==202:
    deleted=requests.delete(base+'/api/ingestion/documents/'+str(r.json()['id']),headers={'Authorization':'Bearer '+tokens['admin']},timeout=30)
    result.append({'feature':'Synthetic boundary document removed','result':'PASS' if deleted.status_code==200 else 'FAIL'})
r=requests.post(base+'/api/ingestion/upload',headers=header,files={'file':('oversize.txt',raw+b'x')},timeout=60)
result.append({'feature':'20 MiB plus one byte rejected','result':'PASS' if r.status_code==413 else 'FAIL','status':r.status_code})
Path('/evidence/parity/upload-boundary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
