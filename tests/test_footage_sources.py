"""Offline tests for keyless archive providers and optional cached Pixabay."""
import json
import time

import pytest

from video import footage, footage_sources as fs


@pytest.mark.parametrize(("url", "expected"), [
    ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
    ("https://creativecommons.org/publicdomain/mark/1.0/", "Public Domain Mark"),
    ("http://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
    ("https://creativecommons.org/licenses/by-sa/3.0/", "CC BY-SA 3.0"),
    ("https://creativecommons.org/licenses/by-nc/4.0/", None),
    ("https://creativecommons.org/licenses/by-nd/4.0/", None),
    ("https://example.com/licenses/by/4.0/", None),
    ("", None),
])
def test_archive_license_accepts_only_commercial_permissions(url, expected):
    assert fs._archive_licence(url) == expected


def test_pixabay_video_cache_prevents_duplicate_calls(monkeypatch, tmp_path):
    calls = []
    def fake_api(url, params=None):
        calls.append((url, params))
        assert params["key"] == "test-secret-key"
        return {"hits": [{
            "id": 50, "user": "Creator", "pageURL": "https://pixabay.com/videos/id-50/",
            "duration": 12, "tags": "atlantic ocean",
            "videos": {
                "medium": {"url": "https://cdn.pixabay.com/video/ocean_medium.mp4",
                           "width": 1920, "height": 1080, "size": 1000000},
                "large": {"url": "https://cdn.pixabay.com/video/ocean_large.mp4",
                          "width": 3840, "height": 2160, "size": 20000000},
            },
        }]}
    monkeypatch.setattr(fs, "_json_get", fake_api)
    output = fs.search_pixabay("ocean", "test-secret-key", cache_dir=str(tmp_path))
    cached = fs.search_pixabay("ocean", "test-secret-key", cache_dir=str(tmp_path))
    assert len(calls) == 1
    assert output == cached
    assert output[0]["url"].endswith("medium.mp4")
    assert output[0]["rights_review"] == "pending"
    assert "test-secret-key" not in (tmp_path / next(p.name for p in tmp_path.iterdir())).read_text()
    assert fs.search_pixabay("ocean", "", cache_dir=str(tmp_path)) == []


def test_pixabay_cache_expired(monkeypatch, tmp_path):
    count = 0
    def fake_api(url, params=None):
        nonlocal count
        count += 1
        return {"hits": []}
    monkeypatch.setattr(fs, "_json_get", fake_api)
    fs.search_pixabay("new query", "secret", cache_dir=str(tmp_path))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data["saved_at"] = time.time() - fs.CACHE_SECONDS - 10
    path.write_text(json.dumps(data))
    fs.search_pixabay("new query", "secret", cache_dir=str(tmp_path))
    assert count == 2


def test_archive_item_requires_valid_cc_and_small_mp4(monkeypatch):
    calls = []
    def fake_api(url, params=None):
        calls.append(url)
        if url == fs.ARCHIVE_SEARCH:
            return {"response": {"docs": [
                {"identifier": "allowed-clip", "title": "Allowed"},
                {"identifier": "restricted-clip", "title": "Restricted"},
            ]}}
        if url.endswith("/allowed-clip"):
            return {"metadata": {
                "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                "title": "Atlantic Ocean footage", "creator": "Archivist",
            }, "files": [
                {"name": "a.mp4", "size": "9000", "source": "original"},
                {"name": "big.mp4", "size": str(fs.MAX_DOWNLOAD_SIZE + 1),
                 "source": "original"},
            ]}
        if url.endswith("/restricted-clip"):
            return {"metadata": {
                "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"
            }, "files": [{"name": "b.mp4", "size": "9000", "source": "original"}]}
        raise AssertionError("Unexpected URL: " + url)
    monkeypatch.setattr(fs, "_json_get", fake_api)
    results = fs.search_internet_archive("Atlantic ocean", limit=3)
    assert len(results) == 1
    assert results[0]["license"] == "CC BY 4.0"
    assert results[0]["url"] == "https://archive.org/download/allowed-clip/a.mp4"
    assert results[0]["rights_review"] == "pending"
    assert len(calls) == 3


def test_archive_skips_missing_license_and_unsafe_names(monkeypatch):
    def fake_api(url, params=None):
        if url == fs.ARCHIVE_SEARCH:
            return {"response": {"docs": [{"identifier": "only-entry"}]}}
        return {"metadata": {"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/"},
                "files": [{"name": "../secret.mp4", "size": "10000"},
                          {"name": "huge.mp4", "size": str(2 ** 34)}]}
    monkeypatch.setattr(fs, "_json_get", fake_api)
    assert fs.search_internet_archive("ocean") == []


def test_provider_routing_never_requires_pexels(monkeypatch, tmp_path):
    called = []
    def commons(query, limit=6):
        called.append(("commons", query))
        return [{
            "id": "commons:10", "source": "Wikimedia Commons",
            "media_type": "video", "url": "https://upload.wikimedia.org/example.webm",
            "file_extension": ".webm", "rights_review": "pending",
        }]
    monkeypatch.setattr(footage, "search_commons_video", commons)
    monkeypatch.setattr(footage, "search_commons", lambda *a, **k: [])
    monkeypatch.setattr(fs, "search_internet_archive",
                        lambda *a, **k: pytest.fail("Other provider unnecessary"))
    monkeypatch.setattr(fs, "search_pixabay",
                        lambda *a, **k: pytest.fail("Pixabay should be skipped without key"))
    shots = [{"query": "ocean", "intent": "stock", "asset": None,
              "download_status": "not_requested"}]
    footage.discover_assets(shots, pixabay_key="", cache_dir=str(tmp_path))
    assert shots[0]["asset"]["id"] == "commons:10"
    assert called == [("commons", "ocean")]


@pytest.mark.parametrize(("url", "allowed"), [
    ("https://cdn.pixabay.com/video/test.mp4", True),
    ("https://upload.wikimedia.org/path/example.webm", True),
    ("https://archive.org/download/example/test.mp4", True),
    ("https://ia600000.us.archive.org/test.mp4", True),
    ("http://archive.org/download/example/test.mp4", False),
    ("https://archive.org.attacker.invalid/test.mp4", False),
    ("https://random.example/clip.mp4", False),
])
def test_permitted_video_download_hosts(url, allowed):
    assert footage._allowed_download_url(url) is allowed
