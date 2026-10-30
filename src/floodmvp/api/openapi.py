"""Keep FastAPI's generated validation responses aligned with our HTTP handler."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from floodmvp.api.openapi_examples import RESP_INVALID_ARGUMENT
from floodmvp.common.errors import ErrorResponse


class ContractFastAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        spec = super().openapi()
        schemas = spec.setdefault("components", {}).setdefault("schemas", {})
        error_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(error_schema.pop("$defs", {}))
        schemas["ErrorResponse"] = error_schema

        for route in self.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            for method in route.methods:
                responses = spec["paths"][route.path_format][method.lower()]["responses"]
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
