import asyncio
import sys
import os
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DEBUG'] = 'false'

from auth import jwt_handler


class StubAsyncClient:
    def __init__(self, *, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, headers):
        self.url = url
        self.headers = headers
        return httpx.Response(
            200,
            json={
                "identity_id": "identity-1",
                "username": "writer",
                "email": "writer@example.test",
                "grantflow_access": ["read", "write"],
                "grantflow_role": "grant_writer",
            },
        )


def test_central_identity_is_required_when_service_secret_missing(monkeypatch):
    monkeypatch.setattr(jwt_handler.settings, "ANTHESIS_GFM_INTROSPECTION_SECRET", "")

    with pytest.raises(HTTPException) as error:
        asyncio.run(jwt_handler.validate_anthesis_identity("not-a-central-token"))

    assert error.value.status_code == 503


def test_identity_is_obtained_from_anthesis_not_local_jwt(monkeypatch):
    monkeypatch.setattr(
        jwt_handler.settings,
        "ANTHESIS_GFM_INTROSPECTION_SECRET",
        "unit-test-service-secret",
    )
    monkeypatch.setattr(jwt_handler.httpx, "AsyncClient", StubAsyncClient)

    identity = asyncio.run(jwt_handler.validate_anthesis_identity("anthesis-token"))

    assert identity["identity_id"] == "identity-1"
    assert identity["username"] == "writer"
    assert identity["role"] == "grant_writer"
    assert identity["grantflow_access"] == ["read", "write"]
