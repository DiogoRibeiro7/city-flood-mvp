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

JOB_ENQUEUED = Counter(
    "job_queue_enqueued_total",
    "Total jobs enqueued",
    ["job_type"],
)
JOB_COMPLETED = Counter(
    "job_queue_completed_total",
    "Total jobs completed",
    ["job_type"],
)
JOB_FAILED = Counter(
    "job_queue_failed_total",
    "Total jobs failed",
    ["job_type"],
)
JOB_RETRIED = Counter(
    "job_queue_retried_total",
    "Total job retries",
    ["job_type"],
)
JOB_QUEUE_AGE = Histogram(
    "job_queue_age_seconds",
    "Seconds a job spent waiting in queue before processing",
    ["job_type"],
)
JOB_PROCESSING_DURATION = Histogram(
    "job_processing_duration_seconds",
    "Seconds to process a job",
    ["job_type"],
)


def classify_operation(statement: str | None) -> str:
    if not statement:
        return "other"
    first = statement.strip().split(" ", 1)[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return first.lower()
    return "other"
