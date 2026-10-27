"""Wire-contract fixtures only; these do not verify the public integration."""
import asyncio
import json
import httpx
import pytest
from config import settings
from services import alambda_chat
from services.ai_service import AIService, AIUnavailable


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(settings, 'AI_PROVIDER', 'alambda')
    monkeypatch.setattr(settings, 'AI_ENABLED', True)
    monkeypatch.setattr(settings, 'ALAMBDA_API_TOKEN', 'synthetic-service-token')
    monkeypatch.setattr(settings, 'ALAMBDA_API_TOKEN_FILE', '')
    monkeypatch.setattr(settings, 'ALAMBDA_MODEL', '')
    monkeypatch.setattr(alambda_chat, '_last_success', 0.0)
    original = httpx.AsyncClient
    def install(handler):
        def client(**kwargs):
            if 'follow_redirects' not in kwargs:
                return original(**kwargs)
            assert kwargs['verify'] is True and kwargs['follow_redirects'] is False
            return original(transport=httpx.MockTransport(handler), **kwargs)
        monkeypatch.setattr(alambda_chat.httpx, 'AsyncClient', client)
    return install


def test_contract_and_buffered_stream(remote):
    requests = []
    def handler(request):
        assert str(request.url) == 'https://api.alambda.com/api/chat'
        assert request.headers['authorization'] == 'Bearer synthetic-service-token'
        assert 'cookie' not in request.headers
        payload = json.loads(request.content)
        assert 'model' not in payload and 'messages' not in payload
        assert 'Never invent' in payload['context']
        assert payload['message'].endswith('USER REQUEST:\nSynthetic organization')
        assert not payload['message'].startswith('[{')
        requests.append(payload)
        return httpx.Response(200, json={'response': 'Synthetic complete answer'})
    remote(handler)
    async def run():
        service = AIService()
        try:
            assert await service.generate('loi', {'prompt': 'Synthetic organization'}) == 'Synthetic complete answer'
            chunks = [s async for s in service.stream_generate('loi', {'prompt': 'Synthetic organization'})]
            assert chunks == ['Synthetic complete answer']
        finally:
            await service._client.aclose()
    asyncio.run(run())
    assert len(requests) == 2
    assert alambda_chat.status()['ready']
    assert not alambda_chat.status()['model_identity_verified']


def test_plain_latest_message_and_preserved_history(remote):
    def handler(request):
        payload=json.loads(request.content)
        assert payload['message']=='50.25 + 49.75'
        assert 'Synthetic system policy' in payload['context']
        assert 'PRIOR CONVERSATION' in payload['context']
        assert 'Previous question' in payload['context'] and 'Previous answer' in payload['context']
        assert request.headers['authorization']=='Bearer synthetic-service-token'
        assert 'cookie' not in request.headers
        return httpx.Response(200,json={'response':'100'})
    remote(handler)
    result=asyncio.run(alambda_chat.chat([{'role':'system','content':'Synthetic system policy'},
        {'role':'user','content':'Previous question'},{'role':'assistant','content':'Previous answer'},
        {'role':'user','content':'50.25 + 49.75'}]))
    assert result=='100'


@pytest.mark.parametrize('status,body', [(404, {}), (302, {}), (200, {'response': ''}),
    (200, {'error': 'failed', 'response': 'not a draft'}),
    (200, {'response': "I'm having trouble connecting to my language model right now."}),
    (200, {'response': 'Ollama Error: model unavailable'})])
def test_remote_errors_fail_closed(remote, status, body):
    remote(lambda request: httpx.Response(status, json=body))
    async def run():
        with pytest.raises(RuntimeError, match='Alambda chat unavailable'):
            await alambda_chat.chat([{'role': 'user', 'content': 'Synthetic test'}])
    asyncio.run(run())
    assert not alambda_chat.status()['ready']


def test_disabled_does_not_send(remote, monkeypatch):
    remote(lambda request: pytest.fail('Disabled AI must not make a request'))
    monkeypatch.setattr(settings, 'AI_ENABLED', False)
    with pytest.raises(RuntimeError, match='not configured'):
        asyncio.run(alambda_chat.chat([{'role': 'user', 'content': 'Synthetic'}]))
