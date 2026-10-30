# City Flood MVP release roadmap

Audited on 2026-10-30 against `develop` commit
`5b4a600b1c4e73638284b54113de53e3339f7ca2`. This replaces the 2026 H1 roadmap.
Package and web versions remain `0.1.0`; the versions below are targets, not
published releases or calendar commitments.

The objective is a reproducible, evidence-backed flood monitoring demonstration.
It does not establish municipal production readiness or prediction accuracy.
The [implementation audit](docs/releases/implementation-audit.md) reconciles
every historical milestone item with code, test evidence, and remaining work.
The [acceptance gates](docs/releases/v1-acceptance.md) define what must be observed
before a release decision. An implementation or passing unit test alone does
not satisfy an end-to-end release gate.

## `v0.9.0-rc1`: reproducible synthetic demonstration

1. **Record the baseline (execution prompt 1).** Replace stale feature checkboxes
   with the implementation inventory, command outcomes, and observable gates.
2. **Verify a repeatable full stack (prompt 2).** Extend the existing ingestion
   and export smoke scripts into an isolated, rerunnable workflow with bounded
   readiness checks, deterministic data, worker/scheduler prerequisites, useful
   failure output, and cleanup. Verify both success and intentional failure.
3. **Audit the public contract (prompt 3).** Start with the existing live OpenAPI
   snapshot test and timestamp, spatial, scenario, and error regression tests.
   Resolve demonstrated status, pagination, filter, and schema discrepancies;
   preserve compatibility and regenerate the snapshot only when needed.
4. **Verify database upgrades (prompt 4).** Retain the existing test-name guard.
   Exercise Alembic from zero and over representative data on a disposable DB;
   compare constraints, indexes, timestamps, extensions, and ORM expectations.
   Table recreation in integration tests is not migration verification.
5. **Make candidate checks auditable (prompt 5).** Address baseline check
   failures; reconcile CI's Python 3.12 environment with the Python 3.14 backend
   image; cover format and OpenAPI-export typing, failure artifacts, and action
   pinning. Define the tested version matrix, changelog, and candidate checklist.
   Current backend static checks already run once, not once per matrix entry.

**Checkpoint:** decide whether gates G1-G4 and G6 in the acceptance document
support an RC. The candidate may remain synthetic, with real-data and recovery
gates explicitly open. Creating a candidate does not authorize tagging or
publishing it.

## `v1.0.0`: evidence-backed demonstration

Build on a reviewed RC baseline, in this order:

1. **Establish real-data evidence (prompts 6-10).** Compare at least two
   authoritative Portuguese rainfall/river sources; verify reuse terms, station
   identities, units, time zones, history, and gaps. Select a source before
   implementing its bounded, retryable adapter. Characterize actual coverage and
   quality, define an event evaluation protocol, and reproduce one historical
   case study with provenance. Label results descriptive if independent event
   labels are unavailable. Never substitute synthetic metrics for observations.
2. **Verify reliability and security (prompts 11-13).** Complete observable
   API/ingest/worker objectives and scraping, a disposable backup/restore and
   worker recovery drill, and a focused multi-process security review. Resolve
   process-local quota limitations and the gap between tenant attribution and
   authorization. RTO/RPO and SLO values remain proposals until measured.
3. **Verify the operator workflow (prompt 14).** Exercise observations, quality
   flags, events, explanations, notes, comparisons, and exports in the existing
   React UI. Label synthetic and real inputs and uncertainty; add focused browser
   and accessibility assertions. Screenshots alone are not workflow tests.
4. **Prepare provenance and a release decision (prompt 15).** Re-run every
   acceptance gate, publish exact results/skips in the readiness PR, reconcile
   version metadata, changelog and established author/citation details, and give
   a go/no-go recommendation. Do not invent a DOI or publish a tag, GitHub
   Release, or deposit without explicit owner approval.

**Checkpoints:** after prompt 10, review provenance and scientific validity;
after prompt 15, require all applicable v1 gates to pass. No release is approved
by this roadmap.

## Delivery and dependency rules

Use a feature branch and a coherent PR against the verified integration branch
(currently `develop`). Do not merge as part of this execution sequence. Each
subsequent prompt depends on review and merge of its predecessor; refresh from
the integration branch and report that dependency if it is still outstanding.
Adjacent work may be combined only when it remains one reviewable change.

Keep an evidence record for each gate: code revision, tool versions, exact
command/configuration, dataset provenance, outcome, and artifact location.
Resolve data licensing, infrastructure costs, secrets, and publication choices
with the repository owner when they become concrete dependencies.

## Deferred beyond the demonstration

Horizontal autoscaling, Kafka streaming, blue/green deployment, shared-database
multi-tenant hosting, and municipal operational certification are not v1
demonstration promises. Reconsider them only with explicit use cases, security
boundaries, deployment evidence, and operational ownership. Existing deployment
reference documents describe design options, not verified capabilities.
