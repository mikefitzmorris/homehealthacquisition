# hhpanel

**Ownership churn and quality drift in Medicare-certified home health agencies.**

A small, reproducible pipeline that builds a longitudinal agency-level panel
linking *who owns a home health agency* to *how that agency scores on Care
Compare* — and tracks what happens to quality after ownership changes hands.

[![ci](https://github.com/OWNER/hhpanel/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/hhpanel/actions/workflows/ci.yml)

---

## The question

Private equity and holding-company acquisition of post-acute providers has been
studied heavily in nursing homes and hospice. Home health is comparatively
under-examined, largely because the data to do it only recently became
available: CMS did not publish agency-level ownership rosters for home health
until the provider-enrollment ownership files were expanded, and Care Compare
quality data lives on an entirely separate portal with no shared key.

The question this repo is built to support:

> When a home health agency acquires a financial (as opposed to operating)
> owner, what happens to its quality of patient care star rating and its patient
> survey scores over the following refresh cycles?

## Why this isn't trivial

The two halves of the data don't join.

- **Care Compare** (Provider Data Catalog) is keyed on **CCN**, the 6-digit CMS
  Certification Number.
- **The ownership files** (data.cms.gov) are keyed on **enrollment ID** and
  **associate ID**. There is no CCN column.

The bridge is the Home Health Agency *Enrollments* file, which carries both.
Miss that and you either join on nothing or, worse, fuzzy-match on agency name
and quietly produce garbage — organization names differ across the two systems
far more often than you'd expect.

The other trap: **CMS rotates dataset identifiers on every quarterly refresh.**
Anything with a hardcoded distribution ID stops working within a few months and
usually fails silently. This pipeline resolves dataset titles to live IDs at run
time and fails loudly, with suggestions, when a title no longer matches.

## What it does

```
sources.json ──► discover ──► pull ──► build ──► data/processed/panel.parquet
                (resolve       (dated     (DuckDB
                 live IDs)    parquet      joins +
                             snapshots)   lag windows)
```

Snapshots are immutable and date-stamped. The panel is longitudinal by
accumulation: run it every quarter after the Care Compare refresh and the
within-agency time series builds itself.

## Quickstart

```bash
pip install -e ".[dev]"

hhpanel run --max-pages 1   # ~30s smoke test against the live API
hhpanel run                 # full pull
```

Then:

```python
import pandas as pd
panel = pd.read_parquet("data/processed/panel.parquet")

# Agencies that picked up a financial owner, and what happened next
panel[panel.became_financially_owned]
```

`make smoke` and `make run` do the same thing. `hhpanel status` shows what's on
disk.

## Panel schema

One row per `(ccn, snapshot_date)`.

| column | meaning |
| --- | --- |
| `ccn` | CMS Certification Number, zero-padded to 6 |
| `snapshot_date` | date the pull ran, not the measurement period |
| `provider_name`, `state` | from Care Compare |
| `quality_star` | quality of patient care star rating |
| `survey_star` | HHCAHPS survey summary star rating |
| `declared_ownership_type` | Care Compare's own coarse category (Proprietary / Non-profit / Government) |
| `owner_count` | distinct owners on the enrollment record |
| `financial_owner_count` | owners matching the financial-owner heuristic |
| `any_financial_owner` | boolean |
| `max_owner_pct` | largest single ownership percentage |
| `quality_star_delta` | change vs. the agency's previous snapshot |
| `owner_count_delta` | change vs. the agency's previous snapshot |
| `became_financially_owned` | first snapshot where a financial owner appears |

## Limitations

These are real and you should read them before drawing anything from the output.

1. **`any_financial_owner` is a keyword heuristic, not a CMS classification.**
   It pattern-matches owner-type text for investment firms, holding companies,
   and similar. It will miss PE ownership held through an operating-company
   shell — which is common — and it will over-flag benign holding structures.
   The patterns live in `normalize.py` and are meant to be edited.
2. **Snapshot date ≠ measurement period.** Care Compare star ratings reflect a
   trailing measurement window that lags the refresh by roughly a year. Any
   causal reading has to align on the measure dates file, not on the pull date.
   This pipeline collects the measure-dates file but does not yet apply it.
3. **The panel starts when you start running it.** CMS does not maintain an
   archive of prior Care Compare refreshes at these endpoints. Historical depth
   has to come from the CMS archive or from your own accumulated snapshots.
4. **Ownership files are self-reported enrollment data** with known lags between
   a transaction closing and the roster updating.
5. **Star ratings are suppressed** for low-volume agencies, which are not
   randomly distributed with respect to ownership.

## Data sources

See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md). All public, no API key, no
scraping of anything behind a login. Which datasets get pulled is controlled by
[`sources.json`](sources.json) — plain JSON, no code changes required.

## Roadmap

- Align outcomes to measurement periods using the measure-dates file
- Chain/roll-up detection: cluster CCNs by shared owner associate ID
- HHVBP Total Performance Score as a second outcome
- Event-study specification around the transition quarter

## License

MIT.
