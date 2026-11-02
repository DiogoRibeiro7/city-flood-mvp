from __future__ import annotations

import datetime as dt

from prometheus_client import Counter, Gauge, Histogram

from floodmvp.models.domain import IngestResponse

JOB_TYPES = ("analytics_run", "export_csv", "report_csv", "other")
JOB_BUCKETS = (1, 5, 10, 30, 60, 120, 300, 600, 900, 1800, 3600)


def job_type_label(value: str) -> str:
    return value if value in JOB_TYPES else "other"


def tenant_label(value: str) -> str:
    """Expose authentication classes, never individual tenant identifiers."""
    return value if value in {"public", "analytics-key"} else "authenticated"


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

TENANT_REQUEST_COUNT = Counter(
    "http_requests_tenant_total",
    "Total HTTP requests by authentication class (not tenant identity)",
    ["tenant", "method", "path", "status"],
)
TENANT_REQUEST_LATENCY = Histogram(
    "http_request_tenant_latency_seconds",
    "HTTP request latency by authentication class (not tenant identity)",
    ["tenant", "method", "path"],
)
TENANT_HTTP_ERRORS = Counter(
    "http_requests_tenant_errors_total",
    "HTTP error responses by authentication class (not tenant identity)",
    ["tenant", "method", "path", "status_class"],
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
    "Enqueue calls flushed; may include transactions subsequently rolled back",
    ["job_type"],
)
JOB_COMPLETED = Counter(
    "job_queue_completed_total",
    "Worker completions observed after database commit",
    ["job_type"],
)
JOB_FAILED = Counter(
    "job_queue_failed_total",
    "Worker terminal failures observed after database commit (excludes retries)",
    ["job_type"],
)
JOB_RETRIED = Counter(
    "job_queue_retried_total",
    "Worker retry schedules observed after database commit",
    ["job_type"],
)
JOB_QUEUE_AGE = Histogram(
    "job_queue_age_seconds",
    "Seconds a job spent waiting in queue before processing",
    ["job_type"],
    buckets=JOB_BUCKETS,
)
JOB_PROCESSING_DURATION = Histogram(
    "job_processing_duration_seconds",
    "Seconds to process a job",
    ["job_type"],
    buckets=JOB_BUCKETS,
)

JOB_COMPLETION_DURATION = Histogram(
    "job_completion_latency_seconds",
    "Created-to-terminal-commit latency including retries and scheduled delays",
    ["job_type", "outcome"],
    buckets=JOB_BUCKETS,
)
JOB_LAST_SUCCESS = Gauge(
    "job_last_success_timestamp_seconds", "Last completion observed by this worker", ["job_type"]
)
WORKER_LAST_POLL = Gauge(
    "worker_last_poll_timestamp_seconds", "Last successful committed worker poll/attempt"
)
QUEUE_DUE = Gauge(
    "job_queue_due_jobs",
    "Committed due unfinished jobs; may include active processing",
    ["job_type"],
)
QUEUE_OLDEST = Gauge(
    "job_queue_oldest_due_age_seconds",
    "Age since scheduled_at of oldest committed due unfinished job; includes processing",
    ["job_type"],
)
QUEUE_COLLECTION_SUCCESS = Gauge(
    "job_queue_collection_success", "Whether the latest queue snapshot query succeeded"
)
QUEUE_COLLECTION_TIMESTAMP = Gauge(
    "job_queue_collection_timestamp_seconds", "Timestamp of the last successful queue snapshot"
)
INGEST_EVENTS = Counter(
    "ingest_events_total", "Event results in committed non-replayed API batches", ["outcome"]
)
INGEST_DELAY = Histogram(
    "ingest_event_delay_seconds",
    "Event timestamp to commit delay for inserted API events with aware non-future timestamps",
    buckets=(1, 5, 30, 60, 120, 300, 600, 1800, 3600, 86400),
)
INGEST_TIMESTAMP_ANOMALIES = Counter(
    "ingest_timestamp_anomalies_total",
    "Inserted API events without a usable event delay",
    ["reason"],
)
INGEST_LAST_COMMIT = Gauge(
    "ingest_last_commit_timestamp_seconds",
    "Last API commit inserting at least one event in this process",
)
INGEST_EXPECTED_ACTIVE = Gauge(
    "ingest_expected_active", "Operator opts into arrival-silence monitoring for a live API feed"
)

# Bounded, known series exist before traffic so zero errors is not an absent vector.
for _job_type in JOB_TYPES:
    for _counter in (JOB_COMPLETED, JOB_FAILED, JOB_RETRIED):
        _counter.labels(job_type=_job_type)
    for _outcome in ("completed", "failed"):
        JOB_COMPLETION_DURATION.labels(job_type=_job_type, outcome=_outcome)
for _outcome in ("accepted", "duplicate", "invalid"):
    INGEST_EVENTS.labels(outcome=_outcome)
for _reason in ("future", "naive"):
    INGEST_TIMESTAMP_ANOMALIES.labels(reason=_reason)


def record_ingest_commit(response: IngestResponse, now: dt.datetime) -> None:
    """Call only after commit; idempotency replays and failed transactions do not count."""
    for result in response.results:
        if result.status == "accepted":
            INGEST_EVENTS.labels(outcome="accepted").inc()
            if result.ts.tzinfo is None or result.ts.utcoffset() is None:
                INGEST_TIMESTAMP_ANOMALIES.labels(reason="naive").inc()
            elif result.ts > now:
                INGEST_TIMESTAMP_ANOMALIES.labels(reason="future").inc()
            else:
                INGEST_DELAY.observe((now - result.ts).total_seconds())
        else:
            outcome = "duplicate" if result.reason == "duplicate" else "invalid"
            INGEST_EVENTS.labels(outcome=outcome).inc()
    if response.accepted:
        INGEST_LAST_COMMIT.set(now.timestamp())


def record_job_commit(
    job_type: str, status: str, created_at: dt.datetime, now: dt.datetime
) -> None:
    """Counters reflect committed worker outcomes; retry attempts are not terminal jobs."""
    label = job_type_label(job_type)
    if status == "queued":
        JOB_RETRIED.labels(job_type=label).inc()
    elif status in {"completed", "failed"}:
        counter = JOB_COMPLETED if status == "completed" else JOB_FAILED
        counter.labels(job_type=label).inc()
        JOB_COMPLETION_DURATION.labels(job_type=label, outcome=status).observe(
            max(0, (now - created_at).total_seconds())
        )
        if status == "completed":
            JOB_LAST_SUCCESS.labels(job_type=label).set(now.timestamp())


def classify_operation(statement: str | None) -> str:
    if not statement:
        return "other"
    first = statement.strip().split(" ", 1)[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return first.lower()
    return "other"
