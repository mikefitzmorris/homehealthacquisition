"""Runtime discovery of CMS dataset identifiers.

CMS rotates distribution ids on every quarterly refresh, and the data.cms.gov
UUIDs are not documented anywhere stable. Hardcoding them guarantees the
pipeline breaks silently a few months from now. So we resolve titles to ids at
run time, cache the resolution, and fail loudly with near-miss suggestions.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .config import CMS_DCAT_URL, INTERIM_DIR, PDC_METASTORE, Source
from .fetch import get_json

UUID_RE = re.compile(
    r"/dataset/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

RESOLVED_FILE = INTERIM_DIR / "resolved_sources.json"


@dataclass
class Resolved:
    key: str
    portal: str
    dataset_id: str
    matched_title: str
    modified: str | None = None


class DatasetNotFound(RuntimeError):
    """Raised with suggestions rather than a bare KeyError."""


def _suggest(wanted: str, titles: list[str]) -> str:
    close = difflib.get_close_matches(wanted, titles, n=5, cutoff=0.3)
    if not close:
        close = [t for t in titles if wanted.split()[0].lower() in t.lower()][:5]
    bullets = "\n".join(f"    - {t}" for t in close) or "    (no close matches)"
    return (
        f"No CMS dataset title contains '{wanted}'.\n"
        f"Closest available titles:\n{bullets}\n"
        "Edit sources.json so title_match uses one of these."
    )


def pdc_catalog(client: httpx.Client | None = None, refresh: bool = False) -> list[dict]:
    return get_json(f"{PDC_METASTORE}?show-reference-ids", client=client, refresh=refresh)


def dcat_catalog(client: httpx.Client | None = None, refresh: bool = False) -> list[dict]:
    return get_json(CMS_DCAT_URL, client=client, refresh=refresh).get("dataset", [])


def _pdc_distribution_id(item: dict) -> str | None:
    """Pull the distribution id out of a DKAN metastore item."""
    for dist in item.get("distribution", []) or []:
        if isinstance(dist, dict):
            ident = dist.get("identifier") or dist.get("%Ref:downloadURL")
            if isinstance(ident, str):
                return ident
            if isinstance(ident, list) and ident:
                return ident[0].get("identifier")
    return None


def _dcat_uuid(item: dict) -> str | None:
    for dist in item.get("distribution", []) or []:
        for field in ("accessURL", "downloadURL"):
            url = dist.get(field, "")
            match = UUID_RE.search(url or "")
            if match:
                return match.group(1)
    return None


def resolve(
    sources: list[Source],
    *,
    client: httpx.Client | None = None,
    refresh: bool = False,
) -> list[Resolved]:
    """Map each configured Source onto a live dataset id."""
    pdc = pdc_catalog(client, refresh) if any(s.portal == "pdc" for s in sources) else []
    dcat = dcat_catalog(client, refresh) if any(s.portal == "dcat" for s in sources) else []

    out: list[Resolved] = []
    for source in sources:
        items = pdc if source.portal == "pdc" else dcat
        titles = [i.get("title", "") for i in items]
        needle = source.title_match.lower()
        hits = [i for i in items if needle in i.get("title", "").lower()]

        if not hits:
            if source.required:
                raise DatasetNotFound(_suggest(source.title_match, titles))
            continue

        # Prefer the most recently modified match.
        hits.sort(key=lambda i: str(i.get("modified", "")), reverse=True)
        item = hits[0]
        dataset_id = (
            _pdc_distribution_id(item) if source.portal == "pdc" else _dcat_uuid(item)
        )
        if dataset_id is None:
            if source.required:
                raise DatasetNotFound(
                    f"Found '{item.get('title')}' but it exposes no queryable "
                    "API distribution. CMS sometimes publishes CSV-only. "
                    "Mark this source as required=false to skip it."
                )
            continue

        out.append(
            Resolved(
                key=source.key,
                portal=source.portal,
                dataset_id=dataset_id,
                matched_title=item.get("title", ""),
                modified=item.get("modified"),
            )
        )
    return out


def save_resolved(resolved: list[Resolved], path: Path | None = None) -> Path:
    path = path or RESOLVED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(r) for r in resolved], indent=2))
    return path


def load_resolved(path: Path | None = None) -> list[Resolved]:
    path = path or RESOLVED_FILE
    if not path.exists():
        raise FileNotFoundError(
            "Dataset ids have not been resolved yet. Run:  hhpanel discover"
        )
    return [Resolved(**row) for row in json.loads(path.read_text())]
