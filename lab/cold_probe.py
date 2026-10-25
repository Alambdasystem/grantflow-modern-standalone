"""Windows-host client: first actual inference after each lab-only provider restart."""
import json
import argparse
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error

root = Path(__file__).resolve().parents[1]
out = root / 'evidence/parity'
base = 'http://127.0.0.1:5100'


def request(path, data=None, token=None, timeout=400):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.load(response)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    app = json.loads((out / 'persistent-state.json').read_text())['application_id']
    rows = []
    for iteration in range(1, args.rounds + 1):
        subprocess.run(['docker', 'compose', 'restart', 'ollama'], cwd=root, check=True, stdout=subprocess.DEVNULL)
        token = request('/lab/session', {'role': 'grant_writer'})[1]['token']
        started = time.monotonic()
        try:
            status, body = request('/gfm-app/api/ai/generate', {'task': 'proposal', 'application_id': app,
                'context': 'Return exactly one short sentence using supplied synthetic evidence.'}, token)
            result = {'round': iteration, 'result': 'PASS' if status == 200 and body.get('result') and body.get('draft_id') else 'FAIL',
                      'status': status, 'seconds': round(time.monotonic() - started, 3), 'saved_candidate': bool(body.get('draft_id'))}
        except Exception as exc:
            result = {'round': iteration, 'result': 'FAIL', 'error_type': type(exc).__name__, 'seconds': round(time.monotonic() - started, 3)}
            if isinstance(exc, urllib.error.HTTPError):
                result['status'] = exc.code
        rows.append(result)
        (out / 'cold-start-fixed.json').write_text(json.dumps(rows, indent=2))
        print(json.dumps(result), flush=True)
    raise SystemExit(0 if all(r['result'] == 'PASS' for r in rows) else 1)
