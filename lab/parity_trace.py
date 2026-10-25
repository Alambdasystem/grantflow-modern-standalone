"""Pytest request metadata only: no headers, tokens, payloads or record contents."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
events=[]
current='collection'
def pytest_sessionstart(session):
    from starlette.testclient import TestClient
    original=TestClient.request
    def request(self,method,url,*args,**kwargs):
        response=original(self,method,url,*args,**kwargs)
        events.append({'test':current,'method':method.upper(),'path':urlsplit(str(url)).path,'status':response.status_code})
        return response
    TestClient.request=request
def pytest_runtest_setup(item):
    global current
    current=item.nodeid
def pytest_sessionfinish(session,exitstatus):
    path=os.environ.get('GFM_TRACE_FILE')
    if path:Path(path).write_text(json.dumps(events,indent=2))
