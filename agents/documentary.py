"""Long-form, calm, chaptered documentary script generation.

Each chapter is generated in a separate model call. This avoids asking a text
model to return a 30–90 minute script in a single response, which can truncate.
This is script generation only: real duration, factual accuracy, and media
licences must still be checked before publication.
"""
import math

from agents.gemini_client import generate
from agents.json_utils import extract_json

# A 10-minute pilot first; other presets are intentionally unlocked for later.
SUPPORTED_MINUTES = (10, 30, 60, 90)
NARRATION_WPM = 118
CHAPTER_TARGET_MINUTES = 3


def chapter_count(target_minutes: int) -> int:
    """Approximately three minutes per chapter, with at least three chapters."""
    if target_minutes not in SUPPORTED_MINUTES:
        raise ValueError(
            f"Documentary duration must be one of {SUPPORTED_MINUTES}, "
            f"not {target_minutes!r}."
        )
    return max(3, math.ceil(target_minutes / CHAPTER_TARGET_MINUTES))


def _grounding(research: dict) -> str:
    info = research.get("grounding") or {}
    facts = (info.get("facts") or "").strip()
    sources = info.get("sources") or []
    links = "\n".join(
        f"- {s.get('source', 'Source')}: {s.get('title', '')} ({s.get('url', '')})"
        for s in sources if isinstance(s, dict)
    )
    return (f"RESEARCH NOTES (not independently verified by the generator):\n"
            f"{facts[:6500] or 'No background facts supplied.'}\n"
            f"SOURCE LINKS:\n{links[:3000] or 'None supplied.'}")


def _outline(research: dict, target_minutes: int) -> list:
    count = chapter_count(target_minutes)
    key_points = research.get("key_points") or []
    prompt = f"""You are planning a well-researched, original, bedtime-friendly
history and mysteries documentary. Create exactly {count} chronological or
thematically progressive chapters for a {target_minutes}-minute documentary.

SUBJECT: {research.get('topic', '')}
VIDEO TITLE: {research.get('video_title', '')}
KEY POINTS: {key_points}
{_grounding(research)}

Editorial requirements:
- Calm, immersive, informative, with gentle curiosity rather than sensationalism.
- Preserve chronological coherence and avoid repeated ideas across chapters.
- Distinguish documented evidence from hypothesis, folklore and speculation.
- Do not fabricate eyewitness accounts, quotations, dates or discoveries.
- Do not assert that a legend has been proven merely because it is interesting.
- Open with location and atmosphere, then investigate evidence and alternatives.
- The ending should be a satisfying quiet reflection, never a subscribe CTA.
- Select three DIFFERENT, concrete archive/stock photo search terms per chapter.
- Every source link supplied is a lead, not proof that a claim was verified.
- Do not use generic "shocked face", neon, sci-fi or clickbait imagery.

Return ONLY JSON with exactly this structure:
{{
  "chapters": [
    {{
      "title": "Meaningful short chapter title",
      "focus": "New facts, chronology and purpose of this chapter; no repetition",
      "image_query": "Specific historic or geographic scene",
      "image_query_2": "Specific relevant archival photograph or map",
      "image_query_3": "Specific calm landscape or visual detail"
    }}
  ]
}}
Ensure the chapters array contains EXACTLY {count} objects."""
    data = extract_json(generate(prompt), "Documentary outline")
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != count:
        raise ValueError(
            f"Documentary outline returned {len(chapters) if isinstance(chapters, list) else 0} "
            f"chapters; expected {count}. Retry before rendering."
        )
    for chapter in chapters:
        if not isinstance(chapter, dict) or not str(chapter.get("focus", "")).strip():
            raise ValueError("Documentary outline contains a chapter with no focus.")
    return chapters


def _write_chapter(research: dict, chapters: list, index: int,
                   words_target: int) -> str:
    current = chapters[index]
    previous = chapters[index - 1]["focus"] if index else "None"
    following = chapters[index + 1]["focus"] if index + 1 < len(chapters) else "None"
    is_last = index == len(chapters) - 1
    prompt = f"""Write ONE complete chapter of an original, calm, immersive
mystery/historical documentary intended for relaxed evening listening.

TOPIC: {research.get('topic', '')}
CHAPTER {index + 1} OF {len(chapters)}: {current.get('title', '')}
THIS CHAPTER MUST COVER: {current.get('focus', '')}
PREVIOUS CHAPTER FOCUS (avoid repetition): {previous}
NEXT CHAPTER FOCUS (save this material for later): {following}
{_grounding(research)}

Aim for {words_target} spoken words, in complete connected paragraphs.
The length matters: do not return a summary or outline.
Narration should sound natural in a warm, unhurried British documentary voice.
Describe locations, atmosphere, context and evidence in plain English.
Use smooth transitions and gentle rhythm; no shouting, hype, jump scares,
aggressive re-hooks, rhetorical-question chains or repeated recaps.
No section headings, sound cues, bracketed instructions, visual directions,
citations read out loud, direct calls to action, or "like and subscribe".
Do not claim to have investigated primary documents unless supplied.
If important claims cannot be verified from the supplied material, state the
uncertainty naturally; never invent a precise date, a quote or a source.
{"Close the whole documentary with a reflective final paragraph." if is_last else "End with a natural bridge toward what follows."}

Return ONLY JSON: {{"narration": "The COMPLETE spoken chapter, with paragraphs."}}"""
    best = ""
    for attempt in range(2):
        data = extract_json(generate(prompt + (
            "\nIMPORTANT: The previous response was too short; write the entire "
            f"{words_target}-word chapter, not a synopsis." if attempt else ""
        )), f"Documentary chapter {index + 1}")
        narration = data.get("narration", "")
        if not isinstance(narration, str) or not narration.strip():
            raise ValueError(f"Chapter {index + 1} returned no narration.")
        if len(narration.split()) > len(best.split()):
            best = narration.strip()
        if len(best.split()) >= round(words_target * 0.75):
            break
    if len(best.split()) < round(words_target * 0.60):
        raise ValueError(
            f"Chapter {index + 1} is significantly shorter than requested "
            f"({len(best.split())}/{words_target} words). Stop for review."
        )
    return best


def write_documentary_script(research: dict, target_minutes: int = 10) -> dict:
    """Return the existing YAAS section schema, with documentary metadata."""
    count = chapter_count(target_minutes)
    chapters = _outline(research, target_minutes)
    total_words = target_minutes * NARRATION_WPM
    # Divide requested speech evenly; chapters get their own independent calls.
    words_each = round(total_words / count)
    sections = []
    for index, chapter in enumerate(chapters):
        narration = _write_chapter(research, chapters, index, words_each)
        words = len(narration.split())
        sections.append({
            "id": index + 1,
            "section_type": "documentary",
            "title": str(chapter.get("title", f"Chapter {index + 1}")),
            "narration": narration,
            "image_query": str(chapter.get("image_query", "")),
            "image_query_2": str(chapter.get("image_query_2", "")),
            "image_query_3": str(chapter.get("image_query_3", "")),
            "bullet_points": [],
            "caption_text": "",
            "duration_seconds": round(words / NARRATION_WPM * 60),
        })
    words_total = sum(len(s["narration"].split()) for s in sections)
    return {
        "title": research.get("video_title") or research.get("topic") or "Mystery Documentary",
        "description": research.get("description", ""),
        "tags": research.get("tags", []),
        "video_type": "normal",
        "style": "sleep_documentary",
        "target_minutes": target_minutes,
        "estimated_minutes": round(words_total / NARRATION_WPM, 1),
        "sections": sections,
    }
