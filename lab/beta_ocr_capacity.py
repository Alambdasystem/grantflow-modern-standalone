"""Offline full-app OCR capacity measurement. Only a disposable synthetic fixture."""
import json,os,subprocess,time,urllib.request
from pathlib import Path
import fitz
assert os.environ.get('SECRET_KEY','').startswith('synthetic-isolated-capacity-'), 'Use a disposable capacity-test container only'
for attempt in range(60):
 try:
  with urllib.request.urlopen('http://127.0.0.1:10000/health',timeout=3)as r:
   if json.load(r)['status']=='ok':break
 except Exception:pass
 time.sleep(1)
else:raise RuntimeError('Replica did not start')
small=fitz.open();page=small.new_page(width=700,height=180);page.insert_text((30,70),'SYNTHETIC BLUEBIRD EDUCATION',fontsize=22);raw=page.get_pixmap().tobytes('png');Path('/tmp/synthetic-ocr-small.png').write_bytes(raw)
large=fitz.open();page=large.new_page(width=2000,height=1500);page.insert_text((100,200),'SYNTHETIC BLUEBIRD EDUCATION',fontsize=48);Path('/tmp/synthetic-ocr-large.png').write_bytes(page.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png'))
scan=fitz.open();scan.new_page(width=700,height=180).insert_image(fitz.Rect(0,0,700,180),stream=raw);Path('/tmp/synthetic-ocr-scan.pdf').write_bytes(scan.tobytes())
env=dict(os.environ);env.update({k:'1'for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')});limit=Path('/sys/fs/cgroup/memory.max').read_text().strip();env['GFM_EXTRACTION_MEMORY_LIMIT_MB']=str(int(limit)//1048576)
for name in ('small.png','large.png','scan.pdf'):
 start=time.monotonic();proc=subprocess.Popen(['python','/app/backend/services/document_extract.py','/tmp/synthetic-ocr-'+name,'synthetic.'+name.split('.')[-1]],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env);latencies=[]
 while proc.poll()is None:
  before=time.monotonic()
  with urllib.request.urlopen('http://127.0.0.1:10000/health',timeout=10)as response:assert json.load(response)['status']=='ok'
  latencies.append(time.monotonic()-before);time.sleep(.5)
 stdout,_=proc.communicate();result=json.loads(stdout)if stdout else{}
 row={'case':name,'exit_code':proc.returncode,'actual_ocr':result.get('ocr'),'recognized':'SYNTHETIC' in result.get('text',''),'seconds':round(time.monotonic()-start,2),'health_max_seconds':round(max(latencies),3),'memory_peak_bytes':int(Path('/sys/fs/cgroup/memory.peak').read_text()),'memory_limit_bytes':int(limit),'memory_events':Path('/sys/fs/cgroup/memory.events').read_text()}
 print(json.dumps(row),flush=True)
 assert row['exit_code']==0 and row['recognized'] and 'oom_kill 0' in row['memory_events']
