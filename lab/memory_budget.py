"""Host-driven selected hard-limit test, with cgroup peaks/OOM events.

Only the explicit grantflow-lab Compose project is touched. No WSL lifecycle
commands, original endpoints, external integrations or real accounts are used.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
import urllib.error
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--profile', choices=['2gb', 'candidate'], default='2gb')
parser.add_argument('--run')
parser.add_argument('--readiness-images', action='store_true')
args = parser.parse_args()
args.run = args.run or 'memory-' + args.profile
budget_mib = 2048 if args.profile == '2gb' else 5824
root = Path(__file__).resolve().parents[1]
out = root / 'evidence/parity'
base = 'http://127.0.0.1:5100'
services = ['backend', 'frontend', 'identity', 'gateway', 'ollama']
compose = ['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.memory-' + args.profile + '.yaml']
if args.readiness_images:
    compose += ['-f', 'compose.readiness-lab.yaml']
checks, samples = [], []
stop = threading.Event()


def inspect():
    names = ['grantflow-lab-' + service + '-1' for service in services]
    return json.loads(subprocess.check_output(['docker', 'inspect', *names], cwd=root))


def telemetry():
    rows = []
    for service in services:
        name = 'grantflow-lab-' + service + '-1'
        try:
            data = subprocess.check_output(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.current',
                '/sys/fs/cgroup/memory.peak', '/sys/fs/cgroup/memory.events', '/sys/fs/cgroup/memory.swap.current'], stderr=subprocess.DEVNULL).decode().splitlines()
            rows.append({'service': service, 'current': int(data[0]), 'peak': int(data[1]), 'events':
                         {line.split()[0]: int(line.split()[1]) for line in data[2:-1]}, 'swap_current': int(data[-1])})
        except Exception as exc:
            rows.append({'service': service, 'error_type': type(exc).__name__})
    return {'elapsed_seconds': round(time.monotonic() - started, 2), 'containers': rows}


def monitor():
    while not stop.is_set():
        samples.append(telemetry())
        (out / (args.run + '-samples.json')).write_text(json.dumps(samples, indent=2))
        stop.wait(2)


def call(method, path, token=None, payload=None, content_type='application/json', timeout=280):
    headers = {'Content-Type': content_type}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            return response.status, json.loads(data) if response.headers.get_content_type() == 'application/json' else data
    except urllib.error.HTTPError as exc:
        return exc.code, None


def check(name, fn):
    begin = time.monotonic()
    try:
        detail = fn()
        assert detail is not False
        row = {'feature': name, 'result': 'PASS', 'seconds': round(time.monotonic() - begin, 3), 'detail': detail}
    except Exception as exc:
        row = {'feature': name, 'result': 'FAIL', 'seconds': round(time.monotonic() - begin, 3), 'error_type': type(exc).__name__, 'detail': str(exc)[:160]}
    checks.append(row)
    (out / (args.run + '-checks.json')).write_text(json.dumps(checks, indent=2))
    print(json.dumps(row), flush=True)


started = time.monotonic()
proc = subprocess.run(compose + ['up', '-d', '--force-recreate', '--wait', '--wait-timeout', '180'], cwd=root, capture_output=True, text=True)
(out / (args.run + '-startup.log')).write_text(proc.stdout + proc.stderr)
initial = inspect()
limits = {r['Name']: {'memory': r['HostConfig']['Memory'], 'memory_swap': r['HostConfig']['MemorySwap']} for r in initial}
assert sum(v['memory'] for v in limits.values()) == budget_mib * 1024 ** 2
assert all(v['memory'] == v['memory_swap'] for v in limits.values())
checks.append({'feature': 'Container startup under hard limits', 'result': 'PASS' if proc.returncode == 0 else 'FAIL', 'seconds': round(time.monotonic() - started, 3)})
thread = threading.Thread(target=monitor, daemon=True)
thread.start()
try:
    assert proc.returncode == 0, 'Container startup failed'
    def readiness(expected):
        code = "import urllib.request,urllib.error,json\ntry:\n r=urllib.request.urlopen('http://127.0.0.1:8001/ready'); print(json.dumps({'code':r.status,**json.load(r)}))\nexcept urllib.error.HTTPError as e:\n print(json.dumps({'code':e.code,**json.load(e)}))"
        result = json.loads(subprocess.check_output(['docker','exec','grantflow-lab-backend-1','python','-c',code]))
        assert result['code'] == (200 if expected else 503) and result['ready'] is expected
        return result
    if args.readiness_images:
        check('Cold model prevents ready despite healthy containers', lambda: readiness(False))
    writer = call('POST', '/lab/session', payload={'role': 'grant_writer'})[1]['token']
    viewer = call('POST', '/lab/session', payload={'role': 'viewer'})[1]['token']
    state = json.loads((out / 'persistent-state.json').read_text())
    appid = state['application_id']
    suffix = uuid.uuid4().hex[:8]

    def core(i):
        assert call('GET', '/gfm-app/api/applications/', writer)[0] == 200
        assert call('GET', '/gfm-app/api/analytics/dashboard', writer)[0] == 200
        assert call('PATCH', f'/gfm-app/api/applications/{appid}', viewer, {'notes': 'denied'})[0] == 403
        status, app = call('POST', '/gfm-app/api/applications/', writer, {'grant_id': json.loads((out / 'seed.json').read_text(encoding='utf-8-sig'))['grant_id'], 'title': f'SYNTHETIC capacity {suffix}-{i}'})
        assert status == 201
        note = 'Synthetic capacity saved result ' + suffix
        assert call('PATCH', '/gfm-app/api/applications/' + str(app['id']), writer, {'notes': note})[0] == 200
        assert call('GET', '/gfm-app/api/applications/' + str(app['id']), writer)[1]['notes'] == note
        return {'saved_application': app['id'], 'viewer_denied': True}

    def upload():
        # Stay inside the original extractor's 500,000-character bound. The
        # initial 1 MiB plain-text attempt correctly hit that separate guard.
        raw = ('Synthetic capacity document ' + suffix + '\n').encode() + b'synthetic evidence\n' * 10000
        boundary = 'lab' + suffix
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="capacity-{suffix}.txt"\r\nContent-Type: text/plain\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
        status, doc = call('POST', '/gfm-app/api/ingestion/upload', writer, body, 'multipart/form-data; boundary=' + boundary)
        assert status == 202, f'Upload status {status}'
        docid = doc['id']
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            status, item = call('GET', f'/gfm-app/api/ingestion/documents/{docid}', writer)
            if status == 200 and item['status'] in {'ready', 'needs_review'}:
                break
            assert status == 200 and item['status'] != 'failed', f'Extraction status {status}; state {item.get("status") if item else "missing"}'
            time.sleep(1)
        assert item['status'] in {'ready', 'needs_review'}
        status, data = call('GET', f'/gfm-app/api/ingestion/documents/{docid}/original', writer)
        assert status == 200 and hashlib.sha256(data).digest() == hashlib.sha256(raw).digest()
        return {'bytes': len(raw), 'document_id': docid, 'worker_status': item['status'], 'download_hash_matches': True}

    def ai():
        status, data = call('POST', '/gfm-app/api/ai/generate', writer, {'task': 'proposal', 'application_id': appid, 'context': 'Return one short sentence about synthetic education.'})
        assert status == 200 and data.get('draft_id') and data.get('result'), f'AI status {status}'
        return {'status': status, 'saved_candidate': True}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(check, 'Concurrent saved core workflow ' + str(i), lambda i=i: core(i)) for i in range(3)]
        futures += [executor.submit(check, 'Upload, worker extraction and download during AI startup', upload), executor.submit(check, 'Cold AI inference under selected aggregate budget', ai)]
        for future in futures:
            future.result()
    check('Existing persisted record remains readable', lambda: call('GET', f'/gfm-app/api/applications/{appid}', writer)[1]['notes'] == state['notes'])
    check('Existing uploaded bytes survive container recreation', lambda: hashlib.sha256(
        call('GET', f'/gfm-app/api/ingestion/documents/{state["document_id"]}/original', writer)[1]
    ).hexdigest() == state['sha256'])
    if args.readiness_images:
        check('Exact loaded model and core report ready after actual inference', lambda: readiness(True))
finally:
    stop.set()
    thread.join(timeout=30)
    samples.append(telemetry())
    (out / (args.run + '-samples.json')).write_text(json.dumps(samples, indent=2))
    final = inspect()
    totals = [sum(c.get('current', 0) for c in s['containers']) for s in samples]
    peaks = {service: max(c.get('peak', 0) for s in samples for c in s['containers'] if c['service'] == service) for service in services}
    events = {service: {key: max(c.get('events', {}).get(key, 0) for s in samples for c in s['containers'] if c['service'] == service) for key in ['oom', 'oom_kill', 'max']} for service in services}
    summary = {'budget_bytes': budget_mib * 1024 ** 2, 'swap_disabled': True, 'limits': limits, 'checks': checks,
        'sampled_peak_aggregate_bytes': max(totals, default=0), 'per_container_cgroup_peaks': peaks,
        'sum_noncoincident_peaks_bytes': sum(peaks.values()), 'memory_events': events,
        'containers': [{'name': r['Name'], 'restart_count': r['RestartCount'], 'oom_killed': r['State']['OOMKilled'], 'state': r['State']['Status']} for r in final],
        'result': 'PASS' if all(c['result'] == 'PASS' for c in checks) and not any(e['oom_kill'] for e in events.values()) else 'FAIL',
        'scope': 'Five application containers only; Windows client and Docker/WSL/kernel overhead excluded. Not an actual 2 GB WSL test.'}
    (out / (args.run + '-summary.json')).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['result'] == 'PASS' else 1)
