from __future__ import annotations

import hmac
import importlib
from dataclasses import dataclass
from typing import Any, cast

from fastapi import Header

from floodmvp.common.errors import AppError
from floodmvp.config.settings import settings

_jwt: Any | None


class InvalidTokenError(Exception):
    pass


class ExpiredSignatureError(InvalidTokenError):
    pass


try:
    _jwt = importlib.import_module("jwt")
except ImportError:  # pragma: no cover - runtime guard
    _jwt = None


JwtInvalidTokenError: type[Exception] = InvalidTokenError
JwtExpiredSignatureError: type[Exception] = ExpiredSignatureError

if _jwt is not None:
    JwtInvalidTokenError = cast(
        type[Exception], getattr(_jwt, "InvalidTokenError", InvalidTokenError)
    )
    JwtExpiredSignatureError = cast(
        type[Exception], getattr(_jwt, "ExpiredSignatureError", ExpiredSignatureError)
    )


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
        raise AppError(
            code="AUTH_NOT_CONFIGURED", message="JWT auth not configured", status_code=500
        )
    options: dict[str, object] = {
        "verify_signature": True,
        "verify_aud": bool(settings.jwt_audience),
        "verify_iss": bool(settings.jwt_issuer),
    }
    if not settings.is_local:
        options["require"] = ["exp", "sub"]
    return cast(
        dict[str, Any],
        _jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=cast(Any, options),
        ),
    )


def try_decode_token(token: str) -> dict[str, Any] | None:
    if not settings.jwt_secret:
        return None
    try:
        return _decode_token(token)
    except JwtInvalidTokenError:
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
    return raw if isinstance(raw, str) and raw.strip() else None


def credentials_match(provided: str, expected: str) -> bool:
    """Compare encoded bytes so non-ASCII input is rejected without a server error."""
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_deployment_access(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Admit only the configured tenant to a dedicated deployment's data routes."""
    if not settings.is_local:
        require_privileged_access(x_api_key, authorization, {"viewer", "analyst", "admin"})


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(code="UNAUTHORIZED", message="Missing bearer token", status_code=401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = _decode_token(token)
    except JwtExpiredSignatureError as exc:
        raise AppError(code="UNAUTHORIZED", message="Token expired", status_code=401) from exc
    except JwtInvalidTokenError as exc:
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


def require_privileged_access(
    x_api_key: str | None,
    authorization: str | None,
    allowed_roles: set[str],
) -> None:
    """Authorize protected endpoints without silently opening production APIs.

    JWT takes precedence over the legacy API key and enforces roles. In local
    development only, anonymous access remains available for the demo UI.
    Other environments require an explicitly configured authentication method.
    """
    if not settings.is_local and not settings.deployment_tenant_id:
        raise AppError(
            code="AUTH_NOT_CONFIGURED",
            message="DEPLOYMENT_TENANT_ID must identify the dedicated deployment",
            status_code=503,
        )
    if settings.jwt_secret:
        user = get_current_user(authorization)
        if not settings.is_local and extract_tenant(user.claims) != settings.deployment_tenant_id:
            raise AppError(
                code="FORBIDDEN",
                message="Tenant is not admitted to this deployment",
                status_code=403,
            )
        require_roles(user, allowed_roles)
        return

    if settings.analytics_api_key:
        if not x_api_key:
            raise AppError(code="UNAUTHORIZED", message="Missing API key", status_code=401)
        if not credentials_match(x_api_key, settings.analytics_api_key):
            raise AppError(code="FORBIDDEN", message="Invalid API key", status_code=403)
        return

    if settings.is_local:
        return
    raise AppError(
        code="AUTH_NOT_CONFIGURED",
        message="Authentication must be configured for privileged API operations",
        status_code=503,
    )
