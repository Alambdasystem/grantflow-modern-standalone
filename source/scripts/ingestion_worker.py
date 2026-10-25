"""Run on a worker PC with a private JSON config: base_url, token, worker_id.

Uses HTTPS (or loopback for testing). No database, cloud credentials or user login
are copied to workers. Temporary originals are removed after each extraction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import httpx

BACKEND=Path(__file__).resolve().parents[1]/'backend'
sys.path.insert(0,str(BACKEND))
from services.document_extract import MAX_BYTES


def run_once(config):
    base=config['base_url'].rstrip('/')
    url=urlsplit(base)
    if url.username or url.password or (url.scheme!='https' and not
        (url.scheme=='http' and url.hostname in {'127.0.0.1','localhost'})):
        raise ValueError('Worker endpoint requires HTTPS or local test loopback.')
    with httpx.Client(timeout=45,follow_redirects=False,headers={'Authorization':'Bearer '+config['token']}) as client:
        response=client.post(base+'/api/ingestion-workers/claim')
        response.raise_for_status(); claim=response.json()
        if not claim.get('job_id'): return False
        endpoint=base+f'/api/ingestion-workers/{claim["job_id"]}'
        headers={'X-Ingestion-Lease':claim['lease_token']}
        result={'failed':True}
        try:
            with tempfile.TemporaryDirectory(prefix='gfm-extract-') as directory:
                path=Path(directory)/'original'
                size=0; digest=hashlib.sha256()
                with client.stream('GET',endpoint+'/original',headers=headers) as download:
                    download.raise_for_status()
                    with path.open('wb') as handle:
                        for chunk in download.iter_bytes():
                            size+=len(chunk)
                            if size>MAX_BYTES: raise ValueError('Document exceeds size limit')
                            digest.update(chunk); handle.write(chunk)
                if digest.hexdigest()!=claim['sha256']: raise ValueError('Document checksum mismatch')
                parsed=subprocess.run([sys.executable,str(BACKEND/'services/document_extract.py'),str(path),claim['filename']],
                    capture_output=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if parsed.returncode==0: result={'result':json.loads(parsed.stdout)}
        except Exception:
            pass  # no credentials, source data or exception URLs in logs
        completed=client.post(endpoint+'/complete',headers=headers,json=result)
        completed.raise_for_status()
        print(json.dumps({'job_id':claim['job_id'],'submitted':True,'extracted':'result' in result}),flush=True)
        return True


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    while True:
        try:
            config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
            worked=run_once(config)
        except Exception:
            print('Worker unavailable; retrying without discarding queued work.',flush=True)
            if args.once: sys.exit(1)
            worked=False
        if args.once: break
        if not worked: time.sleep(5)
