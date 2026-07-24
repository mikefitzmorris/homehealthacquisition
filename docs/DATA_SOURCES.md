# Data sources

All sources are public CMS data. No authentication, no key, no rate-limit
agreement to sign. Be polite anyway — the pipeline caches every response and
backs off on 429/5xx.

## 1. Provider Data Catalog (Care Compare)

- Portal: `https://data.cms.gov/provider-data`
- API: DKAN. Catalog at `/api/1/metastore/schemas/dataset/items`, rows at
  `/api/1/datastore/query/{distribution_id}/0?limit=&offset=`
- Datasets used:
  - **Home Health Care Agencies** — provider-level file. Quality of patient
    care star rating, HHCAHPS survey summary star rating, declared ownership
    type, address, offered services.
  - **Home Health Care - Measure Dates** — the measurement period behind each
    refresh. Collected for provenance; not yet applied to the panel.
- Refresh cadence: quarterly.
- Key: `CMS Certification Number (CCN)`.

**Gotcha.** Distribution IDs change every refresh. They are not stable
identifiers and must be re-resolved from the catalog. Suppressed values arrive
as text (`Not Available`, `-`), not nulls.

## 2. data.cms.gov (provider enrollment and ownership)

- Portal: `https://data.cms.gov`
- Catalog: the DCAT document at `https://data.cms.gov/data.json`
- API: `https://data.cms.gov/data-api/v1/dataset/{uuid}/data?size=&offset=`
- Datasets used:
  - **Home Health Agency All Owners** — one row per owner per enrollment.
    Owner type, role, percentage, effective date.
  - **Home Health Agency Enrollments** — one row per enrolled agency. Carries
    both `ENROLLMENT_ID` and `CCN`. This is the bridge table.
- Refresh cadence: quarterly.
- Key: `ENROLLMENT_ID` / `ASSOCIATE_ID`.

**Gotcha.** The owners file has no CCN. Joining it to Care Compare requires the
enrollments file. Owner names are not deduplicated — the same investment firm
appears under multiple spellings and multiple associate IDs.

## Join path

```
all_owners.ENROLLMENT_ID  ─┐
                           ├─► enrollments.CCN ─► care_compare.CCN
enrollments.ENROLLMENT_ID ─┘
```

## Adding a source

Edit `sources.json`, then run `hhpanel discover`. Use a distinctive substring of
the dataset title rather than the full title — CMS appends dates and version
suffixes. If the title no longer matches, `discover` prints the closest
available titles rather than failing with a traceback.
