"""Shared paths, config, transcript loading, and link helpers for the election-fallout report.

LLM calls and quote verification are reused from scripts/hospital_attacks (imported by
path, so module names here are prefixed to avoid clashing with its `common`/`analyze`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HA_DIR = PROJECT_ROOT / "scripts" / "hospital_attacks"
for p in (str(PROJECT_ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
if str(HA_DIR) not in sys.path:
    sys.path.append(str(HA_DIR))  # after HERE, so our own modules win

# hospital_attacks helpers (LLM wrapper, JSON extraction, transcript-quote matching).
from analyze import _extract_json as extract_json  # noqa: E402
from analyze import _locate_quote as locate_quote  # noqa: E402
from analyze import _quote_end as quote_end  # noqa: E402
from analyze import ask_claude  # noqa: E402
from common import Entry, Transcript, hhmmss_to_seconds, normalize, seconds_to_hhmmss  # noqa: E402

SOURCES_PATH = HERE / "sources.json"
OUT_DIR = PROJECT_ROOT / "reports" / "election_fallout"
ANALYSIS_DIR = OUT_DIR / "analysis"
CANDIDATES_PATH = OUT_DIR / "candidates.json"
TRIAGE_PATH = OUT_DIR / "triage.json"
INVENTORY_PATH = OUT_DIR / "inventory.json"
DATA_PATH = OUT_DIR / "data.json"
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"
MEDIA_DIR = PROJECT_ROOT / "videos" / "election_fallout"
COMPONENTS_DIR = PROJECT_ROOT / "components"

DEFAULT_MODEL = "opus"

_YT_ID = re.compile(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})")
_TS_LINE = re.compile(r"^\[(\d{1,2}:\d{2}:\d{2})\]\s?(.*)$")

# Health topics. Keys are stable (used in cached analyses); labels are for the report.
TOPICS: dict[str, str] = {
    "medicaid": "Medicaid & Healthy Michigan Plan",
    "federal_cuts": "Federal health cuts (H.R. 1)",
    "aca_coverage": "ACA subsidies & coverage",
    "costs": "Health care costs & affordability",
    "drug_prices": "Prescription drugs & PBMs",
    "medicare": "Medicare & seniors",
    "single_payer": "Medicare for All / universal coverage",
    "hospitals": "Hospitals & access to care",
    "hospital_pricing": "Hospital prices, consolidation & oversight",
    "workforce": "Health workforce & staffing",
    "behavioral": "Mental & behavioral health",
    "public_health": "Public health, vaccines & science",
    "reproductive": "Reproductive health & abortion",
    "insurers_corporate": "Insurers, corporate & private-equity influence",
    "medical_debt": "Medical debt",
    "rural": "Rural health",
    "other_health": "Other health",
}

KINDS = {
    "victory_speech": "Victory speech",
    "remarks": "Remarks",
    "press_conference": "Press conference",
    "interview": "Interview",
    "statement_video": "Video statement",
}


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_sources() -> dict:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def speakers_by_key() -> dict[str, dict]:
    return {s["key"]: s for s in load_sources()["speakers"]}


def youtube_id(url: str) -> str | None:
    if "youtube.com" not in (url or "") and "youtu.be" not in (url or ""):
        return None
    m = _YT_ID.search(url)
    return m.group(1) if m else None


def media_id(url: str) -> str:
    """Stable id: the YouTube id, else 'x' + a short hash of the page URL."""
    return youtube_id(url) or "x" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def link_at(url: str, seconds: int) -> str:
    """Deep link into the video. Only YouTube supports a start offset; other players
    get the page URL and the report prints the timestamp beside it."""
    yid = youtube_id(url)
    if yid:
        return f"https://www.youtube.com/watch?v={yid}&t={int(seconds)}s"
    return url


def short_ts(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pretty_date(iso: str | None) -> str:
    try:
        d = dt.date.fromisoformat(iso or "")
    except ValueError:
        return iso or ""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def load_transcript(path: Path, url: str, vid: str, title: str = "") -> Transcript | None:
    """Parse a transcripts/*.txt file (presser.save_transcript format) for any source."""
    if not path or not Path(path).exists():
        return None
    entries: list[Entry] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _TS_LINE.match(line)
        if m:
            entries.append(Entry(m.group(1), m.group(2).strip(), hhmmss_to_seconds(m.group(1))))
    return Transcript(
        path=Path(path), title=title, channel="", publish_date=None, url=url, video_id=vid,
        entries=entries,
    )


_ACRONYMS = {"ACA", "DTE", "AIPAC", "US", "USA", "ICE", "GOP", "PBM", "PBMS", "CEO", "CEOS", "ER", "DC", "AG",
              "UAW", "AP", "TV", "OK", "HHS", "CDC", "FDA", "NIH", "MHA", "II", "III", "MAGA"}
_PROPER = {
    w.lower(): w
    for w in (
        "Medicare Medicaid Michigan Michigander Michiganders America American Americans Detroit Lansing "
        "Trump Vance Musk Republicans Republican Democrats Democrat Benson Brinks Whitmer El-Sayed Peters "
        "Gary Dingell Washington Congress Senate God Rogers Abdul Jocelyn Debbie "
        "Winnie Gretchen Flint Hudson's January Washtenaw Sarah"
    ).split()
}


def tidy_caps(text: str) -> str:
    """Display-only cleanup for broadcast captions typed in ALL CAPS.

    Lowercases all-caps words (keeping acronyms and a list of proper nouns), then restores
    sentence-initial capitals and "I". Words are never added, removed, or reordered.
    """
    if not any(len(w) >= 3 and w.isupper() and w not in _ACRONYMS for w in re.findall(r"[A-Za-z']+", text)):
        return text  # normal caption casing: leave untouched
    words = re.split(r"(\s+)", text)
    out = []
    for w in words:
        core = re.sub(r"[^A-Za-z'-]", "", w)
        if core == "A" or (len(core) >= 2 and core.isupper() and core not in _ACRONYMS):
            low = w.lower()
            key = re.sub(r"[^a-z'-]", "", low)
            stem = key[:-2] if key.endswith("'s") else key
            if stem in _PROPER:
                low = low.replace(stem, _PROPER[stem], 1)
            out.append(low)
        else:
            out.append(w)
    s = "".join(out)
    s = re.sub(r"\bi\b", "I", s)
    s = re.sub(r"\bi'(m|ve|ll|d)\b", lambda m: "I'" + m.group(1), s)
    s = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


__all__ = [
    "ask_claude", "extract_json", "locate_quote", "quote_end", "Transcript", "normalize",
    "seconds_to_hhmmss", "hhmmss_to_seconds",
]
