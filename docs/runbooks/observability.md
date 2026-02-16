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
- `db_queries_total{operation}`
- `db_query_latency_seconds_bucket{operation}`
- `db_query_errors_total{operation}`
- `job_queue_enqueued_total{job_type}`
- `job_queue_completed_total{job_type}`
- `job_queue_failed_total{job_type}`
- `job_queue_retried_total{job_type}`
- `job_queue_age_seconds_bucket{job_type}`
- `job_processing_duration_seconds_bucket{job_type}`

## Local stack
Start services:
```
docker compose up -d prometheus grafana
```

Grafana:
- URL: http://localhost:3000
- User/pass: admin/admin
- Dashboard: "FloodMVP API"

## Alerts
Prometheus alert rules are defined in:
- `infra/observability/alerts.yml`

To validate rules locally:
```
docker compose up -d prometheus
docker compose exec -T prometheus promtool check rules /etc/prometheus/alerts.yml
```
