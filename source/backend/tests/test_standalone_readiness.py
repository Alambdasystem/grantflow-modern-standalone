"""Synthetic transport/readiness contracts; not live Anthesis verification."""
import asyncio
import importlib.util
import sqlite3
from pathlib import Path
import httpx
import pytest
from config import Settings, settings
from services import model_readiness, secure_transport


def trial(**kwargs):
    return Settings(_env_file=None, ENVIRONMENT='standalone-trial',
        ANTHESIS_IDENTITY_URL='https://central.example.com/api/gfm/introspect',
        ANTHESIS_REVOKE_URL='https://central.example.com/api/gfm/revoke',
        ANTHESIS_PLATFORM_ME_URL='https://central.example.com/api/auth/me',
        ANTHESIS_EMAIL_SAFETY_BASE_URL='https://central.example.com/api/email-monitor/decision-dashboard/',
        ANTHESIS_ALLOWED_HOSTS=['central.example.com'], PUBLIC_ORIGIN='https://trial.example.com',
        ALLOWED_ORIGINS=['https://trial.example.com'],
        ANTHESIS_GFM_INTROSPECTION_SECRET='', ANTHESIS_GFM_INTROSPECTION_SECRET_FILE='/run/secrets/key',
        OLLAMA_URL='http://ollama:11434', EXPECTED_MODEL_DIGEST='a'*64, **kwargs)


def test_trial_accepts_explicit_tls_settings():
    assert trial().ENVIRONMENT == 'standalone-trial'


@pytest.mark.parametrize('field,value', [('ANTHESIS_IDENTITY_URL','http://central.example.com/x'),
    ('ANTHESIS_REVOKE_URL','https://other.example.com/x'),
    ('ANTHESIS_PLATFORM_ME_URL','https://central.example.com/x?token=unsafe'),
    ('OLLAMA_URL','http://remote.example.com:11434'), ('DEBUG',True)])
def test_unsafe_trial_configuration_refused(field, value):
    config = trial().model_dump(); config[field] = value
    with pytest.raises(ValueError):
        Settings(_env_file=None, **config)


def test_secret_file_rotation_and_missing_fail_closed(tmp_path, monkeypatch):
    key = tmp_path/'key'
    monkeypatch.setattr(settings,'ANTHESIS_GFM_INTROSPECTION_SECRET_FILE',str(key))
    key.write_text('synthetic-first'); assert secure_transport.service_key() == 'synthetic-first'
    key.write_text('synthetic-second'); assert secure_transport.service_key() == 'synthetic-second'
    key.unlink()
    with pytest.raises(Exception) as error:
        secure_transport.service_key()
    assert error.value.status_code == 503


@pytest.mark.parametrize('available,loaded,digest,reason', [
    (False,False,'a'*64,'model_missing'), (True,False,'a'*64,'model_not_loaded'),
    (True,True,'b'*64,'model_digest_mismatch'), (True,True,'a'*64,'ready')])
def test_model_availability_is_not_server_health(monkeypatch,available,loaded,digest,reason):
    monkeypatch.setattr(settings,'DEFAULT_MODEL','llama3.2:latest')
    monkeypatch.setattr(settings,'EXPECTED_MODEL_DIGEST','a'*64)
    def handler(request):
        assert request.method == 'GET'
        present = available if request.url.path == '/api/tags' else loaded
        return httpx.Response(200,json={'models':[{'name':'llama3.2:latest','digest':digest}] if present else []})
    monkeypatch.setattr(model_readiness,'model_client',lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert asyncio.run(model_readiness.model_status()) == {'ready':reason=='ready','reason':reason}


def storage_module():
    spec = importlib.util.spec_from_file_location('storage', '/ops/storage.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_offline_backup_restore_and_refuse_overwrite(tmp_path):
    storage = storage_module(); data=tmp_path/'data'; data.mkdir()
    with sqlite3.connect(data/'grantflow.db') as db:
        db.execute('create table evidence (value text)'); db.execute("insert into evidence values ('synthetic')")
    (data/'uploads').mkdir(); (data/'uploads'/'example.txt').write_bytes(b'synthetic file')
    archive=tmp_path/'backup.zip'; storage.backup(data,archive)
    (data/'uploads'/'example.txt').write_bytes(b'changed')
    target=tmp_path/'restore'; storage.restore(archive,target)
    assert (target/'uploads'/'example.txt').read_bytes()==b'synthetic file'
    with sqlite3.connect(target/'grantflow.db') as db:
        assert db.execute('select value from evidence').fetchone()[0]=='synthetic'
    with pytest.raises(ValueError): storage.restore(archive,target)
    with pytest.raises(ValueError): storage.backup(data,archive)


def test_corrupt_archive_refused(tmp_path):
    import zipfile,json
    storage=storage_module(); archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('manifest.json',json.dumps({'database':'grantflow.db','sha256':{'grantflow.db':'0'*64}}))
        z.writestr('data/grantflow.db','corrupt')
    with pytest.raises(ValueError): storage.restore(archive,tmp_path/'target')
    assert not (tmp_path/'target').exists()


def test_archive_traversal_refused(tmp_path):
    import zipfile,json,hashlib
    storage=storage_module(); archive=tmp_path/'escape.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('manifest.json',json.dumps({'database':'../escape','sha256':{'../escape':hashlib.sha256(b'x').hexdigest()}}))
        z.writestr('data/../escape',b'x')
    with pytest.raises(ValueError): storage.restore(archive,tmp_path/'target')
    assert not (tmp_path/'escape').exists()


def test_remote_model_requires_mutual_tls():
    config=trial().model_dump(); config['OLLAMA_URL']='https://model.example.com'
    with pytest.raises(ValueError): Settings(_env_file=None,**config)


def test_trial_refuses_permissive_cors():
    config=trial().model_dump(); config['ALLOWED_ORIGINS']=['*']
    with pytest.raises(ValueError): Settings(_env_file=None,**config)


def test_explicit_operator_host_and_platform_admin_denial(monkeypatch):
    from routers import email_safety
    from starlette.requests import Request
    monkeypatch.setattr(settings,'ANTHESIS_PLATFORM_ME_URL','https://identity.example.com/explicit/me')
    monkeypatch.setattr(settings,'ANTHESIS_EMAIL_SAFETY_BASE_URL','https://operator.example.com/explicit/views/')
    calls=[]; central_admin=True
    def handler(request):
        calls.append(str(request.url))
        assert request.headers['Authorization']=='Bearer synthetic-test-token'
        assert 'X-Anthesis-Service-Key' not in request.headers
        if request.url.host=='identity.example.com':
            return httpx.Response(200,json={'user':{'role':'admin' if central_admin else 'viewer'}})
        return httpx.Response(200,json={'synthetic':True})
    monkeypatch.setattr(email_safety,'anthesis_client',lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    request=Request({'type':'http','headers':[(b'authorization',b'Bearer synthetic-test-token')]})
    assert asyncio.run(email_safety.read_dashboard('summary',request,40,{'role':'admin'}))=={'synthetic':True}
    assert calls==['https://identity.example.com/explicit/me','https://operator.example.com/explicit/views/summary?limit=40']
    central_admin=False; calls.clear()
    with pytest.raises(Exception) as error: asyncio.run(email_safety.read_dashboard('summary',request,40,{'role':'admin'}))
    assert error.value.status_code==403 and len(calls)==1


def test_raw_tls_failure_is_retryable_identity_outage(monkeypatch):
    from auth import jwt_handler
    import ssl
    monkeypatch.setattr(jwt_handler,'service_key',lambda:'synthetic-key')
    def broken(timeout): raise ssl.SSLError('synthetic TLS failure')
    monkeypatch.setattr(jwt_handler,'anthesis_client',broken)
    with pytest.raises(Exception) as error: asyncio.run(jwt_handler.validate_anthesis_identity('synthetic-token'))
    assert error.value.status_code==503
