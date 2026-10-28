"""Exercise ingestion authentication and idempotency against the seeded API.

Run inside the backend container after seeding the demo database. This test
uses a unique metric, event timestamp and idempotency key on every invocation.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import httpx


def _require_status(response: httpx.Response, expected: int) -> httpx.Response:
    """Fail with the API response body when the status is unexpected."""
    if response.status_code != expected:
        raise AssertionError(
            f"Expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    return response


def _json_object(response: httpx.Response, expected: int) -> dict[str, Any]:
    """Validate an HTTP status and a JSON object response shape."""
    body: object = _require_status(response, expected).json()
    if not isinstance(body, dict):
        raise AssertionError(f"Expected a JSON object, got {type(body).__name__}")
    return cast(dict[str, Any], body)


def _json_list(response: httpx.Response, expected: int) -> list[dict[str, Any]]:
    """Validate an HTTP status and a list of JSON objects."""
    body: object = _require_status(response, expected).json()
    if not isinstance(body, list) or not all(isinstance(item, dict) for item in body):
        raise AssertionError("Expected a JSON list of objects")
    return cast(list[dict[str, Any]], body)


def _send(
    client: httpx.Client, payload: dict[str, Any], headers: dict[str, str]
) -> httpx.Response:
    """Send one batch, including from concurrent smoke-test workers."""
    return client.post("/v1/telemetry/events:batch", json=payload, headers=headers)


def main() -> None:
    """Verify auth, first ingestion, identical replay and changed-body conflict."""
    ingest_token = os.environ.get("INGEST_TOKEN", "")
    if not ingest_token:
        raise RuntimeError("INGEST_TOKEN must be configured for the smoke test")

    base_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
    with httpx.Client(base_url=base_url, timeout=20.0) as client:
        cities = _json_list(client.get("/v1/cities"), 200)
        if not cities:
            raise AssertionError("Seeded database has no cities")
        assets = _json_list(
            client.get(
                f"/v1/cities/{cities[0]['city_id']}/assets",
                params={"type": "pipe", "limit": 1},
            ),
            200,
        )
        if not assets:
            raise AssertionError("Seeded database has no pipe assets")

        now = dt.datetime.now(dt.UTC)
        payload: dict[str, Any] = {
            "device_id": assets[0]["asset_id"],
            "sent_at": now.isoformat(),
            "events": [
                {
                    "ts": now.isoformat(),
                    "type": "smoke_ingest_idempotency",
                    "value": 0.7,
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {ingest_token}",
            "Idempotency-Key": f"ci-smoke-{uuid.uuid4().hex}",
        }

        unauthorized = _send(client, payload, {"Authorization": "Bearer invalid"})
        _require_status(unauthorized, 401)
        if unauthorized.headers.get("WWW-Authenticate") != "Bearer":
            raise AssertionError("401 response must include a Bearer challenge")

        original = _json_object(_send(client, payload, headers), 200)
        if original["accepted"] != 1 or original["rejected"] != 0:
            raise AssertionError(f"Expected one newly accepted event: {original}")

        replay = _json_object(_send(client, payload, headers), 200)
        if replay != original:
            raise AssertionError("Identical retry did not return the original response")

        changed_payload = {
            **payload,
            "events": [{**payload["events"][0], "value": 0.9}],
        }
        conflict = _json_object(_send(client, changed_payload, headers), 409)
        if conflict["error"]["code"] != "IDEMPOTENCY_CONFLICT":
            raise AssertionError(f"Unexpected conflict error: {conflict}")

        # Two simultaneous first attempts with one key must resolve to one result.
        concurrent_headers = {
            **headers,
            "Idempotency-Key": f"ci-concurrent-{uuid.uuid4().hex}",
        }
        concurrent_payload = {
            **payload,
            "events": [
                {**payload["events"][0], "ts": (now + dt.timedelta(seconds=1)).isoformat()}
            ],
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [
                pool.submit(_send, client, concurrent_payload, concurrent_headers)
                for _ in range(2)
            ]
            concurrent_results = [_json_object(future.result(), 200) for future in pending]
        if concurrent_results[0] != concurrent_results[1]:
            raise AssertionError("Concurrent retries returned different responses")
        if concurrent_results[0]["accepted"] != 1:
            raise AssertionError("Concurrent first attempt did not insert the event")

    print("Ingestion authentication, replay, conflict and concurrency smoke test passed.")


if __name__ == "__main__":
    main()
