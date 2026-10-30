"""Offline tests: no model download or Kokoro package required."""
import json

import numpy as np
import pytest

from video.kokoro_narrator import load_chapter_timing, script_hash, split_for_kokoro
from video.creator import _join_documentary_clips


SCRIPT = {
    "style": "sleep_documentary",
    "sections": [
        {"id": 1, "narration": "First historical chapter.", "title": "Introduction"},
        {"id": 2, "narration": "Second historical chapter.", "title": "At sea"},
    ],
}


def test_chunker_respects_limit_and_preserves_words():
    text = ("A quiet voyage crossed the ocean in October. " * 40).strip()
    chunks = split_for_kokoro(text, max_chars=180)
    assert len(chunks) > 1
    assert all(len(c) <= 180 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunker_rejects_unbreakable_token():
    with pytest.raises(ValueError, match="long unbreakable"):
        split_for_kokoro("x" * 300)


def test_timeline_matches_current_script(tmp_path):
    data = {
        "version": 1, "script_hash": script_hash(SCRIPT),
        "sections": [
            {"id": 1, "start_seconds": 0.0, "end_seconds": 2.0, "duration_seconds": 2.0},
            {"id": 2, "start_seconds": 2.0, "end_seconds": 5.0, "duration_seconds": 3.0},
        ],
    }
    (tmp_path / "narration_timing.json").write_text(json.dumps(data), encoding="utf-8")
    assert len(load_chapter_timing(SCRIPT, str(tmp_path), 5.0)) == 2
    with pytest.raises(ValueError, match="different script"):
        load_chapter_timing({**SCRIPT, "sections": [
            {**SCRIPT["sections"][0], "narration": "Changed."}, SCRIPT["sections"][1]
        ]}, str(tmp_path), 5.0)
    with pytest.raises(ValueError, match="Audio length"):
        load_chapter_timing(SCRIPT, str(tmp_path), 4.1)


def test_dissolve_does_not_shorten_video():
    class FakeClip:
        def __init__(self, duration, shade):
            self.duration = duration
            self.shade = shade

        def get_frame(self, t):
            return np.full((4, 4, 3), self.shade, dtype=np.uint8)

    joined = _join_documentary_clips(
        [FakeClip(2.0, 50), FakeClip(3.0, 200)], fade_dur=0.8
    )
    assert joined.duration == pytest.approx(5.0)
    assert joined.get_frame(1.9)[0, 0, 0] == 50
    assert joined.get_frame(2.0)[0, 0, 0] == 50
    assert 50 < joined.get_frame(2.4)[0, 0, 0] < 200
    assert joined.get_frame(2.81)[0, 0, 0] == 200
