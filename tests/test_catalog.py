import json
from pathlib import Path

import pytest

from hhpanel import catalog
from hhpanel.config import Source

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def stub_catalogs(monkeypatch):
    monkeypatch.setattr(catalog, "pdc_catalog", lambda *a, **k: load("pdc_catalog.json"))
    monkeypatch.setattr(
        catalog, "dcat_catalog", lambda *a, **k: load("dcat_catalog.json")["dataset"]
    )


def test_resolves_both_portals(stub_catalogs):
    sources = [
        Source("hha_quality", "pdc", "Home Health Care Agencies", "outcome"),
        Source("hha_owners", "dcat", "Home Health Agency All Owners", "treatment"),
    ]
    resolved = {r.key: r for r in catalog.resolve(sources)}
    assert resolved["hha_quality"].dataset_id == "dist-hha-2026-04"
    assert resolved["hha_owners"].dataset_id == "9767cb68-3f34-4c47-9c5f-70a4a1b0b6a2"


def test_prefers_most_recently_modified_match(stub_catalogs):
    sources = [Source("hha_quality", "pdc", "Home Health Care", "outcome")]
    assert catalog.resolve(sources)[0].modified == "2026-04-15"


def test_missing_dataset_suggests_alternatives(stub_catalogs):
    sources = [Source("nope", "pdc", "Hospice Care Agencies", "outcome")]
    with pytest.raises(catalog.DatasetNotFound) as exc:
        catalog.resolve(sources)
    assert "Closest available titles" in str(exc.value)


def test_optional_dataset_is_skipped(stub_catalogs):
    sources = [Source("nope", "pdc", "Hospice", "outcome", required=False)]
    assert catalog.resolve(sources) == []


def test_bad_portal_is_rejected_at_config_time():
    with pytest.raises(ValueError, match="sources.json"):
        Source("x", "ftp", "whatever", "role")


def test_round_trips_through_disk(stub_catalogs, tmp_path):
    sources = [Source("hha_quality", "pdc", "Home Health Care Agencies", "outcome")]
    resolved = catalog.resolve(sources)
    path = catalog.save_resolved(resolved, tmp_path / "resolved.json")
    assert catalog.load_resolved(path) == resolved
