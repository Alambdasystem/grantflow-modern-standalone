"""Actual synthetic fixture identity-wide revoke; not real Anthesis acceptance."""
import json
import time
import urllib.error
from cold_probe import request, out

rows = []
tokens = [request('/lab/session', {'role': role})[1]['token'] for role in ['grant_writer', 'grant_writer', 'viewer']]
request('/gfm-app/api/auth/logout', {}, tokens[0])
for index, token in enumerate(tokens):
    try:
        status = request('/gfm-app/api/applications/', token=token)[0]
    except urllib.error.HTTPError as exc:
        status = exc.code
    expected = 401 if index < 2 else 200
    rows.append({'feature': 'Revoked same-identity token' if index < 2 else 'Unrelated identity session retained',
                 'result': 'PASS' if status == expected else 'FAIL', 'status': status})
(out / 'identity-wide-revocation.json').write_text(json.dumps(rows, indent=2))
print(json.dumps(rows))
raise SystemExit(0 if all(row['result'] == 'PASS' for row in rows) else 1)
