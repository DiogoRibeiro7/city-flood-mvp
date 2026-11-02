# Dedicated-tenant security and process-quota review

Review date: 2026-11-02. Baseline: `develop` at
`2b19a2ca072301f22e1729b53d3ae4e4c536aa83` (merged recovery drill, PR #154).
The default/integration branch was verified as `develop`. Open PRs inspected
were dependency/action updates; none supplied this admission boundary. This is
a focused implementation review, not a penetration test or production approval.

## Findings and changes

| Area | Observed baseline | Change / boundary |
| --- | --- | --- |
| Ordinary data reads | Cities, assets, observations, scenarios and analytical reads were public even with JWT enabled. Signed tenant identity affected quotas, not access. | All deployed data routers check authentication before DB dependencies. `DEPLOYMENT_TENANT_ID` admits only the matching string JWT claim; even a foreign administrator is denied. Roles remain enforced for each privileged operation. |
| Deployment configuration | Compose forwarded ingestion/CORS settings but omitted the documented JWT/API-key settings. | Compose now forwards deployment ID, JWT secret/issuer/audience/claim names and the legacy key explicitly. Missing binding/auth returns 503 on data routes. |
| JWT lifetime and identity | Expiry was checked when present but not required. Tenant values were coerced to strings. | Non-local JWTs require `exp` and `sub`; tenant must be a matching string. HS256 signature verification and configured issuer/audience validation remain in force. Local demo compatibility is retained. |
| Legacy and ingestion credentials | `hmac.compare_digest(str, str)` raises on non-ASCII input. | Compare UTF-8 bytes, preserving constant-time comparison and turning malformed credentials into normal denials. JWT takes precedence over legacy keys; ingestion remains independently authenticated. |
| Caching | Asset reads advertised public caching. | Deployed `/v1` data responses use `private, no-store`, including errors. Local asset caching remains available. |
| Process quotas | Each interpreter owns its token buckets; no shared backend exists. | Hard release constraint: one API process and one replica. Docker passes `--workers 1`, Compose declares one replica, and documentation prohibits API scaling or overlapping rollout replicas. |
| Browser credential use | Ordinary reads omitted Authorization; changing tokens left other UI caches populated. | All data calls send the runtime JWT. Applying a token reloads the app; applying an empty token clears it and reloads. The field masks input. Two browser regressions exercise header use and the apply/logout flow. |
| CORS | Exact non-local origin allowlist and disabled cookie credentials already existed. | Existing tests retained. CORS is not an authorization mechanism; non-browser clients still require admission. |
| Demo network exposure | Default credentials and development services were published on all host interfaces. | Demo DB/API/web/Prometheus/Grafana ports now bind only to `127.0.0.1`. Remote deployments need explicit ingress/network configuration. |
| Stored/public configuration | Tracked example credentials and synthetic fixtures exist; `VITE_API_BASE` is public. JWTs are stored in local storage. | No signing or ingestion secret is added to client configuration. The local-storage/XSS exposure remains explicit; managed secrets, rotation and dependency remediation remain deployment work. |

## Supported boundary and compatibility

The release supports one dedicated tenant database/export store per API
deployment. Tenant admission is **not row-level authorization**: all records in
that store must belong to the admitted tenant. A city filter does not create a
tenant boundary. Do not connect this service to a shared multi-tenant store or
reuse deployment API/ingestion keys between tenants. The legacy API key grants
all roles within its deployment and is suitable only for trusted server callers.

Outside local environments, formerly public data reads now return 401 without
credentials, 403 for a foreign tenant/insufficient role, or 503 for missing
deployment/authentication configuration. Existing clients must supply the JWT
or configured legacy key. Deployed JWT issuers must include expiry, subject,
tenant and role. Successful payloads and endpoint paths are unchanged. The live
schema and regenerated public OpenAPI document the conditional deployment
requirement and JWT-over-key precedence. Local ordinary reads stay public;
local privileged operations retain their existing rules.

Health remains public. The ingestion token grants write access only to its
dedicated deployment and does not authenticate data reads. Metrics endpoints
remain unauthenticated for private Prometheus scraping: enforce private ingress
for metrics and management endpoints. Configure exact trusted proxy peers and
block direct API access; accepting untrusted forwarded IPs undermines per-IP
limits. The [Uvicorn settings](https://uvicorn.dev/settings/) document both the
worker default from `WEB_CONCURRENCY` and trusted forwarded peers.

The browser's **Apply token** reload clears that page's caches and in-flight
requests. It does not revoke issued JWTs or clear other open tabs. Local storage
is readable by same-origin scripts; hardened sessions, revocation and SSO are
not implemented. [Vite's environment documentation](https://vite.dev/guide/env-and-mode)
explains why `VITE_*` values must contain only public configuration.

## Process experiment and attack coverage

`test_two_processes_each_receive_a_full_quota` starts two distinct Python
interpreters and exercises the actual ASGI middleware with the same identity.
With burst 2 and negligible refill, each process returns `[200, 200, 429]`:
**four requests accepted across two processes**, for both the IP and tenant
limiter configurations. This measures process-local behavior without a real
network or DB; it is not a load-balancer, throughput or adversarial-load test.
Restarting a process or evicting an LRU bucket also resets its quota state.
No global quota, billing guarantee or multi-process rate-limit claim is made.

Tests cover unauthenticated requests and a valid foreign-tenant administrator
on every data route, spoofed `X-Tenant-Id`, malformed/missing tenant claims,
missing expiry/subject, expired/incorrectly signed tokens, issuer/audience
mismatches, unrecognized roles, legacy-key precedence, non-ASCII credentials,
no repository access before denial, and private cache headers. The PostgreSQL
regression seeds a private city, asset and note, proves foreign-tenant denial,
then verifies owner and legacy-key access against actual rows. It does not
claim shared-store row isolation.

## Verification record

Local Windows/PowerShell checks used Python 3.12.10, Node 24.19.0 and repository
Yarn 4.1.1; Docker checks use the repository's Python 3.14 backend and pinned
PostgreSQL 16.11 / TimescaleDB 2.25.0 OSS image.

| Check | Observed result |
| --- | --- |
| Ruff lint / format | Passed; 171 Python files formatted |
| `mypy src scripts/export_openapi.py` | Passed; 77 source files |
| Unit suite / OpenAPI snapshot | 604 passed, 3 skipped (existing POSIX file-mode assertions on Windows) |
| PostgreSQL integration + migration suites | 52 passed in an owned disposable project; cleanup completed |
| Full Compose smoke | Passed in 289.906 s, including exports, scheduler, monitoring and ingestion/job regressions; cleanup completed |
| Locked web install / typecheck / build | Passed; existing large-chunk advisory remains |
| Browser security regressions | 2 passed in Chromium headless shell 145.0.7632.6; backend responses mocked in browser tests |
| Pinned actionlint | Passed |
| Compose configuration | Synthetic env interpolation, JWT/deployment settings, one replica and all five loopback bindings verified without starting the application stack |
| Limited credential-pattern scan | 283 tracked text files / built JS inspected; no private-key, GitHub-token or AWS-key-pattern matches; not a full secret audit |

Ignored evidence lives in `test-results/security-unit.xml`,
`test-results/security-postgres-final/`, `test-results/security-smoke/`, and
`test-results/web/security.xml`. No hosted CI result is asserted.

Reproduce the focused checks:

```sh
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py
poetry run pytest tests/unit -q
# Set TEST_DATABASE_URL only to an owned disposable test DB; never application data.
poetry run pytest tests/integration tests/migrations -q
poetry run python -m scripts.smoke_stack
cd web
corepack yarn install --immutable
corepack yarn typecheck
corepack yarn build --outDir ../test-results/web/dist
corepack yarn playwright install chromium --only-shell
corepack yarn test:security
```

## Remaining release/deployment work

The review inspected tracked configuration, credential-handling code, client
environment use and common credential/private-key patterns without displaying
secret values. No live credential was identified in that scope. This is not a
complete Git-history scan, dependency audit or inventory of a deployed secrets
manager. Existing dependency-update PRs require separate review; no update was
merged here. Deployment ingress/TLS, least-privilege database users, secrets
rotation, restricted metrics access and actual replica topology still require
operator verification. [Gate G6](v1-acceptance.md) stays open for dependency
review and deployment evidence; shared-tenant hosting and multiple API processes
remain outside the supported release boundary.
