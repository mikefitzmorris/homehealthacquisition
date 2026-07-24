"""Configuration, endpoints, and the editable source registry.

Nothing in this file needs to be edited to change *which* CMS datasets are
pulled -- that lives in ``sources.json`` at the repo root.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# --- CMS endpoints -------------------------------------------------------
# Two different CMS portals, two different APIs. This is the single most
# confusing thing about working with CMS provider data.
#
#   1. Provider Data Catalog (PDC) -- the "Care Compare" quality files.
#      DKAN-based. Datasets are addressed by a *distribution* id.
#   2. data.cms.gov -- enrollment / ownership files.
#      Datasets are addressed by a UUID discovered from the DCAT catalog.
PDC_BASE = "https://data.cms.gov/provider-data"
PDC_METASTORE = f"{PDC_BASE}/api/1/metastore/schemas/dataset/items"
PDC_DATASTORE = f"{PDC_BASE}/api/1/datastore/query"

CMS_DCAT_URL = "https://data.cms.gov/data.json"
CMS_DATA_API = "https://data.cms.gov/data-api/v1"

USER_AGENT = "hhpanel/0.1 (research tooling; +https://github.com/)"

# --- Paths ---------------------------------------------------------------
PKG_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PKG_ROOT.parents[1]

DATA_DIR = Path(os.environ.get("HHPANEL_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"

SOURCES_FILE = Path(os.environ.get("HHPANEL_SOURCES", REPO_ROOT / "sources.json"))


def ensure_dirs() -> None:
    for d in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Source:
    """One CMS dataset we intend to pull."""

    key: str
    portal: str  # "pdc" | "dcat"
    title_match: str  # case-insensitive substring match against catalog titles
    role: str  # what this table contributes to the panel
    required: bool = True

    def __post_init__(self) -> None:
        if self.portal not in {"pdc", "dcat"}:
            raise ValueError(
                f"source '{self.key}': portal must be 'pdc' or 'dcat', "
                f"got '{self.portal}'. Fix this in sources.json."
            )


def load_sources(path: Path | None = None) -> list[Source]:
    """Read the source registry. Raises a human-readable error, not a traceback."""
    path = path or SOURCES_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find the source list at {path}.\n"
            "Copy sources.example.json to sources.json and try again."
        )
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not valid JSON (line {exc.lineno}). "
            "A missing comma or trailing comma is the usual cause."
        ) from exc

    return [Source(**row) for row in payload["sources"]]
