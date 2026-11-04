import json
import re
from typing import Generator, Iterator

import requests
import scrapetube
import yt_dlp


VIDEO_ID_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/|youtube\.com/live/)([A-Za-z0-9_-]{11})"),
]

CHANNEL_URL_PATTERNS = [
    re.compile(r"youtube\.com/@[\w.-]+"),
    re.compile(r"youtube\.com/channel/[\w-]+"),
    re.compile(r"youtube\.com/c/[\w.-]+"),
]


def sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip("_.")
    return name[:200] if name else "untitled"
    

def get_video_metadata(video_id: str) -> dict | None:
    """Return {"title", "date", "url"} or None on failure."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None

    upload_date = info.get("upload_date")  # YYYYMMDD
    date_str = None
    if upload_date and len(upload_date) == 8:
        date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

    channel = info.get("channel") or info.get("uploader") or "unknown_channel"

    return {
        "url": url,
        "title": info.get("title", "Untitled"),
        "date": date_str,
        "channel": channel,
    }

def _channel_base_url(channel_ref: str) -> str:
    if channel_ref.startswith("@"):
        return f"https://www.youtube.com/{channel_ref}"
    if "youtube.com" in channel_ref:
        return channel_ref.rstrip("/")
    return f"https://www.youtube.com/{channel_ref}"


def _search_dict(obj, key: str) -> Iterator:
    stack = [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == key:
                    yield v
                else:
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


def _extract_lockup(lvm: dict) -> dict:
    """Pull video_id, title, url, published, length from a lockupViewModel."""
    video_id = lvm.get("contentId")
    md = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
    title = md.get("title", {}).get("content")

    parts: list[str] = []
    rows = md.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
    for row in rows:
        for part in row.get("metadataParts", []):
            txt = part.get("text", {}).get("content")
            if txt:
                parts.append(txt)
    # "Streamed N ago" / "N views" / "Scheduled for ..." live in `parts`.
    published = next((p for p in parts if "ago" in p.lower()), None)

    length = None
    is_live = False
    overlays = lvm.get("contentImage", {}).get("thumbnailViewModel", {}).get("overlays", [])
    for ov in overlays:
        bottom = ov.get("thumbnailBottomOverlayViewModel", {})
        for badge in bottom.get("badges", []):
            text = badge.get("thumbnailBadgeViewModel", {}).get("text")
            if not text:
                continue
            if re.fullmatch(r"\d+(:\d+)+", text):
                length = text
            elif text.upper() in ("LIVE", "UPCOMING"):
                is_live = True

    return {
        "video_id": video_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "published": published,
        "length": length,
        "is_live": is_live,
    }


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def list_channel_videos(
    channel_ref: str,
    content_type: str = "streams",
    limit: int = 50,
) -> Generator[dict, None, None]:
    """Yield videos from a channel as dicts: video_id, title, url, published, length, is_live.

    Replaces scrapetube.get_channel — YouTube moved from videoRenderer to lockupViewModel
    and scrapetube 2.6.0 silently returns nothing. Returns the first page only (~30 items),
    which is enough for current callers.
    """
    base = _channel_base_url(channel_ref)
    url = f"{base}/{content_type}?view=0&flow=grid"

    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT
    session.headers["Accept-Language"] = "en"
    session.cookies.set("CONSENT", "YES+cb", domain=".youtube.com")
    resp = session.get(url, params={"ucbcb": 1}, timeout=15)
    html = resp.text

    marker = "var ytInitialData = "
    start = html.find(marker)
    if start == -1:
        return
    start += len(marker)
    end = html.find("};", start)
    if end == -1:
        return
    try:
        data = json.loads(html[start:end + 1])
    except json.JSONDecodeError:
        return

    count = 0
    for lvm in _search_dict(data, "lockupViewModel"):
        info = _extract_lockup(lvm)
        if not info["video_id"]:
            continue
        yield info
        count += 1
        if count >= limit:
            return


def list_channel_streams(channel_ref: str):
    """Yield video IDs for live-broadcast streams on a channel."""
    for info in list_channel_videos(channel_ref, content_type="streams"):
        yield info["video_id"]


def list_all_channel_videos(
    channel_ref: str,
    content_type: str = "streams",
    limit: int | None = None,
) -> Generator[dict, None, None]:
    """Yield ALL videos from a channel tab, paginating the full list via yt-dlp.

    Unlike list_channel_videos (which scrapes only the first ~30 lockups from
    ytInitialData), this pages through the entire "streams" (or "videos") tab so
    callers can cover a long time window. Uses yt-dlp flat extraction, so it does
    NOT fetch per-video metadata (no upload date) — callers needing the exact date
    should call get_video_metadata() on the entries they keep.

    Yields dicts: {video_id, title, url}. `limit` caps the number yielded.
    """
    base = _channel_base_url(channel_ref)
    url = f"{base}/{content_type}"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    if limit:
        opts["playlistend"] = limit

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return

    entries = info.get("entries") or []
    count = 0
    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id")
        if not video_id:
            continue
        yield {
            "video_id": video_id,
            "title": entry.get("title"),
            "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
        }
        count += 1
        if limit and count >= limit:
            return