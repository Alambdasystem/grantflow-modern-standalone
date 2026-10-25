"""Opt-in sandbox probes. Defaults to BLOCKED without making network requests."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path)
args = parser.parse_args()
checks = []
out = Path('/evidence/parity/sandbox-preflight.json')


def record(feature, result, detail):
    checks.append({'feature': feature, 'result': result, 'detail': detail})
    out.write_text(json.dumps(checks, indent=2))


def validate(config):
    if config.get('environment') != 'sandbox':
        raise ValueError('Explicit sandbox environment required')
    origin = config.get('identity_origin', '')
    url = urlsplit(origin)
    if (url.scheme != 'https' or url.hostname not in config.get('approved_hosts', [])
            or url.hostname in {'localhost', '127.0.0.1', 'host.docker.internal'}
            or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}):
        raise ValueError('Exact approved HTTPS sandbox origin required')
    return origin.rstrip('/')


async def run(config):
    origin = validate(config)
    key = os.getenv(config.get('service_key_env', ''), '')
    writer = os.getenv(config.get('writer_token_env', ''), '')
    operator = os.getenv(config.get('operator_token_env', ''), '')
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        if not key or not writer:
            record('Real central identity sandbox', 'BLOCKED', 'Sandbox service key and synthetic writer session environment values required')
        else:
            headers = {'Authorization': 'Bearer ' + writer, 'X-Anthesis-Service-Key': key}
            response = await client.post(origin + '/api/gfm/introspect', headers=headers)
            data = response.json() if response.status_code == 200 else {}
            good = response.status_code == 200 and bool(data.get('identity_id')) and data.get('grantflow_role') == 'grant_writer' and {'read', 'write'}.issubset(data.get('grantflow_access', []))
            record('Real central identity sandbox', 'PASS' if good else 'FAIL', 'Actual writer introspection; no user projection/database write')
            denied = await client.post(origin + '/api/gfm/introspect', headers={'Authorization': 'Bearer ' + writer})
            record('Central service-key denial', 'PASS' if denied.status_code == 401 else 'FAIL', 'Missing service key must be denied')
            if config.get('allow_sandbox_identity_revocation') is True:
                revoked = await client.post(origin + '/api/gfm/revoke', headers=headers)
                after = await client.post(origin + '/api/gfm/introspect', headers=headers)
                record('Sandbox central session revocation', 'PASS' if revoked.status_code == 200 and after.status_code == 401 else 'FAIL', 'Dedicated sandbox identity only; invalidates its central sessions')
            else:
                record('Sandbox central session revocation', 'BLOCKED', 'Explicit permission for sandbox identity-wide revocation required')
        if not operator:
            record('Real Email Safety sandbox bridge', 'BLOCKED', 'Dedicated synthetic dual-admin operator token required; sending/scheduling must be disabled')
        elif config.get('email_sending_disabled') is not True:
            record('Real Email Safety sandbox bridge', 'BLOCKED', 'Operator must attest sending/scheduling disabled in this sandbox')
        else:
            headers = {'Authorization': 'Bearer ' + operator}
            identity = await client.get(origin + '/api/auth/me', headers=headers)
            if identity.status_code != 200 or identity.json().get('user', {}).get('role') != 'admin':
                record('Real Email Safety sandbox bridge', 'FAIL', 'Platform-admin prerequisite failed; no operator request sent')
            else:
                for view in ['summary', 'recent', 'controls']:
                    response = await client.get(origin + '/api/email-monitor/decision-dashboard/' + view, headers=headers, params={'limit': 1})
                    record('Read-only Email Safety ' + view, 'PASS' if response.status_code == 200 else 'FAIL', 'Read-only upstream contract; relocated GFM dual-admin bridge still needs end-to-end validation')
    sources = config.get('cloud_sources', [])
    if not sources:
        record('Real Google Drive/SharePoint sandbox pickup', 'BLOCKED', 'Synthetic folders, credential files and expected file hashes required')
    for cfg in sources:
        expected = cfg.get('expected_synthetic_sha256', {})
        path = Path(cfg.get('credential_file', '')).resolve()
        if not expected or not str(path).startswith(('/run/secrets/', '/tmp/sandbox/')):
            record('Real cloud sandbox pickup', 'BLOCKED', 'Expected synthetic hashes and sandbox-only credential mount required')
            continue
        sys.path.insert(0, '/app/backend')
        from services.cloud_documents import documents
        found = []
        async for object_id, name, raw in documents(cfg):
            found.append(object_id)
            if len(found) > 5 or object_id not in expected:
                raise ValueError('Sandbox folder contains an unexpected object; stopped without storing files')
            if hashlib.sha256(raw).hexdigest() != expected[object_id]:
                raise ValueError('Synthetic cloud file hash mismatch')
        record('Real cloud sandbox pickup ' + cfg['provider'], 'PASS' if set(found) == set(expected) else 'FAIL', 'Actual read-only adapter bytes verified; no local DB or file writes')


if not args.config:
    for name in ['Real central identity sandbox', 'Real Email Safety sandbox bridge', 'Real Google Drive/SharePoint sandbox pickup', 'Authenticated requirements/portal/Workspace sandbox']:
        record(name, 'BLOCKED', 'No approved sandbox configuration or access supplied')
else:
    try:
        asyncio.run(run(json.loads(args.config.read_text(encoding='utf-8-sig'))))
    except Exception as exc:
        # Do not expose upstream bodies, credential paths, URLs with secrets or headers.
        record('Sandbox integration probe', 'FAIL', type(exc).__name__)
print(json.dumps(checks), flush=True)
