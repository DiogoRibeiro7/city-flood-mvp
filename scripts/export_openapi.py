from __future__ import annotations

import os
import pathlib

import yaml

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/floodmvp"

from floodmvp.api.main import app  # noqa: E402


def main() -> None:
    out_path = pathlib.Path("docs/openapi/public.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    _add_error_components(spec)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, sort_keys=False)
    print(f"Wrote {out_path}")


def _add_error_components(spec: dict) -> None:
    components = spec.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    responses = components.setdefault("responses", {})

    schemas.setdefault(
        "ErrorResponse",
        {
            "type": "object",
            "properties": {
                "error": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "details": {"type": "object"},
                        "request_id": {"type": "string"},
                    },
                    "required": ["code", "message", "details", "request_id"],
                }
            },
            "required": ["error"],
        },
    )

    def _resp(name: str, code: str, message: str) -> None:
        responses.setdefault(
            name,
            {
                "description": f"{code}: {message}",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        "example": {
                            "error": {
                                "code": code,
                                "message": message,
                                "details": {},
                                "request_id": "req_example",
                            }
                        },
                    }
                },
            },
        )

    _resp("InvalidArgument", "INVALID_ARGUMENT", "Validation error")
    _resp("UnauthorizedApiKey", "UNAUTHORIZED", "Missing API key")
    _resp("ForbiddenApiKey", "FORBIDDEN", "Invalid API key")
    _resp("UnauthorizedBearer", "UNAUTHORIZED", "Unauthorized")
    _resp("ForbiddenBearer", "FORBIDDEN", "Forbidden")
    _resp("NotFound", "NOT_FOUND", "Resource not found")
    _resp("Conflict", "CONFLICT", "Conflict")
    _resp("UnprocessableEntity", "UNPROCESSABLE_ENTITY", "Unprocessable entity")

    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for op in path_item.values():
            if not isinstance(op, dict):
                continue
            resp = op.get("responses")
            if not isinstance(resp, dict):
                continue
            _replace_response_ref(resp, "400", "InvalidArgument")
            _replace_response_ref(
                resp,
                "401",
                "UnauthorizedBearer" if _is_bearer_auth(op) else "UnauthorizedApiKey",
            )
            _replace_response_ref(
                resp,
                "403",
                "ForbiddenBearer" if _is_bearer_auth(op) else "ForbiddenApiKey",
            )
            _replace_response_ref(resp, "404", "NotFound")
            _replace_response_ref(resp, "409", "Conflict")
            _replace_response_ref(resp, "422", "UnprocessableEntity")

    _add_security_schemes(spec)


def _replace_response_ref(responses: dict, status: str, ref_name: str) -> None:
    val = responses.get(status)
    if not isinstance(val, dict):
        return
    content = val.get("content")
    if not isinstance(content, dict):
        return
    if "application/json" not in content:
        return
    responses[status] = {"$ref": f"#/components/responses/{ref_name}"}


def _is_bearer_auth(op: dict) -> bool:
    for param in op.get("parameters", []) or []:
        if param.get("name") == "Authorization":
            return True
    return False


def _add_security_schemes(spec: dict) -> None:
    components = spec.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes.setdefault(
        "BearerAuth",
        {"type": "http", "scheme": "bearer"},
    )
    security_schemes.setdefault(
        "ApiKeyAuth",
        {"type": "apiKey", "in": "header", "name": "X-API-Key"},
    )

    # Default: no auth required unless specified by operation.
    spec["security"] = []

    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for op in path_item.values():
            if not isinstance(op, dict):
                continue
            if _is_bearer_auth(op):
                op["security"] = [{"BearerAuth": []}]
            elif _is_api_key_auth(op):
                op["security"] = [{"ApiKeyAuth": []}]


def _is_api_key_auth(op: dict) -> bool:
    for param in op.get("parameters", []) or []:
        if param.get("name") == "X-API-Key":
            return True
    return False

if __name__ == "__main__":
    main()
