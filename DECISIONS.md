# Decision log

Sequential across the project. Sign-off tier noted where it matters.

| ID | Decision | Tier | Rationale |
| --- | --- | --- | --- |
| D1 | Research question: ownership churn -> quality drift in home health, not hospice or SNF | sign-off | Home health is the under-studied case and the ownership files are newly usable there. SNF/PE is saturated. |
| D2 | Resolve CMS dataset IDs at run time from the catalog rather than hardcoding | sign-off | Hardcoded distribution IDs break silently every quarterly refresh. Runtime resolution fails loudly with suggestions instead. |
| D3 | Join owners -> enrollments -> Care Compare on enrollment ID, never on agency name | sign-off | Name matching across the two CMS systems produces false links at a rate that would invalidate results. |
| D4 | Snapshots are immutable, date-stamped parquet; the panel accumulates | sign-off | CMS does not archive prior refreshes at these endpoints, so longitudinal depth has to be captured as it goes. |
| D5 | DuckDB for the joins and window functions rather than pandas merges | documented | Lag/window logic is clearer in SQL and stays readable as the panel grows. Zero-config, no server. |
| D6 | Financial-owner classification is a documented keyword heuristic | documented | No CMS field encodes PE ownership. Being explicit about the heuristic is better than implying a classification that does not exist. |
| D7 | Configuration lives in `sources.json`, not in Python | documented | Adding or swapping a dataset should not require editing code. |
| D8 | On-disk response cache keyed by URL hash, `--refresh` to bust | documented | Makes re-runs cheap and makes the test suite runnable fully offline. |
| D9 | Errors print next actions, not tracebacks | documented | Standing usability guardrail. |

## Open items

- Apply the measure-dates file so outcomes align to measurement periods rather than pull dates (blocks any causal claim).
- Decide whether roll-up detection clusters on owner associate ID or on owner name after normalization.
