"""Keep FastAPI's generated validation responses aligned with our HTTP handler."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from floodmvp.api.openapi_examples import RESP_INVALID_ARGUMENT, error_response
from floodmvp.common.auth import require_deployment_access
from floodmvp.common.errors import ErrorResponse


class ContractFastAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        spec = super().openapi()
        schemas = spec.setdefault("components", {}).setdefault("schemas", {})
        error_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(error_schema.pop("$defs", {}))
        schemas["ErrorResponse"] = error_schema
        schemes = spec["components"].setdefault("securitySchemes", {})
        schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "description": "JWT with exp, sub, role and the configured deployment tenant outside local development.",
        }
        schemes["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Deployment-scoped legacy key, accepted only when JWT is disabled. Never embed in browser code.",
        }
        schemes["IngestBearer"] = {
            "type": "http",
            "scheme": "bearer",
            "description": "Server-to-server INGEST_TOKEN. Deployment JWTs and API keys do not authorize ingestion.",
        }
        spec["security"] = []

        for route in self.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            for method in route.methods:
                operation = spec["paths"][route.path_format][method.lower()]
                responses = operation["responses"]
                if any(
                    dep.call is require_deployment_access for dep in route.dependant.dependencies
                ):
                    operation["security"] = [{"BearerAuth": []}, {"ApiKeyAuth": []}]
                    operation["x-deployment-access"] = (
                        "Non-local environments require a dedicated DEPLOYMENT_TENANT_ID and authentication. "
                        "JWT takes precedence over API keys; tenant must match and role must permit the operation. "
                        "Local demos retain anonymous ordinary reads and existing privileged-endpoint rules."
                    )
                    for status, code, description in (
                        ("401", "UNAUTHORIZED", "Missing, invalid or expired credential"),
                        (
                            "403",
                            "FORBIDDEN",
                            "Credential, role or deployment tenant is not permitted",
                        ),
                        (
                            "503",
                            "AUTH_NOT_CONFIGURED",
                            "Deployment tenant or authentication is not configured",
                        ),
                    ):
                        response = responses.setdefault(status, error_response(code, description))
                        response["description"] = description
                        response["content"]["application/json"]["schema"] = {
                            "$ref": "#/components/schemas/ErrorResponse"
                        }
                for status, response in responses.items():
                    if status.isdigit() and int(status) >= 400:
                        media = response.get("content", {}).get("application/json")
                        if isinstance(media, dict):
                            media.setdefault(
                                "schema", {"$ref": "#/components/schemas/ErrorResponse"}
                            )
                # Preserve any deliberately declared 422 response. Only the
                # automatic FastAPI validation response is handled as HTTP 400.
                validation = responses.get("422", {})
                schema = validation.get("content", {}).get("application/json", {}).get("schema", {})
                if (
                    422 in route.responses
                    or schema.get("$ref") != "#/components/schemas/HTTPValidationError"
                ):
                    continue
                del responses["422"]
                response = responses.setdefault("400", {"description": "Validation error"})
                media = response.setdefault("content", {}).setdefault("application/json", {})
                media["schema"] = {"$ref": "#/components/schemas/ErrorResponse"}
                if "example" not in media and "examples" not in media:
                    media["example"] = RESP_INVALID_ARGUMENT["content"]["application/json"][
                        "example"
                    ]
        return spec
