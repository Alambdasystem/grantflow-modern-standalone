"""Readiness is stronger than an alive Ollama process; polling never loads it."""
from config import settings
from services.secure_transport import model_client


async def model_status():
    base = settings.OLLAMA_URL.rstrip('/').removesuffix('/api/chat')
    name = settings.DEFAULT_MODEL
    if ':' not in name:
        name += ':latest'
    try:
        async with model_client(5) as client:
            tags = await client.get(base + '/api/tags')
            tags.raise_for_status()
            available = next((m for m in tags.json().get('models', []) if m.get('name') == name), None)
            if not available:
                return {'ready': False, 'reason': 'model_missing'}
            digest = available.get('digest')
            if settings.EXPECTED_MODEL_DIGEST and digest != settings.EXPECTED_MODEL_DIGEST:
                return {'ready': False, 'reason': 'model_digest_mismatch'}
            loaded = await client.get(base + '/api/ps')
            loaded.raise_for_status()
            match = any(m.get('name') == name and m.get('digest') == digest for m in loaded.json().get('models', []))
            return {'ready': match, 'reason': 'ready' if match else 'model_not_loaded'}
    except Exception:
        return {'ready': False, 'reason': 'model_unavailable'}
