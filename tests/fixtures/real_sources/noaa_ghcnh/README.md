# Recorded Portuguese GHCNh reports

This directory contains six real reports from NOAA NCEI's Porto / Pedras
Rubras station `POMU0068545`, plus its station-list entry. See
[the assessment](../../../../docs/data/real-source-assessment.md) for the
selection decision, source URLs, limits and downstream requirements.

`provenance.json` records the CC0-1.0 licence evidence, dataset citation,
retrieval timestamps, original hashes and exact transformations. Retain that
manifest when copying the data. These files are source observations; they
contain no flood labels and no synthetic values. Selection is curated, so
the fixture is unsuitable for measuring coverage.

The PSV preserves the full upstream schema, blank cells and source flags.
In particular, the `0.0` six-hour value on January 11 has measurement code
`T` (trace); it is not an observed zero-rainfall interval. All nonempty rainfall
values have blank QC codes, which must not be relabelled as passed checks.
The station record and PSV use LF line endings enforced by `.gitattributes`.

## Offline verification

Run the following Python code from the repository root, using Python 3.12+.
It needs only the standard library and makes no network or database calls.
It can be pasted into `poetry run python`, or saved outside tracked source
and run with that interpreter.

```python
import csv
import hashlib
import io
import json
from pathlib import Path

root = Path("tests/fixtures/real_sources/noaa_ghcnh")
manifest = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
for key in ("fixture", "station_fixture"):
    spec = manifest[key]
    data = (root / spec["file"]).read_bytes()
    assert len(data) == spec["bytes"]
    assert hashlib.sha256(data).hexdigest() == spec["sha256"]
    assert b"\r" not in data
spec = manifest["fixture"]
reader = csv.DictReader(
    io.StringIO((root / spec["file"]).read_text(encoding="utf-8")), delimiter="|"
)
rows = list(reader)
assert len(reader.fieldnames or []) == spec["column_count"]
assert len(rows) == spec["row_count"]
assert all(None not in row and None not in row.values() for row in rows)
assert {row["STATION"] for row in rows} == {manifest["station"]["id"]}
assert [row["DATE"] for row in rows] == spec["selection_timestamps_utc"]
assert rows[-1]["precipitation_6_hour"] == "0.0"
assert rows[-1]["precipitation_6_hour_Measurement_Code"] == "T"
assert rows[-2]["precipitation_6_hour"] == ""
print("Fixture hashes, schema, station, timestamps and trace/missing flags verified")
```

## Re-extraction from the recorded source

For an optional online provenance check, download the manifest's exact
`source.url` into an ignored working directory. Bound the request (25-second
socket timeout and 20 MB response limit were used in the assessment).
Verify the entire downloaded byte stream against `source.sha256` **before**
extracting anything. A mismatch means the upstream archive changed; retain
the committed fixture and investigate the revision.

With matching bytes, use `splitlines(keepends=True)`, keep the header at line
1, then the one-based `fixture.source_line_numbers` in manifest order. Join
those byte strings without decoding/re-encoding or newline translation.
The result must equal `porto_2010_excerpt.psv` byte-for-byte. Similarly,
verify the downloaded station list against `station.source.sha256`, then
retain the complete line beginning with `POMU0068545 `, including its LF.
The provider adapter and a bounded historical-download CLI are prompt 7 work.
