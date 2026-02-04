from __future__ import annotations

from prometheus_client import Counter, Histogram


REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)
HTTP_ERRORS = Counter(
    "http_requests_errors_total",
    "Total HTTP error responses",
    ["method", "path", "status_class"],
)

DB_QUERY_COUNT = Counter(
    "db_queries_total",
    "Total database queries",
    ["operation"],
)
DB_QUERY_LATENCY = Histogram(
    "db_query_latency_seconds",
    "Database query latency in seconds",
    ["operation"],
)
DB_QUERY_ERRORS = Counter(
    "db_query_errors_total",
    "Total database query errors",
    ["operation"],
)


def classify_operation(statement: str | None) -> str:
    if not statement:
        return "other"
    first = statement.strip().split(" ", 1)[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return first.lower()
    return "other"
