"""Transcribe the canonical recording of each event in inventory.json.

YouTube: captions first, then Whisper (transcriber.fetch_transcript).
Other sites (TV-station players): download audio with yt-dlp, then Whisper.
Transcripts land in transcripts/election_<date>_<event_key>.txt.
"""

from __future__ import annotations

import time

import yt_dlp

from ef_common import (
    INVENTORY_PATH,
    MEDIA_DIR,
    PROJECT_ROOT,
    TRANSCRIPTS_DIR,
    load_transcript,
    log,
    read_json,
    write_json,
    youtube_id,
)
from transcriber.transcriber import fetch_transcript, fetch_transcript_file, resolve_gpu_flag  # noqa: E402

MIN_COVERAGE = 0.7  # a transcript covering less of the video than this was probably cut short


def transcript_path(ev: dict):
    return TRANSCRIPTS_DIR / f"election_{ev['event_date']}_{ev['event_key']}.txt"


def save(entries: list[dict], ev: dict, source: str):
    path = transcript_path(ev)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Title: {ev['title']}",
        f"Channel: {ev.get('channel') or 'Unknown'}",
        f"Date: {ev.get('upload_date') or ev['event_date']}",
        f"URL: {ev['url']}",
        f"Event: {ev['label']}",
        f"Source: {source}",
        "",
        "Transcript:",
        "",
    ]
    lines += [f"[{e['timestamp']}] {e['text']}" for e in entries]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _download_media(url: str, vid: str) -> str:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(MEDIA_DIR.glob(f"{vid}.*"))
    if existing:
        return str(existing[0])
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio/best",
        "outtmpl": str(MEDIA_DIR / f"{vid}.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def youtube_blocked(url: str) -> bool:
    """True when YouTube is serving the 'Sign in to confirm you're not a bot' wall.

    In that state captions, subtitles and audio downloads all fail, and every extra
    request prolongs the block, so the caller should stop rather than retry.
    """
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        return "confirm you" in str(e) and "bot" in str(e)
    return False


def run(only: str | None = None, gpu: bool | None = None, pause: float = 30.0) -> dict:
    inv = read_json(INVENTORY_PATH)
    if not inv:
        raise SystemExit("inventory.json missing; run discover first")
    backend = resolve_gpu_flag(gpu)
    blocked = False
    fetched = 0
    for ev in inv["events"]:
        if only and only not in ev["event_key"]:
            continue
        if blocked and youtube_id(ev["url"]):
            ev["status"] = "blocked"
            continue
        t = load_transcript(PROJECT_ROOT / ev["transcript_path"], ev["url"], ev["canonical_id"]) if ev.get("transcript_path") else None
        covered = t.entries[-1].seconds if t and t.entries else 0
        dur = ev.get("duration") or 0
        if t and t.entries and (not dur or covered >= MIN_COVERAGE * dur):
            ev["status"] = "cached"
            continue
        if ev.get("is_live"):
            ev["status"] = "live"
            log(f"  still live, skipping {ev['label']}")
            continue
        if fetched and youtube_id(ev["url"]):
            time.sleep(pause)  # be gentle: bursts of caption/audio requests trip YouTube's bot wall
        fetched += 1
        log(f"transcribing {ev['event_date']}  {ev['label']}  ({ev['url']})")
        start = time.time()
        try:
            yid = youtube_id(ev["url"])
            if yid:
                entries, source = fetch_transcript(yid, backend=backend)
            else:
                media = _download_media(ev["url"], ev["canonical_id"])
                entries, source = fetch_transcript_file(media, backend=backend)
            path = save(entries, ev, source)
            ev.update(
                status="transcribed",
                transcript_path=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                transcript_source=source,
                segments=len(entries),
            )
            log(f"  ok via {source}: {len(entries)} segments in {time.time() - start:.0f}s")
        except Exception as e:  # noqa: BLE001
            ev["status"] = "failed"
            ev["error"] = str(e)[:300]
            log(f"  FAILED: {e}")
            if youtube_id(ev["url"]) and youtube_blocked(ev["url"]):
                ev["status"] = "blocked"
                blocked = True
                log("  YouTube bot-check wall is up; skipping remaining YouTube videos. Retry later "
                    "or from another network.")
        write_json(INVENTORY_PATH, inv)
    write_json(INVENTORY_PATH, inv)
    counts: dict[str, int] = {}
    for ev in inv["events"]:
        counts[ev.get("status", "?")] = counts.get(ev.get("status", "?"), 0) + 1
    log(f"transcripts: {counts}")
    return inv
