# Tagged-release checklist

This is a preparation checklist, not publication authorization. The staged version
is `1.0.0-rc1` (`1.0.0rc1` for Python); stable `v1.0.0` is a proposed target.
The [readiness record](v1-readiness.md) owns the current go/no-go decision.

## Before requesting a release decision

- [ ] Resolve or explicitly disposition every open G1–G9 item in the readiness
  record, including dependency advisories and API/migration exceptions. Do not
  reinterpret absent independent flood labels as validated prediction.
- [ ] Review and merge the intended source changes. Fetch `develop`, verify its
  SHA, use a clean checkout and select a new candidate number when source or
  dependencies change. Never move or reuse a published version tag.
- [ ] Align `pyproject.toml`, `web/package.json`, FastAPI, the regenerated public
  OpenAPI snapshot and `CITATION.cff`. For a proposed stable release, change all to
  `1.0.0` in a reviewed metadata PR and rerun the checks on that commit.
- [ ] Repeat locked installs, Python 3.12–3.14 unit/database suites, web and browser
  checks, positive/negative smoke, monitoring/recovery, dependency/secret scans
  and case-study reproduction. Record skips, failures, image IDs and platform details.
- [ ] Confirm the hosted CI run for that exact candidate SHA succeeds and retain
  its artifacts. A prior SHA's green run is historical evidence only.
- [ ] Build the wheel, sdist and web bundle; validate citation metadata; create a
  manifest containing their hashes and the clean source revision. Keep raw NOAA
  archives, credentials, database state and large logs out of the source release.
- [ ] Finalize the Unreleased changelog into an entry only with an approved
  version/date. Preserve migration prerequisites, deployment credential changes,
  dedicated-tenant/single-process constraints and scientific limits.
- [ ] Record an explicit owner go/no-go decision tied to the reviewed SHA and artifacts.

## Publication is a separate action

- [ ] Obtain an explicit instruction to push the named version tag and publish
  the GitHub Release. Approval to merge a readiness PR is not approval to publish.
- [ ] If authorized, create a new annotated tag at the approved SHA; verify its
  remote target. Attach only the reviewed artifacts, checksums and release notes.
- [ ] If an archival deposit is wanted, obtain separate authorization and confirm
  author/affiliation/license metadata. Create Zenodo metadata only from established
  facts; add a DOI only after the service actually assigns it.
- [ ] Verify release links, package/artifact versions and checksums after publication.

No tag push, GitHub Release or external deposit is performed by the verification
commands or this checklist.
