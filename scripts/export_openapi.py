from __future__ import annotations

import copy
import os
import pathlib
from typing import Any

import yaml  # type: ignore[import-untyped]  # PyYAML stubs are not a project dependency.

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/floodmvp"

from floodmvp.api.main import app  # noqa: E402


def build_public_spec() -> dict[str, Any]:
    """Export the full live API without mutating FastAPI's cached schema."""
    spec: dict[str, Any] = copy.deepcopy(app.openapi())
    _add_error_components(spec)
    return spec


def main() -> None:
    out_path = pathlib.Path("docs/openapi/public.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spec = build_public_spec()
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, sort_keys=False)
    print(f"Wrote {out_path}")


def _add_error_components(spec: dict[str, Any]) -> None:
    components = spec.setdefault("components", {})
    responses = components.setdefault("responses", {})

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


def _replace_response_ref(responses: dict[str, Any], status: str, ref_name: str) -> None:
    val = responses.get(status)
    if not isinstance(val, dict):
        return
    content = val.get("content")
    if not isinstance(content, dict):
        return
    media = content.get("application/json")
    if not isinstance(media, dict):
        return

    # Preserve specific runtime error codes and details. For example, a route
    # returning ASSET_NOT_FOUND must not be documented as generic NOT_FOUND.
    expected = {
        "InvalidArgument": ("INVALID_ARGUMENT", "Validation error"),
        "UnauthorizedApiKey": ("UNAUTHORIZED", "Missing API key"),
        "ForbiddenApiKey": ("FORBIDDEN", "Invalid API key"),
        "UnauthorizedBearer": ("UNAUTHORIZED", "Unauthorized"),
        "ForbiddenBearer": ("FORBIDDEN", "Forbidden"),
        "NotFound": ("NOT_FOUND", "Resource not found"),
        "Conflict": ("CONFLICT", "Conflict"),
    }[ref_name]
    # Named examples can document multiple endpoint-specific error codes for
    # one HTTP status. Never replace them with the generic response component.
    if "examples" in media:
        media.setdefault("schema", {"$ref": "#/components/schemas/ErrorResponse"})
        return
    example = media.get("example")
    error = example.get("error") if isinstance(example, dict) else None
    if isinstance(error, dict) and (
        error.get("code") != expected[0]
        or error.get("message") != expected[1]
        or error.get("details") != {}
    ):
        media.setdefault("schema", {"$ref": "#/components/schemas/ErrorResponse"})
        return

    responses[status] = {"$ref": f"#/components/responses/{ref_name}"}


def _is_bearer_auth(op: dict[str, Any]) -> bool:
    return any(
        "BearerAuth" in requirement or "IngestBearer" in requirement
        for requirement in op.get("security", [])
    )


if __name__ == "__main__":
    main()
