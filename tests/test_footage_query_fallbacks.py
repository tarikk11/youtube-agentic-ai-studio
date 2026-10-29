"""Search fallback regression tests for first cinematic documentary preview."""
from video import footage, footage_sources


def _asset(media_type="video", identity="1"):
    return {
        "id": f"commons:{identity}", "source": "Wikimedia Commons",
        "media_type": media_type,
        "title": f"Relevant {media_type}",
        "url": f"https://upload.wikimedia.org/{identity}",
        "file_extension": ".webm" if media_type == "video" else ".jpg",
        "rights_review": "pending",
    }


def test_bermuda_has_shorter_query_alternatives():
    assert footage._query_variations("Bermuda coastline aerial ocean") == [
        "Bermuda coastline aerial ocean", "Bermuda coastline", "Bermuda island",
    ]


def test_commons_still_explicitly_requests_bitmap(monkeypatch):
    calls = []
    def fake_search(query, limit=8):
        calls.append(query)
        return [_asset("video", "v"), _asset("image", "i")]
    monkeypatch.setattr(footage, "search_commons", fake_search)
    found = footage.search_commons_still("Bermuda map")
    assert [x["media_type"] for x in found] == ["image"]
    assert calls == ["Bermuda map filetype:bitmap"]


def test_video_fallback_preferred_over_still(monkeypatch):
    calls = []
    def video(query, limit=6):
        calls.append(("video", query))
        return [_asset("video", "ocean")] if query == "Atlantic ocean" else []
    monkeypatch.setattr(footage, "search_commons_video", video)
    monkeypatch.setattr(footage, "search_commons_still",
                        lambda *a, **k: AssertionError("Should not use stills"))
    monkeypatch.setattr(footage_sources, "search_internet_archive",
                        lambda *a, **k: [])
    monkeypatch.setattr(footage_sources, "search_pixabay",
                        lambda *a, **k: [])
    shots = [{"query": "Atlantic Ocean aerial drone", "intent": "stock",
              "asset": None, "download_status": "not_requested"}]
    footage.discover_assets(shots)
    assert shots[0]["asset"]["media_type"] == "video"
    assert shots[0]["selected_query"] == "Atlantic ocean"
    assert shots[0]["fallback_used"] is True
    assert calls == [
        ("video", "Atlantic Ocean aerial drone"),
        ("video", "Atlantic ocean"),
    ]


def test_historical_map_prefers_archival_still(monkeypatch):
    def still(query, limit=8):
        return [_asset("image", "map")] if query == "Bermuda map" else []
    monkeypatch.setattr(footage, "search_commons_still", still)
    monkeypatch.setattr(footage, "search_commons_video",
                        lambda *a, **k: [])
    monkeypatch.setattr(footage_sources, "search_internet_archive",
                        lambda *a, **k: [])
    shots = [{"query": "historic Atlantic nautical chart Bermuda",
              "intent": "archive", "asset": None,
              "download_status": "not_requested"}]
    footage.discover_assets(shots)
    assert shots[0]["asset"]["media_type"] == "image"
    assert shots[0]["selected_query"] == "Bermuda map"


def test_distinct_sources_or_missing_not_duplicated(monkeypatch):
    monkeypatch.setattr(footage, "search_commons_video",
                        lambda *a, **k: [_asset("video", "one")])
    monkeypatch.setattr(footage, "search_commons_still",
                        lambda *a, **k: [])
    monkeypatch.setattr(footage_sources, "search_internet_archive",
                        lambda *a, **k: [])
    shots = [
        {"query": "dark ocean storm clouds", "intent": "stock",
         "asset": None, "download_status": "not_requested"},
        {"query": "dark ocean storm clouds", "intent": "stock",
         "asset": None, "download_status": "not_requested"},
    ]
    footage.discover_assets(shots)
    assert shots[0]["asset"]["id"] == "commons:one"
    assert shots[1]["asset"] is None
    assert shots[1]["download_status"] == "missing"


def test_archive_uses_one_short_query_only(monkeypatch):
    archive_calls = []
    monkeypatch.setattr(footage, "search_commons_video", lambda *a, **k: [])
    monkeypatch.setattr(footage, "search_commons_still", lambda *a, **k: [])
    def archive(query, limit=3):
        archive_calls.append(query)
        return []
    monkeypatch.setattr(footage_sources, "search_internet_archive", archive)
    shots = [{"query": "Atlantic Ocean aerial drone", "intent": "stock",
              "asset": None, "download_status": "not_requested"}]
    footage.discover_assets(shots)
    assert archive_calls == ["Atlantic ocean"]
    assert shots[0]["download_status"] == "missing"
