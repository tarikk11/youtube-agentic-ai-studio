"""Rights-aware footage discovery for the documentary preview.

This is intentionally separate from YAAS's still-image renderer. Nothing in
this module modifies the script, audio, existing images or video output.
A search result is NEVER automatically considered legally cleared.
"""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

import config
from video.kokoro_narrator import load_chapter_timing

PEXELS_API = "https://api.pexels.com/v1/videos/search"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PEXELS_LICENSE = "https://www.pexels.com/license"
MAX_FILE_BYTES = 80 * 1024 * 1024
USER_AGENT = (
    "MysteriesDocumentaryStudio/0.1 "
    "(https://github.com/tarikk11/youtube-agentic-ai-studio)"
)

# This first preview has a hand-authored, historically cautious visual outline.
# It uses generic B-roll as illustration, never as footage of an actual incident.
BERMUDA_OPENING = [
    ("Atlantic Ocean aerial drone", "stock", "Open Atlantic aerial"),
    ("Bermuda coastline aerial ocean", "stock", "Bermuda geography"),
    ("historic Atlantic nautical chart Bermuda", "archive", "Historical map"),
    ("turquoise ocean water aerial", "stock", "Atlantic seascape"),
    ("historical sailing ship ocean", "archive", "Historical maritime illustration"),
    ("dark ocean storm clouds", "stock", "Changing weather"),
]


def _plain(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).strip()


def _license_eligible(name: str) -> bool:
    """Conservative catalogue filter, not a legal determination."""
    value = name.strip().lower()
    if value in ("cc0", "cc0 1.0", "public domain", "pd", "pd-usgov"):
        return True
    if value.startswith("pd-"):
        return True
    return bool(re.fullmatch(r"cc by(?:-sa)? (?:[1-4]\.0)", value))


def _api_json(url: str, *, params: dict, headers: dict | None = None) -> dict:
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    response = requests.get(url, params=params, headers=merged, timeout=22)
    response.raise_for_status()
    return response.json()


def search_pexels(query: str, api_key: str, limit: int = 4) -> list[dict]:
    """Search Pexels VIDEOS, preferring standard HD MP4 files."""
    if not api_key or api_key.upper().startswith("YOUR_"):
        return []
    data = _api_json(
        PEXELS_API,
        params={"query": query, "per_page": min(15, max(limit, 4)),
                "orientation": "landscape"},
        headers={"Authorization": api_key},
    )
    assets = []
    for video in data.get("videos", []):
        files = [
            f for f in video.get("video_files", [])
            if f.get("file_type") == "video/mp4"
            and f.get("link", "").startswith("https://")
            and int(f.get("width") or 0) >= 640
        ]
        if not files:
            continue
        # Prefer 1080p or 720p and avoid downloading 4K source files.
        files.sort(key=lambda f: (
            abs((f.get("height") or 0) - 1080),
            abs((f.get("width") or 0) - 1920),
        ))
        chosen = files[0]
        author = video.get("user") or {}
        assets.append({
            "id": f"pexels:{video['id']}",
            "source": "Pexels",
            "media_type": "video",
            "title": f"Pexels video {video['id']}",
            "url": chosen["link"],
            "page_url": video.get("url", ""),
            "creator": author.get("name", ""),
            "license": "Pexels License",
            "license_url": PEXELS_LICENSE,
            "mime_type": "video/mp4",
            "width": chosen.get("width"),
            "height": chosen.get("height"),
            "duration_seconds": video.get("duration"),
            "file_extension": ".mp4",
            "rights_review": "pending",
            "historical_authenticity": "illustrative_only",
        })
        if len(assets) >= limit:
            break
    return assets


def search_commons(query: str, limit: int = 8) -> list[dict]:
    """Search Wikimedia Commons video/stills with licence metadata.

    Unknown, noncommercial or no-derivatives licences are excluded. A human
    still must confirm item descriptions, authorship and attribution.
    """
    data = _api_json(
        COMMONS_API,
        params={
            "action": "query", "generator": "search", "gsrsearch": query,
            "gsrnamespace": 6, "gsrlimit": min(20, max(8, limit)),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit",
            "format": "json",
        },
    )
    results = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _plain(meta.get("LicenseShortName", {}).get("value", ""))
        media_url = info.get("url", "")
        mime = info.get("mime", "")
        if not _license_eligible(license_name) or not media_url.startswith("https://"):
            continue
        if mime in ("video/webm", "video/ogg", "video/mp4"):
            kind = "video"
            extension = {"video/webm": ".webm", "video/ogg": ".ogv",
                         "video/mp4": ".mp4"}[mime]
        elif mime in ("image/jpeg", "image/png"):
            kind = "image"
            extension = ".jpg" if mime == "image/jpeg" else ".png"
        else:
            continue
        # Prefer video; images make the archive fallback useful without Pexels.
        results.append({
            "id": f"commons:{page['pageid']}",
            "source": "Wikimedia Commons",
            "media_type": kind,
            "title": page.get("title", ""),
            "url": media_url,
            "page_url": info.get("descriptionurl", ""),
            "creator": _plain(meta.get("Artist", {}).get("value", ""))[:300],
            "license": license_name,
            "license_url": _plain(meta.get("LicenseUrl", {}).get("value", "")),
            "mime_type": mime,
            "width": info.get("width"),
            "height": info.get("height"),
            "duration_seconds": None,
            "file_extension": extension,
            "rights_review": "pending",
            "historical_authenticity": "unverified",
        })
    results.sort(key=lambda r: r["media_type"] != "video")
    return results[:limit]


def search_commons_video(query: str, limit: int = 6) -> list[dict]:
    """Video-only Commons search; do not silently substitute stills."""
    items = search_commons(query + " filetype:video", limit=limit)
    return [item for item in items if item["media_type"] == "video"]


def plan_preview(script: dict, spans: list[dict], seconds: float = 90,
                 shot_seconds: float = 15) -> list[dict]:
    """Generate deterministic scene slots aligned to measured chapter bounds."""
    if seconds <= 0 or shot_seconds <= 0:
        raise ValueError("Preview and shot duration must be positive.")
    if not spans or not script.get("sections"):
        raise ValueError("Generate the narration timeline before planning footage.")
    section_lookup = {s["id"]: s for s in script["sections"]}
    limit = min(float(seconds), float(spans[-1]["end_seconds"]))
    shots = []
    t = 0.0
    while t < limit - 0.001:
        span = next((s for s in spans if s["start_seconds"] <= t < s["end_seconds"]), None)
        if span is None:
            raise ValueError("Chapter timing has a gap.")
        section = section_lookup[span["id"]]
        end = min(t + shot_seconds, limit, float(span["end_seconds"]))
        if end <= t:
            raise ValueError("Invalid preview timing.")
        i = len(shots)
        if "bermuda triangle" in script.get("title", "").lower() and span["id"] == script["sections"][0]["id"]:
            query, intent, label = BERMUDA_OPENING[i % len(BERMUDA_OPENING)]
        else:
            queries = [
                str(section.get(k) or "").strip()
                for k in ("image_query", "image_query_2", "image_query_3")
            ]
            queries = [q for q in queries if q] or [script.get("title", "ocean")]
            query = queries[i % len(queries)]
            intent = "archive" if re.search(r"historic|archive|vintage|map|naval|photo", query, re.I) else "stock"
            label = section.get("title", "Documentary scene")
        shots.append({
            "shot": i + 1,
            "chapter_id": span["id"],
            "start_seconds": round(t, 3),
            "end_seconds": round(end, 3),
            "duration_seconds": round(end - t, 3),
            "query": query,
            "intent": intent,
            "label": label,
            "asset": None,
            "file": None,
            "download_status": "not_requested",
        })
        t = end
    return shots


# Curated initial pilot fallbacks. Keep geographical/historical intent intact:
# "Bermuda" should never silently turn into an unrelated tropical island.
BERMUDA_FALLBACK_QUERIES = {
    "Atlantic Ocean aerial drone": ["Atlantic ocean", "ocean aerial"],
    "Bermuda coastline aerial ocean": ["Bermuda coastline", "Bermuda island"],
    "historic Atlantic nautical chart Bermuda": ["Bermuda map", "Atlantic nautical chart"],
    "turquoise ocean water aerial": ["turquoise sea", "ocean water aerial"],
    "historical sailing ship ocean": ["sailing ship", "tall ship"],
    "dark ocean storm clouds": ["ocean storm", "storm clouds"],
}


def _query_variations(query: str) -> list[str]:
    """A few bounded, specific searches instead of one overconstrained phrase."""
    alternatives = BERMUDA_FALLBACK_QUERIES.get(query, [])
    if not alternatives:
        # For non-pilot documentary chapters, simplify without replacing the
        # original subject with generic stock footage.
        words = query.split()
        alternatives = [" ".join(words[:3])] if len(words) > 3 else []
    return list(dict.fromkeys([query, *alternatives]))[:3]


def discover_assets(shots: list[dict], *, pixabay_key: str = "",
                    cache_dir: str = "output/footage/.pixabay-cache") -> list[dict]:
    """Find distinct footage with bounded query retries, then eligible stills.

    Relevant archival maps are intentionally stills. Every other scene prefers
    real moving footage before considering an illustrated fallback.
    """
    from video.footage_sources import search_pixabay, search_internet_archive
    used = set()
    cache = {}

    for shot in shots:
        queries = _query_variations(shot["query"])
        # A literal historical map is a more faithful visual than unrelated
        # stock footage merely matching the word "Atlantic".
        map_scene = shot["intent"] == "archive" and bool(
            re.search(r"\b(map|chart|document|logbook)\b", shot["query"], re.I)
        )
        chosen = None
        matched_query = None

        def candidates(provider, query):
            key = (provider, query)
            if key not in cache:
                try:
                    if provider == "commons_video":
                        cache[key] = search_commons_video(query)
                    elif provider == "commons_still":
                        cache[key] = search_commons(query)
                    elif provider == "archive_video":
                        cache[key] = search_internet_archive(query)
                    elif provider == "pixabay":
                        cache[key] = search_pixabay(query, pixabay_key, cache_dir=cache_dir)
                    else:
                        raise ValueError("Unknown media provider")
                except (requests.RequestException, ValueError, KeyError, OSError) as exc:
                    # Provider exceptions may contain API credentials in URLs.
                    shot.setdefault("warnings", []).append(
                        f"{provider} search failed: {type(exc).__name__}"
                    )
                    cache[key] = []
            return cache[key]

        # For geographical maps, prioritize actual archival stills first.
        if map_scene:
            stages = [("commons_still", "image"), ("commons_video", "video")]
        else:
            stages = []
            if pixabay_key and not pixabay_key.upper().startswith("YOUR_") and shot["intent"] != "archive":
                stages.append(("pixabay", "video"))
            stages.extend([
                ("commons_video", "video"),
                ("archive_video", "video"),
                ("commons_still", "image"),
            ])

        for provider, desired_type in stages:
            if chosen:
                break
            # Internet Archive searches can be very costly (one request per
            # result's metadata), so try only the first two query variants.
            selected_queries = queries[:2] if provider == "archive_video" else queries
            for query in selected_queries:
                items = candidates(provider, query)
                chosen = next(
                    (a for a in items if a["id"] not in used and a["media_type"] == desired_type),
                    None,
                )
                if chosen:
                    matched_query = query
                    break
        if chosen:
            used.add(chosen["id"])
            shot["asset"] = chosen
            shot["selected_query"] = matched_query
            shot["fallback_used"] = matched_query != shot["query"]
        else:
            shot["asset"] = None
            shot["download_status"] = "missing"
    return shots


def _allowed_download_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (
            host == "cdn.pixabay.com"
            or host == "upload.wikimedia.org"
            or host == "archive.org"
            or host.endswith(".archive.org")
        )
    )


def download_asset(asset: dict, destination: Path,
                   max_bytes: int = MAX_FILE_BYTES) -> int:
    """Stream bounded files from known CDN domains, refusing redirects off-CDN."""
    url = asset["url"]
    if not _allowed_download_url(url):
        raise ValueError("Media URL is not from an approved HTTPS CDN.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    response = None
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT},
            timeout=(15, 60), stream=True,
        )
        response.raise_for_status()
        if not _allowed_download_url(response.url):
            raise ValueError("Media redirect left the approved CDN.")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
        if content_type and not content_type.startswith(
            "video/" if asset["media_type"] == "video" else "image/"
        ) and content_type != "application/octet-stream":
            raise ValueError(f"Unexpected media type: {content_type}")
        declared = int(response.headers.get("Content-Length") or 0)
        if declared > max_bytes:
            raise ValueError("Asset exceeds download size limit.")
        total = 0
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Asset exceeds download size limit.")
                handle.write(chunk)
        if total < 1024:
            raise ValueError("Asset download was unexpectedly small.")
        partial.replace(destination)
        return total
    finally:
        partial.unlink(missing_ok=True)
        if response is not None:
            response.close()


def create_preview_manifest(output_dir: str = "output", *,
                            seconds: float = 90, download: bool = False,
                            plan_only: bool = False) -> Path:
    """Plan/lookup six-ish shots; optionally download them for manual review."""
    output = Path(output_dir)
    script_file = output / "script.json"
    timing_file = output / "narration_timing.json"
    if not script_file.is_file() or not timing_file.is_file():
        raise FileNotFoundError("Expected output/script.json and output/narration_timing.json. "
                                "Complete Narration before running footage preview.")
    script = json.loads(script_file.read_text(encoding="utf-8"))
    timing = json.loads(timing_file.read_text(encoding="utf-8"))
    spans = load_chapter_timing(script, str(output),
                                float(timing["total_duration_seconds"]))
    shots = plan_preview(script, spans, seconds=seconds)
    if not plan_only:
        discover_assets(shots, pixabay_key=config.PIXABAY_API_KEY,
                        cache_dir=str(output / "footage" / ".pixabay-cache"))
    folder = output / "footage"
    folder.mkdir(parents=True, exist_ok=True)
    if download and not plan_only:
        for shot in shots:
            asset = shot["asset"]
            if not asset:
                continue
            path = folder / f"shot_{shot['shot']:02d}{asset['file_extension']}"
            try:
                size = download_asset(asset, path)
                shot["file"] = str(path.as_posix())
                shot["download_bytes"] = size
                shot["download_status"] = "downloaded_pending_review"
            except (requests.RequestException, OSError, ValueError) as exc:
                shot["download_status"] = "failed"
                shot.setdefault("warnings", []).append(str(exc))
    manifest = {
        "version": 2,
        "purpose": "90-second footage-sourcing preview, NOT a final edit",
        "preview_seconds": min(float(seconds), float(spans[-1]["end_seconds"])),
        "script_title": script.get("title", ""),
        "script_hash": timing.get("script_hash"),
        "status": "needs_human_review",
        "notice": (
            "All files remain pending rights, accuracy and visual review. "
            "Stock footage is illustrative; do not imply it records historical events. "
            "Pixabay results must follow its API conditions and Content License. "
            "Commons and Internet Archive licence labels need individual verification."
        ),
        "sources": ["Wikimedia Commons", "Internet Archive",
                    "Pixabay (only with optional API key)"],
        "pixabay_credit": "Stock footage search: https://pixabay.com/videos/",
        "shots": shots,
    }
    target = folder / "preview_manifest.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    return target
