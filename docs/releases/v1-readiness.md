# v1.0.0 readiness review — 2026-11-03

**Recommendation: NO-GO for publishing v1.0.0.** Candidate preparation and
verification do not clear outstanding security and contract/migration gates.
The staged metadata is `1.0.0-rc1` (Python `1.0.0rc1`), unreleased.
No version tag, GitHub Release or archival deposit is created by this review.

Baseline: merged prompt 14 at `fd046be8a54083fad57317336c70fc7290e05910`.
Remote default and integration branches were verified as `develop`. Twenty-two
open PRs were dependency/action updates; none was merged into this review.
The preceding feature SHA `262234c718cf28319e33ca814832acf1aeb44be8` has a
[successful hosted CI run](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/runs/41545362453).
It does not establish results for this candidate's SHA.

## Verification record

The final results are recorded below after execution. Commands, logs, JUnit and
the artifact manifest are retained under ignored `test-results/v1-readiness/`.
Fresh Python 3.12–3.14 environments are outside that artifact directory. Owned
disposable databases are isolated from application configuration and data.

## Gate disposition

The final gate table reconciles the [acceptance criteria](v1-acceptance.md) with
observed results; a check that was skipped or failed is not a pass.

## Metadata and scope

The established non-bot Git author is **Diogo Ribeiro**. Poetry's placeholder
author is replaced by that name; citation metadata uses its given/family names.
No email, ORCID, affiliation, DOI or release date is inferred. The repository's
MIT license is retained. [CITATION.cff](../../CITATION.cff) describes the software
and an unreleased candidate; it does not cite the NOAA dataset as software authorship.
The source dataset's existing attribution and DOI remain in the case-study materials.

See the [reproducibility statement](../../REPRODUCIBILITY.md),
[changelog](../../CHANGELOG.md) and [tagged-release checklist](v1-release-checklist.md).
