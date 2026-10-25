from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt as _bcrypt
from werkzeug.security import check_password_hash as _check_werkzeug_password_hash
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False

    if hashed.startswith(("pbkdf2:", "scrypt:")):
        try:
            return _check_werkzeug_password_hash(hashed, plain)
        except Exception:
            return False

    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


async def validate_anthesis_identity(token: str) -> dict:
    identity_url = settings.ANTHESIS_IDENTITY_URL
    service_secret = settings.ANTHESIS_GFM_INTROSPECTION_SECRET
    if not service_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthesis identity validation is not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                identity_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Anthesis-Service-Key": service_secret,
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthesis identity validation timed out",
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthesis identity validation is unavailable",
        )

    if response.status_code != status.HTTP_200_OK:
        detail = "Anthesis identity rejected the token"
        if response.status_code == status.HTTP_403_FORBIDDEN:
            detail = "Anthesis account is not authorized for GrantFlow"
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        identity = response.json()
    except ValueError:
        raise HTTPException(status_code=503, detail='Anthesis returned an invalid response')
    if not isinstance(identity, dict):
        raise HTTPException(status_code=503, detail='Anthesis returned an invalid response')
    if not identity.get("identity_id") or not identity.get("username"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Anthesis returned an invalid identity",
        )
    access = identity.get("grantflow_access") or []
    if not isinstance(access, list):
        raise HTTPException(status_code=403, detail='Invalid GrantFlow access scope')
    if "read" not in access and "all" not in access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="GrantFlow access is not granted",
        )

    return {
        "sub": identity["identity_id"],
        "identity_id": identity["identity_id"],
        "username": identity["username"],
        "email": identity.get("email"),
        "role": identity.get("grantflow_role") if identity.get("grantflow_role") in {'admin', 'grant_writer', 'reviewer', 'viewer'} else 'viewer',
        "grantflow_access": access,
    }


async def revoke_anthesis_identity(token: str) -> None:
    identity_url = settings.ANTHESIS_REVOKE_URL
    service_secret = settings.ANTHESIS_GFM_INTROSPECTION_SECRET
    if not service_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthesis identity validation is not configured",
        )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                identity_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Anthesis-Service-Key": service_secret,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthesis identity service is unavailable",
        )
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=response.status_code,
            detail="Anthesis could not revoke the current session",
        )


async def get_current_user_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    identity = await validate_anthesis_identity(credentials.credentials)
    read_only_post = request.method.upper() == 'POST' and request.url.path in {'/api/grants/search', '/api/ai/match-grants'}
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and not read_only_post:
        if identity.get('role') == 'viewer':
            raise HTTPException(status_code=403, detail='Read-only GrantFlow role; ask a Rubix administrator for writer access')
        access = identity["grantflow_access"]
        if "write" not in access and "all" not in access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="GrantFlow write access is not granted",
            )
    return identity


async def require_admin(token_data: dict = Depends(get_current_user_token)) -> dict:
    if token_data.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return token_data
