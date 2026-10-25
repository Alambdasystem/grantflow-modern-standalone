"""Explicit TLS and runtime-file secrets; never log credential values."""
from pathlib import Path
import ssl
import httpx
from fastapi import HTTPException
from config import settings


def service_key():
    if settings.ANTHESIS_GFM_INTROSPECTION_SECRET_FILE:
        try:
            value = Path(settings.ANTHESIS_GFM_INTROSPECTION_SECRET_FILE).read_text().strip()
        except (OSError, UnicodeError):
            raise HTTPException(503, 'Identity service secret is unavailable') from None
        if not value or len(value) > 4096:
            raise HTTPException(503, 'Identity service secret is invalid')
        return value
    return settings.ANTHESIS_GFM_INTROSPECTION_SECRET


def anthesis_client(timeout):
    # httpx defaults verify=True and follow_redirects=False. Preserve those
    # defaults even when an explicit private CA is configured.
    if settings.ANTHESIS_CA_BUNDLE:
        context = ssl.create_default_context(cafile=settings.ANTHESIS_CA_BUNDLE)
        return httpx.AsyncClient(timeout=timeout, verify=context)
    return httpx.AsyncClient(timeout=timeout)


def model_client(timeout):
    if not settings.AI_CA_BUNDLE:
        return httpx.AsyncClient(timeout=timeout)
    context = ssl.create_default_context(cafile=settings.AI_CA_BUNDLE)
    if settings.AI_CLIENT_CERT_FILE or settings.AI_CLIENT_KEY_FILE:
        context.load_cert_chain(settings.AI_CLIENT_CERT_FILE, settings.AI_CLIENT_KEY_FILE)
    return httpx.AsyncClient(timeout=timeout, verify=context)
