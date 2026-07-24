"""Pull stage: CMS API -> date-stamped parquet snapshots.

Snapshots are never overwritten. The whole point of the project is the
longitudinal panel, so each run deposits a new dated file and old ones are
treated as immutable evidence.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pandas as pd

from .catalog import Resolved
from .config import RAW_DIR, USER_AGENT
from .fetch import dcat_rows, pdc_rows
from .normalize import normalize_columns


def snapshot_date() -> str:
    return dt.date.today().isoformat()


def snapshot_path(key: str, date: str | None = None) -> Path:
    return RAW_DIR / f"{key}__{date or snapshot_date()}.parquet"


def pull_one(
    resolved: Resolved,
    *,
    client: httpx.Client | None = None,
    refresh: bool = False,
    max_pages: int | None = None,
    date: str | None = None,
) -> tuple[Path, int]:
    reader = pdc_rows if resolved.portal == "pdc" else dcat_rows
    rows = list(
        reader(
            resolved.dataset_id,
            client=client,
            refresh=refresh,
            max_pages=max_pages,
        )
    )
    frame = normalize_columns(pd.DataFrame(rows))
    frame["snapshot_date"] = date or snapshot_date()
    frame["source_key"] = resolved.key
    frame["source_dataset_id"] = resolved.dataset_id

    path = snapshot_path(resolved.key, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path, len(frame)


def pull_all(
    resolved: list[Resolved],
    *,
    refresh: bool = False,
    max_pages: int | None = None,
) -> list[tuple[str, Path, int]]:
    out = []
    with httpx.Client(
        timeout=60.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as client:
        for item in resolved:
            path, count = pull_one(
                item, client=client, refresh=refresh, max_pages=max_pages
            )
            out.append((item.key, path, count))
    return out


def latest_snapshot(key: str) -> Path | None:
    matches = sorted(RAW_DIR.glob(f"{key}__*.parquet"))
    return matches[-1] if matches else None


def all_snapshots(key: str) -> list[Path]:
    return sorted(RAW_DIR.glob(f"{key}__*.parquet"))
