"""No-network regression tests for documentary footage sourcing."""
import json

import pytest

from video import footage
from video.kokoro_narrator import script_hash


@pytest.mark.parametrize(("license_name", "expected"), [
    ("CC0 1.0", True),
    ("Public domain", True),
    ("PD-USGov", True),
    ("CC BY 4.0", True),
    ("CC BY-SA 3.0", True),
    ("CC BY-NC 4.0", False),
    ("CC BY-ND 4.0", False),
    ("All rights reserved", False),
    ("", False),
])
def test_commons_license_filter(license_name, expected):
    assert footage._license_eligible(license_name) is expected


def test_pexels_selects_1080p_mp4(monkeypatch):
    def fake_api(url, *, params, headers=None):
        assert url.endswith("/v1/videos/search")
        assert headers["Authorization"] == "test-key"
        return {"videos": [{
            "id": 123, "url": "https://www.pexels.com/video/123",
            "duration": 20, "user": {"name": "Example creator"},
            "video_files": [
                {"file_type": "video/mp4", "width": 3840, "height": 2160,
                 "link": "https://videos.pexels.com/4k.mp4"},
                {"file_type": "video/mp4", "width": 1920, "height": 1080,
                 "link": "https://videos.pexels.com/hd.mp4"},
                {"file_type": "video/webm", "width": 1920, "height": 1080,
                 "link": "https://videos.pexels.com/video.webm"},
            ],
        }]}
    monkeypatch.setattr(footage, "_api_json", fake_api)
    assets = footage.search_pexels("Bermuda ocean", "test-key")
    assert len(assets) == 1
    assert assets[0]["url"].endswith("/hd.mp4")
    assert assets[0]["license"] == "Pexels License"
    assert assets[0]["rights_review"] == "pending"


def test_commons_filters_no_derivatives_and_prioritizes_video(monkeypatch):
    def sample(pageid, mime, license_name, suffix):
        return {
            "pageid": pageid,
            "title": f"File:Sample{pageid}{suffix}",
            "imageinfo": [{
                "url": f"https://upload.wikimedia.org/wikipedia/commons/{pageid}{suffix}",
                "mime": mime,
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Sample",
                "extmetadata": {
                    "LicenseShortName": {"value": license_name},
                    "Artist": {"value": "<b>Archive</b>"},
                },
            }],
        }
    monkeypatch.setattr(footage, "_api_json", lambda *a, **k: {
        "query": {"pages": {
            "1": sample(1, "image/jpeg", "CC BY 4.0", ".jpg"),
            "2": sample(2, "video/webm", "CC BY-SA 4.0", ".webm"),
            "3": sample(3, "image/png", "CC BY-ND 4.0", ".png"),
        }}
    })
    assets = footage.search_commons("nautical maps")
    assert [a["id"] for a in assets] == ["commons:2", "commons:1"]
    assert assets[0]["media_type"] == "video"
    assert assets[0]["creator"] == "Archive"
    assert all(a["rights_review"] == "pending" for a in assets)


def test_preview_respects_exact_chapter_boundaries():
    script = {
        "title": "The Bermuda Triangle",
        "sections": [
            {"id": 1, "title": "The Ocean Highway", "image_query": "ocean"},
            {"id": 2, "title": "Vanished", "image_query": "archival ship"},
        ],
    }
    spans = [
        {"id": 1, "start_seconds": 0, "end_seconds": 35},
        {"id": 2, "start_seconds": 35, "end_seconds": 125},
    ]
    shots = footage.plan_preview(script, spans, seconds=90)
    assert [(s["start_seconds"], s["end_seconds"]) for s in shots] == [
        (0, 15), (15, 30), (30, 35), (35, 50), (50, 65),
        (65, 80), (80, 90),
    ]
    assert shots[2]["chapter_id"] == 1
    assert shots[3]["chapter_id"] == 2
    assert shots[0]["intent"] == "stock"


def test_manifest_plan_only_uses_hash_and_never_calls_web(monkeypatch, tmp_path):
    script = {
        "title": "The Bermuda Triangle",
        "style": "sleep_documentary",
        "sections": [{"id": 1, "title": "Ocean", "narration": "A calm ocean."}],
    }
    (tmp_path / "script.json").write_text(json.dumps(script), encoding="utf-8")
    timing = {
        "script_hash": script_hash(script),
        "total_duration_seconds": 30,
        "sections": [{"id": 1, "start_seconds": 0,
                      "end_seconds": 30, "duration_seconds": 30}],
    }
    (tmp_path / "narration_timing.json").write_text(
        json.dumps(timing), encoding="utf-8"
    )
    def not_allowed(*a, **kw):
        raise AssertionError("Plan-only mode must never use the network.")
    monkeypatch.setattr(footage.requests, "get", not_allowed)
    before = (tmp_path / "script.json").read_bytes()
    path = footage.create_preview_manifest(str(tmp_path), plan_only=True)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert len(manifest["shots"]) == 2
    assert all(x["asset"] is None for x in manifest["shots"])
    assert manifest["status"] == "needs_human_review"
    assert (tmp_path / "script.json").read_bytes() == before


def test_manifest_rejects_stale_script_hash(tmp_path):
    script = {
        "title": "Changed script",
        "sections": [{"id": 1, "narration": "New version"}],
    }
    (tmp_path / "script.json").write_text(json.dumps(script), encoding="utf-8")
    timing = {
        "script_hash": "wrong hash",
        "total_duration_seconds": 25,
        "sections": [{"id": 1, "start_seconds": 0,
                      "end_seconds": 25, "duration_seconds": 25}],
    }
    (tmp_path / "narration_timing.json").write_text(json.dumps(timing),
                                                      encoding="utf-8")
    with pytest.raises(ValueError, match="different script"):
        footage.create_preview_manifest(str(tmp_path), plan_only=True)


def test_download_blocks_other_domains(tmp_path):
    with pytest.raises(ValueError, match="approved HTTPS CDN"):
        footage.download_asset({
            "url": "https://evil.example/file.mp4", "media_type": "video"
        }, tmp_path / "shot_01.mp4")


def test_download_enforces_size_limit_and_cleans_partial(monkeypatch, tmp_path):
    class FakeResponse:
        url = "https://videos.pexels.com/test.mp4"
        headers = {"Content-Type": "video/mp4", "Content-Length": "500"}
        def raise_for_status(self):
            return None
        def iter_content(self, chunk_size):
            yield b"A" * 500
            yield b"B" * 600
        def close(self):
            pass
    monkeypatch.setattr(footage.requests, "get",
                        lambda *a, **k: FakeResponse())
    dest = tmp_path / "shot_01.mp4"
    with pytest.raises(ValueError, match="size limit"):
        footage.download_asset({
            "url": FakeResponse.url, "media_type": "video"
        }, dest, max_bytes=1000)
    assert not dest.exists()
    assert not (tmp_path / "shot_01.mp4.part").exists()


def test_download_writes_approved_file(monkeypatch, tmp_path):
    class FakeResponse:
        url = "https://upload.wikimedia.org/wikipedia/commons/test.webm"
        headers = {"Content-Type": "video/webm"}
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size):
            yield b"A" * 2048
        def close(self):
            pass
    monkeypatch.setattr(footage.requests, "get",
                        lambda *a, **k: FakeResponse())
    dest = tmp_path / "shot_01.webm"
    n = footage.download_asset({
        "url": FakeResponse.url, "media_type": "video"
    }, dest)
    assert n == 2048
    assert dest.stat().st_size == 2048
