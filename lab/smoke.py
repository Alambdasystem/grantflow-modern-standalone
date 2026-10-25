"""Isolated container integration checks. Never emits session values or response bodies."""
import argparse
import json
from pathlib import Path
import socket
import urllib.error
import urllib.request


def request(base, path, method='GET', body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read()
            return res.status, json.loads(raw) if res.headers.get('Content-Type', '').startswith('application/json') else None
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['create', 'persistence'], default='create')
    args = parser.parse_args()
    results = []

    def check(name, condition):
        results.append({'check': name, 'passed': bool(condition)})
        if not condition:
            raise RuntimeError('Lab check failed: ' + name)

    status, health = request('http://backend:8001', '/health')
    check('API healthy, dispatcher enabled', status == 200 and health.get('database') == 'ok' and health.get('worker_enabled') is True)
    check('Direct protected API rejects missing credentials', request('http://backend:8001', '/api/auth/me')[0] == 401)
    check('UI served through gateway', request('http://gateway:8080', '/gfm-app/dashboard')[0] == 200)
    status, session = request('http://identity:8000', '/lab/session', 'POST', {'role': 'admin'})
    check('Synthetic contract fixture issues lab session', status == 200 and session.get('synthetic') is True)
    token = session['token']
    status, user = request('http://gateway:8080', '/gfm-app/api/auth/me', token=token)
    check('Frontend rewrite, API, identity and local projection work', status == 200 and user.get('role') == 'admin')
    evidence = Path('/evidence'); evidence.mkdir(exist_ok=True)
    if args.phase == 'create':
        status, org = request('http://gateway:8080', '/gfm-app/api/organizations/', 'POST', {'name': 'SYNTHETIC Docker portability check'}, token)
        check('Synthetic data write succeeds', status in {200, 201} and isinstance(org.get('id'), int))
        (evidence/'synthetic-org-id.json').write_text(json.dumps({'id': org['id']}))
    else:
        org = json.loads((evidence/'synthetic-org-id.json').read_text())
        status, data = request('http://gateway:8080', '/gfm-app/api/organizations/' + str(org['id']), token=token)
        check('Synthetic data persists after backend container restart', status == 200 and data.get('id') == org['id'])
    _, session = request('http://identity:8000', '/lab/session', 'POST', {'role': 'viewer'})
    check('Viewer write rejected by Grantflow backend', request('http://backend:8001', '/api/organizations/', 'POST', {'name': 'must not be created'}, session['token'])[0] == 403)
    check('Legacy local login remains disabled', request('http://backend:8001', '/api/auth/login', 'POST', {})[0] == 410)
    try:
        with socket.create_connection(('1.1.1.1', 443), timeout=2):
            blocked = False
    except OSError:
        blocked = True
    check('External network blocked for lab containers', blocked)
    (evidence/(args.phase + '-checks.json')).write_text(json.dumps(results, indent=2))
    print(json.dumps({'phase': args.phase, 'passed': len(results), 'failed': 0}))


if __name__ == '__main__':
    main()
