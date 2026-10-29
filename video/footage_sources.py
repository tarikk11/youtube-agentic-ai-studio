"""No-subscription documentary footage providers.

Internet Archive is keyless. Pixabay Videos is an optional *free API key* provider.
Do not treat any provider's metadata as proof that historical footage is genuine
or legally cleared. Retain original author, page, and licence for manual review.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

PIXABAY_API = "https://pixabay.com/api/videos/"
ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_META = "https://archive.org/metadata/"
USER_AGENT = "MysteriesDocumentaryStudio/0.1 (https://github.com/tarikk11/youtube-agentic-ai-studio)"
CACHE_SECONDS = 24 * 60 * 60
MAX_DOWNLOAD_SIZE = 80 * 1024 * 1024


def _json_get(url: str, params: dict | None = None) -> dict:
    response = requests.get(url, params=params, timeout=20,
                            headers={"User-Agent": USER_AGENT})
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        # Never echo URLs or query parameters: Pixabay's key is in the URL.
        raise ValueError(f"Media API returned HTTP {response.status_code}") from exc
    return response.json()


def _pixabay_cached_search(query: str, key: str, cache_dir: Path) -> dict:
    """Pixabay requires caching responses for at least 24 hours."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(query.lower().strip().encode("utf-8")).hexdigest()[:20]
    cache_path = cache_dir / (token + ".json")
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(cached["saved_at"]) < CACHE_SECONDS:
                return cached["response"]
        except (ValueError, KeyError, OSError, TypeError):
            pass
    data = _json_get(PIXABAY_API, params={
        "key": key,
        "q": query[:100],
        "video_type": "film",
        "per_page": 20,
        "safesearch": "true",
    })
    cache_path.write_text(json.dumps(
        {"saved_at": time.time(), "response": data}, ensure_ascii=False
    ), encoding="utf-8")
    return data


def search_pixabay(query: str, api_key: str, limit: int = 4,
                   cache_dir: str = "output/footage/.pixabay-cache") -> list[dict]:
    """Optional cinematic B-roll; uses existing PIXABAY_API_KEY from YAAS."""
    if not api_key or api_key.upper().startswith("YOUR_"):
        return []
    data = _pixabay_cached_search(query, api_key, Path(cache_dir))
    out = []
    for video in data.get("hits", []):
        renditions = (video.get("videos") or {})
        variants = []
        for size in ("medium", "large", "small"):
            v = renditions.get(size) or {}
            url = v.get("url", "")
            w, h = int(v.get("width") or 0), int(v.get("height") or 0)
            nbytes = int(v.get("size") or 0)
            if (url.startswith("https://cdn.pixabay.com/")
                    and w >= 640 and h >= 360 and 0 < nbytes <= MAX_DOWNLOAD_SIZE):
                variants.append((abs(h - 1080), abs(w - 1920), v))
        if not variants:
            continue
        variants.sort(key=lambda row: (row[0], row[1]))
        v = variants[0][2]
        out.append({
            "id": f"pixabay:{video['id']}",
            "source": "Pixabay",
            "media_type": "video",
            "title": video.get("tags", "") or f"Pixabay video {video['id']}",
            "url": v["url"],
            "page_url": video.get("pageURL", ""),
            "creator": video.get("user", ""),
            "license": "Pixabay Content License",
            "license_url": "https://pixabay.com/service/license-summary/",
            "mime_type": "video/mp4",
            "width": v.get("width"), "height": v.get("height"),
            "duration_seconds": video.get("duration"),
            "file_extension": ".mp4",
            "rights_review": "pending",
            "historical_authenticity": "illustrative_only",
        })
        if len(out) >= limit:
            break
    return out


def _archive_licence(license_url: str) -> str | None:
    """Allow only recognizable commercial reuse licences from item metadata."""
    if not isinstance(license_url, str):
        return None
    url = urlparse(license_url.strip())
    if url.scheme not in ("https", "http") or url.hostname not in (
            "creativecommons.org", "www.creativecommons.org"):
        return None
    path = url.path.lower().rstrip("/") + "/"
    if path.startswith("/publicdomain/zero/"):
        return "CC0"
    if path.startswith("/publicdomain/mark/"):
        return "Public Domain Mark"
    m = re.fullmatch(r"/licenses/(by|by-sa)/(\d\.\d)/", path)
    if m:
        return f"CC {m.group(1).upper()} {m.group(2)}"
    return None


def search_internet_archive(query: str, limit: int = 3) -> list[dict]:
    """Search publicly accessible archive films with explicit eligible licence URL.

    Item-level Creative Commons metadata is a *lead*, not independent verification
    of rights for every underlying recording. Flag every result for human review.
    """
    words = re.findall(r"[A-Za-z0-9]+", query.lower())[:3]
    if not words:
        return []
    # Restrict searches to movie items. Broad searches are deliberately shallow.
    q = "mediatype:movies AND (" + " AND ".join(words) + ")"
    data = _json_get(ARCHIVE_SEARCH, params={
        "q": q, "fl[]": ["identifier", "title"], "rows": max(4, min(limit * 3, 9)),
        "page": 1, "output": "json",
    })
    out = []
    for hit in data.get("response", {}).get("docs", []):
        identifier = hit.get("identifier")
        if not isinstance(identifier, str) or not re.fullmatch(r"[\w.-]{1,100}", identifier):
            continue
        try:
            metadata = _json_get(ARCHIVE_META + quote(identifier, safe=""))
        except (requests.RequestException, ValueError):
            continue
        item = metadata.get("metadata") or {}
        licence_url = item.get("licenseurl", "")
        if isinstance(licence_url, list):
            licence_url = next((x for x in licence_url if _archive_licence(x)), "")
        licence = _archive_licence(licence_url)
        if not licence:
            continue
        candidates = []
        for f in metadata.get("files", []):
            name = f.get("name", "")
            if not isinstance(name, str) or "/" in name or "\\" in name:
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in (".mp4", ".webm", ".ogv"):
                continue
            try:
                nbytes = int(f.get("size", 0))
            except (ValueError, TypeError):
                continue
            if not 1024 <= nbytes <= MAX_DOWNLOAD_SIZE:
                continue
            # Prefer original MP4; downloaded files are still subject to review.
            candidates.append((0 if f.get("source") == "original" else 1,
                               0 if suffix == ".mp4" else 1, name, suffix))
        if not candidates:
            continue
        candidates.sort()
        _, _, filename, extension = candidates[0]
        creator = item.get("creator") or ""
        if isinstance(creator, list):
            creator = ", ".join(str(x) for x in creator)
        title = item.get("title") or hit.get("title") or identifier
        if isinstance(title, list):
            title = ", ".join(str(x) for x in title)
        out.append({
            "id": f"archive:{identifier}",
            "source": "Internet Archive",
            "media_type": "video",
            "title": str(title)[:250],
            "url": (f"https://archive.org/download/{quote(identifier, safe='')}/"
                    f"{quote(filename, safe='')}"),
            "page_url": f"https://archive.org/details/{quote(identifier, safe='')}",
            "creator": str(creator)[:250],
            "license": licence,
            "license_url": licence_url,
            "mime_type": {".mp4": "video/mp4", ".webm": "video/webm",
                          ".ogv": "video/ogg"}[extension],
            "width": None, "height": None,
            "duration_seconds": None,
            "file_extension": extension,
            "rights_review": "pending",
            "historical_authenticity": "unverified",
        })
        if len(out) >= limit:
            break
    return out
