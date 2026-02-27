from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

_jwt: Any | None

try:
    import jwt as _jwt
    from jwt import ExpiredSignatureError, InvalidTokenError
except ImportError:  # pragma: no cover - runtime guard
    _jwt = None

    class InvalidTokenError(Exception):
        pass

    class ExpiredSignatureError(InvalidTokenError):
        pass
from fastapi import Header

from floodmvp.common.errors import AppError
from floodmvp.config.settings import settings


@dataclass
class AuthUser:
    sub: str
    roles: list[str]
    claims: dict[str, Any]


def _decode_token(token: str) -> dict[str, Any]:
    if _jwt is None:
        raise AppError(
            code="JWT_LIBRARY_MISSING",
            message="PyJWT is not installed. Install dependencies or run via Poetry.",
            status_code=500,
        )
    if not settings.jwt_secret:
        raise AppError(code="AUTH_NOT_CONFIGURED", message="JWT auth not configured", status_code=500)
    options: dict[str, object] = {
        "verify_signature": True,
        "verify_aud": bool(settings.jwt_audience),
        "verify_iss": bool(settings.jwt_issuer),
    }
    return _jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options=cast(Any, options),
    )


def try_decode_token(token: str) -> dict[str, Any] | None:
    if not settings.jwt_secret:
        return None
    try:
        return _decode_token(token)
    except InvalidTokenError:
        return None


def _extract_roles(claims: dict[str, Any]) -> list[str]:
    raw = claims.get(settings.jwt_roles_claim)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(r) for r in raw]
    return []


def extract_tenant(claims: dict[str, Any]) -> str | None:
    raw = claims.get(settings.jwt_tenant_claim)
    if raw is None:
        return None
    return str(raw).strip() or None


def get_current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(code="UNAUTHORIZED", message="Missing bearer token", status_code=401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = _decode_token(token)
    except ExpiredSignatureError as exc:
        raise AppError(code="UNAUTHORIZED", message="Token expired", status_code=401) from exc
    except InvalidTokenError as exc:
        raise AppError(code="UNAUTHORIZED", message="Invalid token", status_code=401) from exc
    sub = str(claims.get("sub", ""))
    roles = _extract_roles(claims)
    return AuthUser(sub=sub, roles=roles, claims=claims)


def require_roles(user: AuthUser, allowed: set[str]) -> None:
    if not allowed:
        return
    if any(r in allowed for r in user.roles):
        return
    raise AppError(code="FORBIDDEN", message="Insufficient role", status_code=403)
