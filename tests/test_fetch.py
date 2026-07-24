import httpx
import pytest

from hhpanel import fetch


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "CACHE_DIR", tmp_path / "cache")


def client_returning(pages):
    """A mock transport that serves successive pages by offset."""

    def handler(request):
        offset = int(request.url.params.get("offset", 0))
        index = offset // 2
        rows = pages[index] if index < len(pages) else []
        return httpx.Response(200, json={"results": rows})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pdc_rows_paginates_until_short_page():
    pages = [[{"i": 0}, {"i": 1}], [{"i": 2}]]
    with client_returning(pages) as client:
        rows = list(fetch.pdc_rows("dist-x", client=client, page_size=2))
    assert [r["i"] for r in rows] == [0, 1, 2]


def test_max_pages_caps_the_pull():
    pages = [[{"i": 0}, {"i": 1}], [{"i": 2}, {"i": 3}]]
    with client_returning(pages) as client:
        rows = list(fetch.pdc_rows("dist-x", client=client, page_size=2, max_pages=1))
    assert len(rows) == 2


def test_get_json_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch.get_json("https://x.test/a", client=client) == {"ok": True}
    assert calls["n"] == 3


def test_get_json_gives_up_with_actionable_message(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda *_: None)
    handler = lambda request: httpx.Response(500)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="hhpanel discover"):
            fetch.get_json("https://x.test/b", client=client, max_attempts=2)


def test_second_call_is_served_from_cache():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"v": calls["n"]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = fetch.get_json("https://x.test/c", client=client)
        second = fetch.get_json("https://x.test/c", client=client)
    assert first == second == {"v": 1}
    assert calls["n"] == 1
