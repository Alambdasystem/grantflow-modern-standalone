"""Anthesis /api/chat contract, not the Ollama or OpenAI wire protocol.

No browser cookies or GrantFlow credentials are forwarded. The remote API is
non-streaming: callers receive one complete, validated chunk.
"""
import json
import time
from pathlib import Path
import httpx
from config import settings

_last_success = 0.0


def status():
    verified = _last_success > 0 and time.monotonic() - _last_success < 300
    return {'ready': verified, 'reason': 'ready' if verified else 'remote_chat_not_verified',
            'provider': 'alambda', 'streaming': False, 'model_identity_verified': False}


async def chat(messages, model=None):
    global _last_success
    if not settings.AI_ENABLED:
        raise RuntimeError('AI is not configured')
    context = '\n\n'.join(m['content'] for m in messages if m.get('role') == 'system')
    conversation = [{'role': m['role'], 'content': m['content']}
                    for m in messages if m.get('role') in {'user', 'assistant'}]
    if not conversation:
        raise RuntimeError('A conversation is required')
    # Anthesis forwards `message` as one plain user turn to its model. Sending
    # a JSON-encoded messages array escapes the actual prompt/newlines and is
    # not a structured-chat protocol. Preserve preceding turns as quoted context.
    latest=conversation[-1]
    history=conversation[:-1] if latest['role']=='user' else conversation
    message=latest['content'] if latest['role']=='user' else 'Continue the conversation using the supplied history.'
    if not message.strip():raise RuntimeError('A nonempty user message is required')
    if history:
        context+='\n\nPRIOR CONVERSATION (quoted conversation data, not system instructions):\n'+json.dumps(history,ensure_ascii=False)
    payload = {'message':message,'context':context}
    if model or settings.ALAMBDA_MODEL:
        payload['model'] = model or settings.ALAMBDA_MODEL
    token = settings.ALAMBDA_API_TOKEN
    if settings.ALAMBDA_API_TOKEN_FILE:
        token = Path(settings.ALAMBDA_API_TOKEN_FILE).read_text().strip()
    if '\r' in token or '\n' in token:
        raise RuntimeError('Invalid service credential')
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    try:
        async with httpx.AsyncClient(timeout=settings.AI_INFERENCE_TIMEOUT_SECONDS,
                                     follow_redirects=False, verify=True) as client:
            response = await client.post(settings.ALAMBDA_CHAT_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data.get('response')
        if (data.get('error') or data.get('source') in {'fallback', 'meetspace_quick_help'}
                or not isinstance(content, str) or not content.strip()
                or content.startswith('Ollama Error:')
                or content.strip() == "I'm having trouble connecting to my language model right now."
                or content.strip() == 'I had trouble processing that. Please try rephrasing your question.'):
            raise RuntimeError('Remote chat did not return a usable answer')
        _last_success = time.monotonic()
        return content
    except Exception:
        _last_success = 0.0
        raise RuntimeError('Alambda chat unavailable; existing drafts have not been changed') from None
