"""Offline tests for the new documentary script-writing path."""
import json

import pytest

import config
from agents import documentary
from agents import scriptwriter


RESEARCH = {
    "topic": "The Bermuda Triangle",
    "video_title": "The Bermuda Triangle: A Quiet History",
    "description": "An evidence-led investigation.",
    "tags": ["history", "ocean"],
    "key_points": ["Geography", "Documented incidents", "Alternative explanations"],
    "grounding": {"facts": "The region is in the western North Atlantic.",
                  "sources": [{"source": "Wikipedia", "title": "Bermuda Triangle",
                               "url": "https://en.wikipedia.org/wiki/Bermuda_Triangle"}]},
}


def test_duration_presets_and_chapter_counts():
    assert documentary.chapter_count(10) == 4
    assert documentary.chapter_count(30) == 10
    assert documentary.chapter_count(60) == 20
    assert documentary.chapter_count(90) == 30
    with pytest.raises(ValueError):
        documentary.chapter_count(13)


def test_documentary_creates_chapters_without_hype(monkeypatch):
    calls = []
    chapters = [{
        "title": f"Chapter {i + 1}",
        "focus": f"Historical period {i + 1}",
        "image_query": "historical nautical map",
        "image_query_2": "North Atlantic coastline",
        "image_query_3": "old navigation compass",
    } for i in range(4)]

    def fake_generate(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps({"chapters": chapters})
        # More than 75% of the ~295-word target, so no retry is required.
        return json.dumps({"narration": "The calm Atlantic ocean extends ahead. " * 48})

    monkeypatch.setattr(documentary, "generate", fake_generate)
    result = documentary.write_documentary_script(RESEARCH, target_minutes=10)
    assert len(calls) == 5  # one outline plus four separate chapter calls
    assert result["style"] == "sleep_documentary"
    assert result["target_minutes"] == 10
    assert result["video_type"] == "normal"
    assert len(result["sections"]) == 4
    assert all(s["section_type"] == "documentary" for s in result["sections"])
    assert all(len(s["narration"].split()) >= 225 for s in result["sections"])
    assert not any(s["section_type"] == "cta" for s in result["sections"])
    assert "Distinguish documented evidence" in calls[0]


def test_short_outline_aborts_instead_of_filling_silently(monkeypatch):
    monkeypatch.setattr(
        documentary, "generate",
        lambda prompt: json.dumps({"chapters": [{"focus": "Only one"}]})
    )
    with pytest.raises(ValueError, match="expected 4"):
        documentary.write_documentary_script(RESEARCH, 10)


def test_normal_routes_to_documentary_and_shorts_unchanged(monkeypatch):
    monkeypatch.setattr(config, "DOCUMENTARY_MODE", True, raising=False)
    monkeypatch.setattr(config, "DOCUMENTARY_TARGET_MINUTES", 30, raising=False)

    from agents import documentary as module
    monkeypatch.setattr(module, "write_documentary_script",
                        lambda research, target_minutes: {
                            "style": "sleep_documentary",
                            "target_minutes": target_minutes
                        })
    assert scriptwriter.write_script(RESEARCH, video_type="normal") == {
        "style": "sleep_documentary", "target_minutes": 30
    }
    monkeypatch.setattr(scriptwriter, "_write_shorts_script", lambda r: {"video_type": "shorts"})
    assert scriptwriter.write_script(RESEARCH, video_type="shorts") == {"video_type": "shorts"}
