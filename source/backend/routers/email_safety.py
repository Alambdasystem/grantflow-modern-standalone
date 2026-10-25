"""Read-only bridge to the existing Anthesis operator dashboard.

Both GrantFlow admin and central platform admin are required: this dashboard is
cross-organization operator data, not an organization's grant mailbox.
"""
from typing import Literal
from urllib.parse import urljoin
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from auth.jwt_handler import require_admin
from config import settings

router = APIRouter(prefix='/api/email-monitor/decision-dashboard', tags=['operator email safety'])


@router.get('/{view}')
async def read_dashboard(view: Literal['summary','recent','controls'], request: Request,
                         limit: int = Query(40,ge=1,le=500), token: dict = Depends(require_admin)):
    base = settings.ANTHESIS_IDENTITY_URL
    headers = {'Authorization': request.headers['Authorization']}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            identity = await client.get(urljoin(base,'/api/auth/me'),headers=headers)
            if identity.status_code != 200 or identity.json().get('user',{}).get('role') != 'admin':
                raise HTTPException(403,'Email Safety requires an Anthesis platform administrator')
            response = await client.get(urljoin(base,f'/api/email-monitor/decision-dashboard/{view}'),
                                        headers=headers,params={'limit':limit})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503,'Anthesis Email Safety is unavailable; no email action was performed') from exc
