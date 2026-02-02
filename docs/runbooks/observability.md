# Observability

## Structured logs
Every request logs a JSON line including:
- `request_id`
- `method`
- `path`
- `status`
- `latency_ms`

## Metrics
Prometheus endpoint: `GET /metrics`

Exported metrics:
- `http_requests_total{method,path,status}`
- `http_request_latency_seconds_bucket{method,path}`
- `http_requests_errors_total{method,path,status_class}`

## Local stack
Start services:
```
docker compose up -d prometheus grafana
```

Grafana:
- URL: http://localhost:3000
- User/pass: admin/admin
- Dashboard: "FloodMVP API"
