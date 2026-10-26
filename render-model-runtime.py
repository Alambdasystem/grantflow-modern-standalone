"""Persistent private Ollama with exact model verification and explicit cold warmup."""
import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

if not os.path.ismount('/var/data'):
    raise RuntimeError('Model service requires a persistent /var/data disk')
Path('/var/data/models').mkdir(parents=True,exist_ok=True)
model=os.environ.get('DEFAULT_MODEL','llama3.2:latest')
expected=os.environ['EXPECTED_MODEL_DIGEST']
if model!='llama3.2:latest':
    raise RuntimeError('This release is approved for llama3.2:latest only')
server=subprocess.Popen(['ollama','serve'])
def stop(*args):
    if server.poll() is None: server.terminate()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
    deadline=time.monotonic()+90
    while True:
        if server.poll() is not None: raise RuntimeError('Model process exited')
        try:
            urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2).close();break
        except OSError:
            if time.monotonic()>deadline: raise RuntimeError('Model socket startup deadline exceeded')
            time.sleep(1)
    subprocess.run(['ollama','pull',model],check=True,timeout=900)
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5) as response:
        tags=json.load(response)['models']
    if not any(m.get('name')==model and m.get('digest')==expected for m in tags):
        raise RuntimeError('Model digest differs from the reviewed model; no substitute is accepted')
    request=urllib.request.Request('http://127.0.0.1:11434/api/generate',method='POST',
        headers={'Content-Type':'application/json'},data=json.dumps({'model':model,'prompt':'','stream':False,'keep_alive':'24h'}).encode())
    with urllib.request.urlopen(request,timeout=600) as response:
        if json.load(response).get('done') is not True: raise RuntimeError('Model warmup failed')
    print('Approved model verified and loaded; application readiness must still be checked.',flush=True)
    server.wait()
    if server.returncode: raise RuntimeError('Model process exited unsuccessfully')
finally:
    stop()
    try: server.wait(timeout=20)
    except subprocess.TimeoutExpired: server.kill();server.wait()
