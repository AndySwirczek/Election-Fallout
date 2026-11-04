"""Shared paths, transcript parsing, and link helpers for the hospital attacks pipeline."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"
OUT_DIR = PROJECT_ROOT / "reports" / "hospital_attacks"
ANALYSIS_DIR = OUT_DIR / "analysis"
COMPONENTS_DIR = PROJECT_ROOT / "components"
INVENTORY_PATH = OUT_DIR / "inventory.json"
DATA_PATH = OUT_DIR / "data.json"

CHANNEL_HANDLE = "@mihouserepublicans"
CHANNEL_NAME = "Michigan House Republicans Official"
SESSION_START = dt.date(2025, 1, 1)
SESSION_LABEL = "2025-2026"

# A Hall presser: title mentions the Speaker (or is a presser on his channel) and is not
# one of the other caucus events that share the naming space.
HALL_TITLE = re.compile(
    r"speaker hall|speaker'?s? (?:press|presser)|\bhall\b.*(?:press|presser|briefing)", re.I
)
NOT_HALL_TITLE = re.compile(r"senate dem|aragona|johnsen|leader|minority", re.I)

_TS_LINE = re.compile(r"^\[(\d{1,2}:\d{2}:\d{2})\]\s?(.*)$")
_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})")

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}
_TITLE_DATE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)


@dataclass
class Entry:
    timestamp: str
    text: str
    seconds: int


@dataclass
class Transcript:
    path: Path
    title: str
    channel: str
    publish_date: str | None
    url: str
    video_id: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def event_date(self) -> str:
        return event_date_from_title(self.title, self.publish_date)

    def as_text(self) -> str:
        return "\n".join(f"[{e.timestamp}] {e.text}" for e in self.entries)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def hhmmss_to_seconds(ts: str) -> int:
    try:
        parts = [int(p) for p in ts.strip().split(":")]
    except (ValueError, AttributeError):
        return 0
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def seconds_to_hhmmss(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def video_id_from_url(url: str) -> str | None:
    m = _VIDEO_ID.search(url or "")
    return m.group(1) if m else None


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def ts_link(video_id: str, seconds: int) -> str:
    return f"{watch_url(video_id)}&t={int(seconds)}s"


def event_date_from_title(title: str, fallback: str | None) -> str:
    """Pull 'March 17, 2026' / 'Aug. 26, 2026' / 'Sept. 3, 2025' out of a title.

    Falls back to the YouTube publish date (which is often the day after the event).
    """
    m = _TITLE_DATE.search(title or "")
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            try:
                return dt.date(int(m.group(3)), month, int(m.group(2))).isoformat()
            except ValueError:
                pass
    return fallback or "unknown"


def pretty_date(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def is_hall_presser(title: str, channel: str | None = None) -> bool:
    if channel and channel.strip().lower() != CHANNEL_NAME.lower():
        return False
    if NOT_HALL_TITLE.search(title or ""):
        return False
    return bool(HALL_TITLE.search(title or ""))


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------


def parse_transcript(path: Path) -> Transcript | None:
    header: dict[str, str] = {}
    entries: list[Entry] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _TS_LINE.match(line)
        if m:
            entries.append(Entry(m.group(1), m.group(2).strip(), hhmmss_to_seconds(m.group(1))))
            continue
        if ":" in line and not entries:
            key, _, val = line.partition(":")
            key = key.strip().lower()
            if key in {"title", "channel", "date", "url"}:
                header[key] = val.strip()
    url = header.get("url", "")
    vid = video_id_from_url(url)
    if not vid:
        return None
    date = header.get("date")
    if date in (None, "", "Unknown", "unknown"):
        date = None
    return Transcript(
        path=path,
        title=header.get("title", path.stem),
        channel=header.get("channel", ""),
        publish_date=date,
        url=watch_url(vid),
        video_id=vid,
        entries=entries,
    )


def load_hall_transcripts() -> dict[str, Transcript]:
    """All Hall presser transcripts on disk, deduped by video id (longest wins)."""
    found: dict[str, Transcript] = {}
    for path in sorted(TRANSCRIPTS_DIR.glob("*.txt")):
        t = parse_transcript(path)
        if not t or not is_hall_presser(t.title, t.channel):
            continue
        prev = found.get(t.video_id)
        if prev is None or len(t.entries) > len(prev.entries):
            found[t.video_id] = t
    return found


_TITLE_NOISE = re.compile(r"^(?:(?:livestream|live now|live|copy of|replay)\s*[:\-]?\s*)+", re.I)


def dedupe_key(title: str) -> str:
    """Normalize a video title so re-uploads of the same presser collide."""
    t = _TITLE_NOISE.sub("", (title or "").strip())
    t = re.sub(r"\bmatt\s+", "", t, flags=re.I)  # "Speaker Matt Hall" == "Speaker Hall"
    t = re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    return t


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9$%\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
