"""Selected post-restoration checks against lab loopback only."""
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from cold_probe import request, out, root

checks = []
writer = request('/lab/session', {'role': 'grant_writer'})[1]['token']
viewer = request('/lab/session', {'role': 'viewer'})[1]['token']
apps = request('/gfm-app/api/applications/', token=writer)[1]
checks.append({'feature': 'Nine synthetic legacy-owned applications retained', 'result': 'PASS' if sum(a.get('title', '').startswith('SYNTHETIC WYF application ') for a in apps) == 9 else 'FAIL'})
state = json.loads((out / 'persistent-state.json').read_text())
app = request('/gfm-app/api/applications/' + str(state['application_id']), token=writer)[1]
checks.append({'feature': 'Saved record preserved after limit restoration/recreation', 'result': 'PASS' if app['notes'] == state['notes'] else 'FAIL'})
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5100/gfm-app/api/ingestion/documents/' + str(state['document_id']) + '/original', headers={'Authorization': 'Bearer ' + writer}), timeout=20) as response:
    sha = hashlib.sha256(response.read()).hexdigest()
checks.append({'feature': 'Uploaded original bytes preserved after limit restoration/recreation', 'result': 'PASS' if sha == state['sha256'] else 'FAIL'})
for label, token, expected in [('Missing authentication denied', None, 401), ('Viewer read access retained', viewer, 200)]:
    try:
        status = request('/gfm-app/api/applications/', token=token)[0]
    except urllib.error.HTTPError as exc:
        status = exc.code
    checks.append({'feature': label, 'result': 'PASS' if status == expected else 'FAIL', 'status': status})
names = ['grantflow-lab-' + s + '-1' for s in ['backend', 'frontend', 'identity', 'gateway', 'ollama']]
containers = json.loads(subprocess.check_output(['docker', 'inspect', *names], cwd=root))
summary = [{'name': c['Name'], 'image': c['Image'], 'memory_limit': c['HostConfig']['Memory'],
            'healthy': c['State'].get('Health', {}).get('Status'), 'restart_count': c['RestartCount'],
            'networks': list(c['NetworkSettings']['Networks'])} for c in containers]
checks.append({'feature': 'Five services healthy at restored normal limits', 'result': 'PASS' if all(c['healthy'] == 'healthy' for c in summary) and sum(c['memory_limit'] for c in summary) > 2048 * 1024**2 else 'FAIL'})
(out / 'followup-final-runtime.json').write_text(json.dumps({'checks': checks, 'containers': summary}, indent=2))
print(json.dumps(checks))
raise SystemExit(0 if all(c['result'] == 'PASS' for c in checks) else 1)
