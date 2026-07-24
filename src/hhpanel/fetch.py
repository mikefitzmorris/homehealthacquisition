"""Cached, polite HTTP access to the two CMS APIs.

Design notes
------------
* Every response is cached to disk keyed by URL hash. Re-running the pipeline
  is therefore cheap and reproducible; ``--refresh`` busts the cache.
* CMS rate-limits aggressively and returns 5xx under load, so every request
  gets bounded exponential backoff.
* Both APIs paginate, but differently. Two paginators, one interface.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from .config import CACHE_DIR, CMS_DATA_API, PDC_DATASTORE, USER_AGENT

RETRY_STATUS = {429, 500, 502, 503, 504}


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    return CACHE_DIR / f"{digest}.json"


def get_json(
    url: str,
    client: httpx.Client | None = None,
    *,
    refresh: bool = False,
    max_attempts: int = 4,
) -> Any:
    """GET a JSON document, with on-disk caching and backoff."""
    cache_file = _cache_path(url)
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    owns_client = client is None
    client = client or httpx.Client(
        timeout=60.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )
    try:
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                response = client.get(url)
                if response.status_code in RETRY_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == max_attempts - 1:
                    break
                time.sleep(2**attempt)
                continue

            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload))
            return payload

        raise RuntimeError(
            f"CMS did not return usable data for:\n  {url}\n"
            f"Last error: {last_error}\n"
            "If this persists, the dataset id may have changed -- "
            "re-run `hhpanel discover` to refresh it."
        ) from last_error
    finally:
        if owns_client:
            client.close()


def pdc_rows(
    distribution_id: str,
    *,
    client: httpx.Client | None = None,
    page_size: int = 2000,
    refresh: bool = False,
    max_pages: int | None = None,
) -> Iterator[dict]:
    """Yield rows from a Provider Data Catalog datastore query."""
    offset = 0
    pages = 0
    while True:
        url = (
            f"{PDC_DATASTORE}/{distribution_id}/0"
            f"?limit={page_size}&offset={offset}"
        )
        payload = get_json(url, client=client, refresh=refresh)
        results = payload.get("results", [])
        if not results:
            return
        yield from results

        offset += len(results)
        pages += 1
        if len(results) < page_size:
            return
        if max_pages is not None and pages >= max_pages:
            return


def dcat_rows(
    dataset_uuid: str,
    *,
    client: httpx.Client | None = None,
    page_size: int = 5000,
    refresh: bool = False,
    max_pages: int | None = None,
) -> Iterator[dict]:
    """Yield rows from a data.cms.gov data-api dataset."""
    offset = 0
    pages = 0
    while True:
        url = (
            f"{CMS_DATA_API}/dataset/{dataset_uuid}/data"
            f"?size={page_size}&offset={offset}"
        )
        payload = get_json(url, client=client, refresh=refresh)
        if isinstance(payload, dict):  # some endpoints wrap in {"data": [...]}
            payload = payload.get("data", [])
        if not payload:
            return
        yield from payload

        offset += len(payload)
        pages += 1
        if len(payload) < page_size:
            return
        if max_pages is not None and pages >= max_pages:
            return
