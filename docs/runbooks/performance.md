# Performance Budgets + Load Testing

## Budgets (p95 latency)
Budgets are measured at the API edge and expressed as p95 latency targets.

- `GET /v1/health`: 200 ms
- `GET /v1/cities`: 300 ms
- `GET /v1/cities/{city_id}/assets?limit=200`: 750 ms
- `POST /v1/telemetry/events:batch`: 1500 ms

Error budget (all endpoints):
- 5xx rate < 2% over 10 minutes
- Request failure rate < 1% during load tests

## Load test (k6)
Prereqs:
- `k6` installed locally
- backend + db running
- data seeded (`make seed`)

Run:
```
k6 run scripts/loadtest/k6-smoke.js
```

Override base URL or ingest token:
```
BASE_URL=http://localhost:8000 INGEST_TOKEN=dev-ingest-token k6 run scripts/loadtest/k6-smoke.js
```

## Notes
- The k6 script uses live city + asset data to generate ingest traffic.
- Budgets should be tightened or relaxed after observing real workloads.
