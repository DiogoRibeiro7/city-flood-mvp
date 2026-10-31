# Portuguese rainfall and river-level source assessment

Assessed **2026-10-31**, after prompt 5 merged at `22f5b90`. This is source
selection for a historical, descriptive experiment. Gate G5 remains open:
there is no provider adapter, complete quality report, validated flood event,
or real-data case study yet.

## Decision

Select **NOAA NCEI GHCNh, Portuguese station `POMU0068545`, Porto / Pedras
Rubras, 2010**, using the version 1.1.0 format documentation. Its explicit
CC0 dedication, documented UTC timestamps, per-variable provenance, and
accessible station-year files permit reproducible offline fixtures. NOAA
archives Portuguese station observations; this is not a claim that NOAA
operates the Portuguese gauge. The [official station list][h-stations] identifies
the station at latitude **41.23**, longitude **-8.68**, elevation **79 m**.

The selected rainfall field is **`precipitation_6_hour`**, in millimetres.
The downloaded 2010 file also contains 12-hour totals. It contains **no
nonempty nominal-hourly rainfall values**. Retain the accumulation interval:
an average rate over six hours cannot validate a 15-minute intensity detector.
This selection supports acquisition, provenance and missing-data handling;
it does not establish suitability for municipal flood warnings.

Use report timestamps in **[2010-01-01T00:00:00Z, 2010-01-12T00:00:00Z)**
for the initial historical CLI sample in prompt 7. This is a reproducibility
window, **not a claimed flood event**. An accumulation ending at the first
timestamp starts before that window. Preserve both interval boundaries.

## Candidate comparison

Two downloadable, reusable rainfall products are viable for descriptive
research: GHCNh and GHCN-Daily. They are distinct products from the same
archive and may share input observations; they are **not independent event
validation sources**. IPMA and APA/SNIRH were assessed as domestic providers.
None of the river-level sources reviewed is ready for implementation.

| Candidate | Access and reuse evidence | Identity, units and time | History, granularity and limitations | Decision |
| --- | --- | --- | --- | --- |
| **NOAA GHCNh** ([product][h-product], [format][h-doc], [metadata XML][h-license]) | Public HTTPS station-year PSV; no key/account/payment in probes. Dataset-specific XML explicitly dedicates data to CC0-1.0. | `POMU0068545`; station metadata above. Documented UTC; accumulated liquid-equivalent precipitation in mm, including explicit 6/12-hour fields. | 2010 file verified; 2023 also accessible but has no rainfall. Sub-hourly weather reporting does not imply sub-hourly rain. Files may be revised. | **Selected**, for historical rainfall with interval and quality restrictions. |
| **NOAA GHCN-Daily** ([product][d-product], [format][d-doc], [NOAA-managed distribution][d-license]) | Public station CSV from NOAA's NODD bucket verified without credentials; distribution states CC0-1.0. Direct NCEI `.dly` also verified. | `PO000008546`, named `PORTO`, lat 41.1331, lon -8.6000, elevation 93 m in the [daily station list][d-stations]. `PRCP` is tenths of mm. Daily date, not a verified UTC instant. | Download contains rain dates from 1940-12-31 to 2026-10-26 with gaps; 364 values in 2010 and none in 2023. Observation-time fields are blank in the inspected first/last CSV records. | **Viable daily descriptive alternative**; not selected for interval-rate ingestion. Do not manufacture hourly values or midnight UTC timestamps. |
| **IPMA station observations** ([API and terms][ipma-api]) | Station and observation JSON both HTTP 200. Terms allow free personal/public use subject to non-profit/non-offensive purposes, attribution and web-logo/link conditions; not an unrestricted open licence. | Verified station `1200545`, Porto / Pedras Rubras, lon -8.681332, lat 41.233502. `precAcumulada`: hourly total in mm; `-99.0`: no data. Offset-free observation keys; forecast UTC wording alone does not settle the observation API's time-zone contract. | Documented rolling 24 hours; probe returned 24 keys, 2026-10-30T10:00 through 2026-10-31T09:00. No historical date selector documented for this endpoint. API may change without notice. | **Not selected**: reuse restrictions and no historical replay contract. No raw IPMA fixture committed. |
| **APA / SNIRH rainfall and hydrometric networks** ([monitoring UI][snirh], [APA description][apa], [catalogue][snirh-catalogue]) | Public monitoring page loaded locally; browser research fetch returned 403. Download page requires source attribution. Catalogue/API for hydrometric station geography explicitly says licence unspecified. | Station-code/parameter selection exists. No particular river station, measurement unit/datum, time zone or interval was verified for a reusable time series. A network ID is not a station ID. | Date-range UI exists, but station geography WFS/WMS/ZIP resources do not establish observation history, completeness or a supported time-series API. | **Deferred**. Obtain explicit reuse scope and a documented/exported station-series contract before implementing or committing measurements. |

IPMA also displays recent daily charts, but [warns that displayed data have
not undergone final processing/validation][ipma-charts]. Its API requests
notification of service use by email; no email was sent. A request for
commercial reuse or historical delivery would require owner involvement.

The [dados.gov.pt general terms][dados-terms] describe a default CC BY 4.0
licence for public-body uploads. We did not extend that general statement to
SNIRH observation downloads: the [specific catalogue API][snirh-api] reports
`license: "notspecified"`, and its resources describe station locations.
River depth, gauge level and elevation relative to a datum must not be
interchanged. There is no approved river-level fixture or station mapping.

## Observed access and gaps

[source-access-evidence.json](source-access-evidence.json) records request URLs,
UTC retrieval timestamps, statuses, response sizes, last-modified headers,
ETags and SHA-256 hashes. Requests were bounded, unauthenticated HTTPS reads
from this laptop. Full downloaded responses remain in ignored
`test-results/source-assessment/`; they are not distributed with the repo.

The selected [2010 station-year file][h-data] returned HTTP 200 twice,
at approximately 10:26:51 and 10:28:11 UTC. Both responses were 14,325,059
bytes and had SHA-256
`1febfaa9832085295cb813e987de298c73298318bf6104a51abb1ba65397d1b7`.
Its last-modified header was 2026-07-10 16:15:47 GMT. Matching two requests
establishes short-term repeatability, not an uptime history, immutable URL,
rate-limit entitlement or SLA. NCEI's product pages currently warn of access
delays during cloud migration. No published numerical request quota was
established from the consulted documentation; keep downloads bounded and cached.

The following are counts from the downloaded files, not completeness scores:

| Station/file | Weather rows | Nonempty rainfall fields | Consequence |
| --- | ---: | --- | --- |
| Porto `POMU0068545`, 2010 | 17,464 | 178 six-hour; 226 twelve-hour; 0 nominal-hourly | Rain availability is sparse relative to weather reporting. The two rainfall fields may overlap. |
| Porto `POMU0068545`, 2023 | 17,156 | 0 in every precipitation amount column | Cannot use this year as a rainfall sample; empty fields do not mean dry weather. |
| Porto / Serra do Pilar `POM00008546`, 2000 | 660 | 0 | Another Porto name does not prove rainfall availability. |
| Coimbra `POM00008549`, 2023 | 1 | 0 | Station-list presence does not establish a usable history. |
| Lisboa / Gago Coutinho `POM00008579`, 2023 | 59 | 0 | Moving geography alone did not resolve the missing rain. |
| Angra do Heroismo `POM00008511`, 2023 | 9 | 0 | Same limitation in this checked Azores file. |

For Porto 2010, 28 of the 178 six-hour values and 32 of the 226 twelve-hour
values have measurement code `T`. All these rainfall rows have blank quality
codes, report type `SYMT`, source `223` and source station `ICAO-LPPR`.
These are observed field contents, not a declaration that every value passed
quality control. Full coverage denominators, duplicate/irregular-interval
checks and station suitability belong to prompt 8. Neither the earliest
station record nor continuous historical coverage was established here.

The daily alternative was verified at both [NCEI `.dly`][d-dly] and
[NOAA's CC0 CSV distribution][d-csv]. The CSV contains 25,891 `PRCP` records
across its available dates; missing years remain missing. [CSV documentation][d-csv-doc]
defines an optional observation time but supplies no station-specific UTC
offset. Daily records are suitable for daily totals and gap analysis, not
the selected pipeline's timestamp/rate contract without further evidence.

## Format, provenance and fixture

NCEI's [format documentation][h-doc], version 1.1.0 dated 2026-03-10,
defines UTC timestamps, millimetre accumulations and variable-specific
measurement, quality, report, source and source-station attributes. Its
nominal-hourly METAR rain can include intermediate running totals; those
must not be summed as independent hours. The chosen 6/12-hour columns
carry explicit accumulation durations. Rainfall is not among the six
variables covered by the described general GHCNh QC pass; preserve source
flags and report uncertainty.

The [six-record fixture](../../tests/fixtures/real_sources/noaa_ghcnh/porto_2010_excerpt.psv)
contains the **original header and complete source lines** 2, 14, 26, 38,
50 and 482, with all 329 columns and LF endings preserved. It is 15,675
bytes. A separate 89-byte station-list line establishes identity. The
[provenance manifest](../../tests/fixtures/real_sources/noaa_ghcnh/provenance.json)
records source/fixture hashes, exact selection timestamps, licence evidence,
metadata and transformations. This is a curated parser sample, not a
contiguous time series or a basis for coverage statistics.

| UTC report timestamp | Six-hour total (mm) | Twelve-hour total (mm) | Meaning |
| --- | ---: | ---: | --- |
| 2010-01-01 00:00 | 7.9 | empty | Recorded six-hour accumulation |
| 2010-01-01 06:00 | empty | 13.0 | Different accumulation interval |
| 2010-01-01 12:00 | 2.0 | empty | Recorded six-hour accumulation |
| 2010-01-01 18:00 | empty | 4.1 | Different accumulation interval |
| 2010-01-02 00:00 | empty | empty | Weather report without rainfall amount |
| 2010-01-11 00:00 | 0.0 (`T`) | empty | Trace; **not an observed dry interval** |

Reuse is supported by the dataset-specific [NCEI XML licence statement][h-license]
under `resourceConstraints` / `Data License Statement`, linking
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/).
The HTML metadata rendering omits the detailed CC0 text; do not infer the
licence solely from public download access. NOAA's [distribution entry][h-distribution]
also states CC0 and requests attribution without implying endorsement.
The repository's software licence does not replace these data terms.

Attribution: Menne, Matthew J., et al. (2023), *Global Historical Climatology
Network-Hourly (GHCNh)*, NOAA National Centers for Environmental Information,
[doi:10.25921/jp3d-3v19](https://doi.org/10.25921/jp3d-3v19).
Subset: `POMU0068545`, six January 2010 reports; accessed 2026-10-31.
Rows were selected without changing field values. NOAA does not endorse this
project. Keep this attribution and provenance with redistributed extracts.

See the [fixture README](../../tests/fixtures/real_sources/noaa_ghcnh/README.md)
for offline verification and exact extraction instructions. New upstream
hashes require deliberate review; do not silently replace recorded evidence.

## Handoff to prompt 7

The existing [rain/river ingestion contracts](../runbooks/ingest_adapters.md)
support mapped JSON/CSV and unit conversion; they do not parse this PSV
format or its duration-specific columns. No adapter or public API is changed
by this assessment.

- Fetch only explicitly requested station-years, cap bytes/time/retries,
  then filter the requested UTC report window. Annual files are chunks;
  there is no need to invent a paginated API. Handle missing files explicitly.
- Use six-hour rainfall as the initial stream. Keep 12-hour values as separate
  source information; never sum overlapping durations. Converting `mm / 6`
  produces a **six-hour mean rate**, not an hourly or instantaneous observation.
  Preserve the original depth and start/end times in provenance.
- Preserve missing cells, `T`, blank QC and unknown codes. Do not turn missing
  rainfall into zero, a trace into a dry interval, or blank QC into `ok`.
  Trace amounts need an explicit policy before numeric analytics.
- Use provider station IDs and recorded coordinates in an explicitly configured
  real-data city/asset mapping. Neither a similar IPMA name nor a synthetic
  Porto asset establishes station equivalence or catchment representativeness.
- Record source URL/version/retrieval time/hash, station, field, duration and
  all source flags. Deduplicate by station, metric, timestamp **and interval**;
  handle revised upstream files explicitly. Keep ordinary tests offline.
- Keep detector accuracy, independent event labels and river observations
  unresolved. If a later case study requires finer rain or river levels,
  obtain another verified source before claiming that capability. An owner
  decision is needed for restricted data, paid access or provider contact.

## Verification for this change

The fixture was compared byte-for-byte with the recorded upstream lines;
both local source downloads have the same checksum. The offline verification
in its README checks fixture/station hashes, schema, identity and timestamps.
Local checks on Python 3.12.10:

| Command/check | Outcome |
| --- | --- |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 149 files |
| `poetry run mypy src scripts/export_openapi.py` | Passed; 69 source files |
| `poetry run pytest -q tests/unit` | 361 passed; existing Alembic `path_separator` deprecation warning |
| Fixture README verification, source-line extraction, recorded HTTP hashes, rainfall counts, local documentation links | Passed |
| Database integration/migration, web, stack smoke | Not run: documentation and recorded fixtures only; no application or schema changes |

These checks do not establish hydrological quality or satisfy G5. No hosted
CI result is asserted by this local record.

[h-product]: https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly
[h-doc]: https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf
[h-stations]: https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.txt
[h-license]: https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc:C01688/xml
[h-distribution]: https://registry.opendata.aws/noaa-ghcnh/
[h-data]: https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2010/psv/GHCNh_POMU0068545_2010.psv
[d-product]: https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily
[d-doc]: https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt
[d-license]: https://registry.opendata.aws/noaa-ghcn/
[d-stations]: https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt
[d-dly]: https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/PO000008546.dly
[d-csv]: https://noaa-ghcn-pds.s3.amazonaws.com/csv/by_station/PO000008546.csv
[d-csv-doc]: https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/readme-by_station.txt
[ipma-api]: https://api.ipma.pt/
[ipma-charts]: https://www.ipma.pt/pt/otempo/obs.superficie/index-map-dia-chart.jsp
[snirh]: https://snirh.apambiente.pt/index.php?idMain=2&idItem=1
[apa]: https://apambiente.pt/en/node/462
[snirh-catalogue]: https://dados.gov.pt/pt/datasets/rede-de-estacoes-hidrometricas-snirh/
[snirh-api]: https://dados.gov.pt/api/1/datasets/rede-de-estacoes-hidrometricas-snirh/
[dados-terms]: https://dados.gov.pt/pt/termos-de-utilizacao
