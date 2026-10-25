"""Synthetic-only cold-provider and optional import acceptance tests."""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import settings
from db.database import Base
from models.models import Organization, Document, Grant, User, UserRole
from services.ai_service import AIService, AIUnavailable


@pytest.mark.parametrize('operation', ['generate', 'chat', 'stream_generate', 'stream_chat'])
def test_cold_load_precedes_each_inference_path(operation, monkeypatch):
    monkeypatch.setattr(settings, 'AI_PRELOAD_MODEL', True)
    async def run():
        calls = []
        async def handler(request):
            calls.append((request.url.path, json.loads(request.content)))
            if request.url.path == '/api/generate':
                return httpx.Response(200, json={'done': True})
            if json.loads(request.content)['stream']:
                return httpx.Response(200, text='{"message":{"content":"synthetic"}}\n{"done":true}\n')
            return httpx.Response(200, json={'message': {'content': 'synthetic'}})
        service = AIService()
        await service._client.aclose()
        service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service.ollama_url = 'http://synthetic.invalid/api/chat'
        try:
            args = ('proposal', {}) if 'generate' in operation else ([{'role': 'user', 'content': 'synthetic'}],)
            if operation.startswith('stream'):
                assert ''.join([chunk async for chunk in getattr(service, operation)(*args)]) == 'synthetic'
            else:
                assert await getattr(service, operation)(*args) == 'synthetic'
            assert [p for p, _ in calls] == ['/api/generate', '/api/chat']
            assert calls[0][1]['prompt'] == ''  # Load only, no fabricated draft.
        finally:
            await service._client.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['timeout', 'provider_error', 'incomplete'])
def test_load_failure_never_starts_inference(failure, monkeypatch):
    monkeypatch.setattr(settings, 'AI_PRELOAD_MODEL', True)
    async def run():
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if failure == 'timeout':
                raise httpx.ReadTimeout('synthetic timeout', request=request)
            return httpx.Response(200, json={'error': 'synthetic'} if failure == 'provider_error' else {})
        service = AIService()
        await service._client.aclose()
        service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(AIUnavailable):
                await service.generate('proposal', {})
            assert calls == ['/api/generate']
        finally:
            await service._client.aclose()
    asyncio.run(run())


def test_concurrent_loads_serialized(monkeypatch):
    monkeypatch.setattr(settings, 'AI_PRELOAD_MODEL', True)
    async def run():
        active = 0
        peak = 0
        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            await asyncio.sleep(.01)
            active -= 1
            return httpx.Response(200, json={'done': True})
        service = AIService()
        await service._client.aclose()
        service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await asyncio.gather(*(service._prepare_model('synthetic') for _ in range(3)))
            assert peak == 1
        finally:
            await service._client.aclose()
    asyncio.run(run())


def test_optional_full_legacy_import_on_synthetic_store(tmp_path, monkeypatch):
    sys.path.insert(0, '/app')
    from migration import adapter
    legacy = tmp_path / 'synthetic-legacy.db'
    conn = sqlite3.connect(legacy)
    conn.executescript('''
        CREATE TABLE grant_opportunities (id INTEGER, title TEXT, description TEXT, funding_agency TEXT,
          amount REAL, deadline TEXT, eligibility TEXT, category TEXT, source_url TEXT);
        INSERT INTO grant_opportunities VALUES (17,'Synthetic legacy grant','Synthetic description','Synthetic agency',1250,'2027-01-01','Synthetic eligibility','education',NULL);
        CREATE TABLE companies (name TEXT,ein TEXT,business_address TEXT,corporate_address TEXT,phone TEXT,email TEXT,website TEXT,founded_year TEXT,structure TEXT,description TEXT,mission TEXT,naics_codes TEXT,sic_codes TEXT,capabilities TEXT,client_since TEXT);
        INSERT INTO companies (name,mission,email) VALUES ('Synthetic Import Organization','Synthetic imported mission','import@example.invalid');
        CREATE TABLE grant_knowledge_documents (organization_name TEXT,title TEXT,filename TEXT,file_type TEXT,file_path TEXT,summary TEXT,extracted_text TEXT,created_at TEXT);
    ''')
    document = tmp_path / 'synthetic.txt'
    document.write_text('Synthetic historical document bytes')
    conn.execute('INSERT INTO grant_knowledge_documents VALUES (?,?,?,?,?,?,?,?)',
                 ('Synthetic Import Organization', 'Synthetic document', 'synthetic.txt', 'text/plain', str(document), 'Synthetic summary', document.read_text(), '2026-01-01'))
    conn.commit()
    conn.close()
    profile = {**adapter.WYF_PROFILE, **{k: 'Synthetic import value' for k in adapter.WYF_PROFILE if isinstance(adapter.WYF_PROFILE[k], str)}}
    profile.update(name='Synthetic Import Organization', email='import@example.invalid', founded_year='2000')
    monkeypatch.setattr(adapter, 'WYF_PROFILE', profile)
    monkeypatch.setattr(adapter, 'COUNTY_CONNECTIONS_GRANT', {**adapter.COUNTY_CONNECTIONS_GRANT, 'title': 'Synthetic starter grant', 'source_url': 'https://example.invalid/synthetic'})
    monkeypatch.setattr(settings, 'LEGACY_GRANT_DB', str(legacy))
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'modern.db'))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async def init():
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(adapter, 'init_db', init)
        monkeypatch.setattr(adapter, 'AsyncSessionLocal', sessions)
        try:
            await adapter.run_full_migration()
            await adapter.run_full_migration()
            async with sessions() as db:
                assert await db.scalar(select(func.count()).select_from(Grant)) == 2
                org = await db.scalar(select(Organization))
                assert org.mission == 'Synthetic imported mission'
                doc = await db.scalar(select(Document))
                assert doc.extracted_text == document.read_text()
                assert Path(doc.file_path).read_bytes() == document.read_bytes()
                assert await db.scalar(select(func.count()).select_from(Document)) == 1
                assert await db.scalar(select(func.count()).select_from(User)) == 0
            # The legacy file reference is preserved, not copied. A relocated
            # deployment must explicitly migrate bytes and rewrite those paths.
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_legacy_email_collision_is_not_an_identity_link(tmp_path, monkeypatch):
    sys.path.insert(0, '/app')
    from migration import adapter
    path = tmp_path / 'users.json'
    path.write_text(json.dumps({'unrelated_synthetic': {'email': 'collision@example.invalid', 'grantflow_only': True}}))
    monkeypatch.setattr(settings, 'LEGACY_USERS_JSON', str(path))
    monkeypatch.setattr(adapter, 'WYF_PROFILE', {**adapter.WYF_PROFILE, 'name': 'Synthetic collision org'})
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'collision.db'))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with sessions() as db:
                user = User(username='existing_synthetic', email='collision@example.invalid', hashed_password='disabled-synthetic', role=UserRole.viewer)
                db.add(user)
                await db.commit()
                with pytest.raises(ValueError, match='reviewed identity'):
                    await adapter.migrate_users_from_legacy(db)
                await db.rollback()
            async with sessions() as db:
                user = await db.scalar(select(User))
                assert user.organization_id is None
                assert user.role == UserRole.viewer
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_public_detail_contract_and_nested_synopsis(monkeypatch):
    from routers import grant_enrichment
    original_client = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append((request.method, request.headers.get('content-type'), request.content))
        return httpx.Response(200, json={'opportunityNumber': 'SYNTHETIC-17',
            'synopsis': {'synopsisDesc': '<p>Synthetic project narrative and SF-424</p>',
                         'agencyName': 'Synthetic agency', 'responseDateStr': '2027-01-01',
                         'awardCeiling': '1,234.50', 'awardFloor': 'not supplied',
                         'applicantTypes': [{'description': 'Synthetic nonprofit'}]},
            'cfdas': [{'cfdaNumber': '00.123'}]})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(grant_enrichment._enrich_grants_gov_api('17'))
    assert calls == [('POST', 'application/x-www-form-urlencoded', b'oppId=17')]
    assert result['funding_agency'] == 'Synthetic agency'
    assert result['synopsis'] == 'Synthetic project narrative and SF-424'
    assert result['award_amounts_mentioned'] == ['Up to $1,234.50']
    assert result['eligibility'] == 'Synthetic nonprofit'
    assert result['cfda_number'] == '00.123'
    assert 'SF-424' in result['required_documents']
