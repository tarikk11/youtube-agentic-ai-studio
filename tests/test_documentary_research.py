"""Ensure the 10-minute pilot researcher uses the calm documentary prompt."""
import json
from agents import researcher
import config


def test_exact_topic_documentary_prompt(monkeypatch):
    prompts = []
    monkeypatch.setattr(config, "DOCUMENTARY_MODE", True, raising=False)
    monkeypatch.setattr(researcher, "load_banned_topics", lambda: [])
    monkeypatch.setattr(researcher, "_grounding", lambda topic: {
        "facts": "The Bermuda Triangle lies in the North Atlantic.",
        "sources": [],
    })

    def fake_generate(prompt):
        prompts.append(prompt)
        return json.dumps({
            "topic": "The Bermuda Triangle",
            "video_title": "The Bermuda Triangle: A Documentary",
            "description": "Explore a maritime legend.",
            "hook_question": "How did the legend begin?",
            "key_points": ["Geography", "History"],
            "tags": ["maritime history"],
        })

    monkeypatch.setattr(researcher, "generate", fake_generate)
    data = researcher.research_topic(
        "Historical mysteries, evidence-led.",
        topic_override="The Bermuda Triangle",
    )
    assert data["topic"] == "The Bermuda Triangle"
    assert len(prompts) == 1
    assert "calm long-form historical/mystery documentary" in prompts[0]
    assert "Never invent dates" in prompts[0]
    assert "clickbait" in prompts[0]
    assert data["grounding"]["sources"] == []
