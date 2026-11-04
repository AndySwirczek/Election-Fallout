"""Find post-election speeches/press events by the speakers in sources.json.

1. Search YouTube (relevance + newest-first) for every configured query; add seed URLs.
2. Fetch metadata for new results (cached in candidates.json) and keep uploads on or
   after `start_date`.
3. Ask Claude to triage new candidates: is this the speaker on camera after the
   election? Which event is it? Full speech or a clip? (cached in triage.json)
4. Group kept candidates into events and pick one canonical recording per event
   (inventory.json); the other uploads are kept as alternates.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from ef_common import (
    CANDIDATES_PATH,
    DEFAULT_MODEL,
    INVENTORY_PATH,
    KINDS,
    TRIAGE_PATH,
    ask_claude,
    extract_json,
    load_sources,
    log,
    media_id,
    read_json,
    write_json,
    youtube_id,
)

_YDL_QUIET = {"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True}


# ---------------------------------------------------------------------------
# Search + metadata
# ---------------------------------------------------------------------------


def _search(query: str, n: int, newest: bool) -> list[dict]:
    if newest:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query) + "&sp=CAI%253D"
    else:
        url = f"ytsearch{n}:{query}"
    opts = {**_YDL_QUIET, "extract_flat": True, "playlistend": n}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        log(f"  search failed ({query}): {str(e)[:120]}")
        return []
    out = []
    for e in (info or {}).get("entries") or []:
        if e and e.get("id") and len(e["id"]) == 11:
            out.append(
                {
                    "id": e["id"],
                    "url": f"https://www.youtube.com/watch?v={e['id']}",
                    "title": e.get("title") or "",
                    "channel": e.get("channel") or e.get("uploader") or "",
                    "duration": e.get("duration"),
                }
            )
    return out[:n]


def _meta(url: str) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(_YDL_QUIET) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}
    if info.get("_type") == "playlist" and info.get("entries"):
        info = next((e for e in info["entries"] if e), info)
    upload = info.get("upload_date") or ""
    date = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if len(upload) == 8 else None
    if not date:
        ts = info.get("timestamp") or info.get("release_timestamp")
        if ts:
            date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()
    if not date:
        m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", url)
        if m:
            date = "-".join(m.groups())
    return {
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or info.get("extractor_key") or "",
        "upload_date": date,
        "duration": info.get("duration"),
        "description": (info.get("description") or "")[:700],
        "is_live": bool(info.get("is_live")),
        "extractor": info.get("extractor_key") or info.get("extractor"),
    }


def gather_candidates(refresh: bool = True) -> dict[str, dict]:
    src = load_sources()
    cands: dict[str, dict] = read_json(CANDIDATES_PATH, default={}) or {}
    n = int(src.get("search_results_per_query", 12))
    max_dur = int(src.get("max_duration_minutes", 75)) * 60

    found: dict[str, dict] = {}
    if refresh:
        queries = [(q, s["key"]) for s in src["speakers"] for q in s.get("queries", [])]
        queries += [(q, None) for q in src.get("general_queries", [])]
        log(f"searching YouTube: {len(queries)} queries x 2 orderings")

        def run(qs):
            q, key = qs
            hits = _search(q, n, newest=False) + _search(q, n, newest=True)
            return q, key, hits

        with ThreadPoolExecutor(max_workers=4) as pool:
            for q, key, hits in pool.map(run, queries):
                for h in hits:
                    row = found.setdefault(h["id"], {**h, "queries": [], "hint_speakers": []})
                    if q not in row["queries"]:
                        row["queries"].append(q)
                    if key and key not in row["hint_speakers"]:
                        row["hint_speakers"].append(key)
        # Caucus/member channels: their titles often omit the speaker's name, so take the
        # newest few uploads directly (bypassing the name prefilter below).
        recent = int(src.get("watch_channel_recent", 6))
        for ch in src.get("watch_channels", []):
            for tab in ("videos", "streams"):
                try:
                    with yt_dlp.YoutubeDL({**_YDL_QUIET, "extract_flat": True, "playlistend": recent}) as ydl:
                        info = ydl.extract_info(f"{ch['url']}/{tab}", download=False)
                except Exception:  # noqa: BLE001  (e.g. channel has no streams tab)
                    continue
                for e in ((info or {}).get("entries") or [])[:recent]:
                    if not e or len(e.get("id") or "") != 11:
                        continue
                    row = found.setdefault(e["id"], {
                        "id": e["id"], "url": f"https://www.youtube.com/watch?v={e['id']}",
                        "title": e.get("title") or "", "channel": ch.get("name", ""),
                        "duration": e.get("duration"), "queries": [], "hint_speakers": [],
                    })
                    row["watched"] = True
                    if ch.get("speaker") and ch["speaker"] not in row["hint_speakers"]:
                        row["hint_speakers"].append(ch["speaker"])
    for seed in src.get("seed_urls", []):
        vid = media_id(seed["url"])
        row = found.setdefault(vid, {"id": vid, "url": seed["url"], "queries": [], "hint_speakers": []})
        row["seed"] = True
        if seed.get("speaker") and seed["speaker"] not in row["hint_speakers"]:
            row["hint_speakers"].append(seed["speaker"])

    # Merge into cache; fetch metadata only for new ids that could plausibly qualify.
    # Every metadata call is a YouTube page load, and a few hundred in a row trips the
    # "confirm you're not a bot" block, so require a tracked name in the title first.
    names = {a.lower() for s in src["speakers"] for a in [s["name"], *s.get("aliases", [])] if len(a) > 3}
    names |= {s["name"].split()[-1].lower() for s in src["speakers"]}
    named = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)), re.I)
    todo = []
    for vid, row in found.items():
        prev = cands.get(vid)
        if prev:
            prev["queries"] = sorted(set(prev.get("queries", [])) | set(row["queries"]))
            prev["hint_speakers"] = sorted(set(prev.get("hint_speakers", [])) | set(row["hint_speakers"]))
            if prev.get("is_live") or (prev.get("error") and not prev.get("skip")):
                prev.pop("error", None)
                todo.append(vid)  # re-check live streams and transient lookup failures
            continue
        cands[vid] = row
        dur = row.get("duration")
        if dur is not None and (dur < 40 or dur > max_dur) and not row.get("seed"):
            row["skip"] = "duration"
            continue
        if not row.get("seed") and not row.get("watched") and not named.search(row.get("title") or ""):
            row["skip"] = "no tracked name in title"
            continue
        todo.append(vid)

    log(f"{len(found)} search hits, {len(todo)} need metadata")

    def fetch(vid):
        return vid, _meta(cands[vid]["url"])

    with ThreadPoolExecutor(max_workers=3) as pool:
        for vid, meta in pool.map(fetch, todo):
            cands[vid].update(meta or {})
    write_json(CANDIDATES_PATH, cands)
    return cands


def eligible(cands: dict[str, dict]) -> dict[str, dict]:
    src = load_sources()
    start = src["start_date"]
    max_dur = int(src.get("max_duration_minutes", 75)) * 60
    out = {}
    for vid, c in cands.items():
        if c.get("skip") or c.get("error") or not c.get("upload_date"):
            continue
        if c["upload_date"] < start:
            continue
        if (c.get("duration") or 0) > max_dur and not c.get("seed"):
            continue
        out[vid] = c
    return out


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------

TRIAGE_PROMPT = """\
You are helping the Michigan Health & Hospital Association build a library of what \
Michigan's newly elected Democratic leaders said on camera after the {election}. \
Today is {today}.

People we track (key: name, office):
{speakers}

Events already identified (reuse these exact event_key values when a video is another \
upload of the same event):
{events}

Candidate videos (id | upload date | channel | duration | title | description excerpt):
{candidates}

For EACH candidate decide whether to keep it. KEEP only when one or more tracked people \
are themselves on camera speaking at length (a speech, remarks, press conference, or a \
one-on-one interview) on or after election night, Nov. 3, 2026. REJECT:
- news packages, anchor recaps, panel analysis, or live results coverage where tracked \
people appear only in short soundbites;
- reaction/commentary channels (e.g. "TYT reacts") and multi-speaker highlight compilations \
from different states;
- anything recorded before the polls closed at 8 p.m. ET on Nov. 3, 2026: primary-night \
speeches, campaign rallies, debates, and Election Day interviews or get-out-the-vote \
appearances (predictions, turnout pitches, campaign disputes). Election-night remarks once \
results were coming in, and anything after, are in scope;
- people not in the list, Republicans, and races outside Michigan.

For kept videos:
- "speakers": list of tracked keys who speak at length (in speaking order).
- "event_key": short kebab-case id for the real-world event, e.g. \
"benson-victory-speech-2026-11-04" or "el-sayed-victory-speech-2026-11-04". Different uploads \
of the same speech (different channels, "FULL", "LIVE", trimmed versions) MUST share one key. \
A clip that is an excerpt of a speech shares the speech's key.
- "event_label": a clean human title, e.g. "Jocelyn Benson victory speech, Hudson's Detroit".
- "event_date": the date the event happened (YYYY-MM-DD). Election-night speeches after \
midnight are 2026-11-04.
- "kind": one of {kinds}.
- "completeness": "full" (the whole speech/event), "partial" (a long portion), or "clip" \
(under ~3 minutes of an event).

Respond with STRICT JSON ONLY, no prose, no markdown fences:
{{"decisions": [{{"id": "...", "keep": true, "speakers": ["benson"], "event_key": "...", \
"event_label": "...", "event_date": "2026-11-04", "kind": "victory_speech", \
"completeness": "full", "reason": "short reason"}}, {{"id": "...", "keep": false, \
"reason": "short reason"}}]}}
Include every candidate id exactly once.\
"""


def _fmt_dur(sec) -> str:
    if not sec:
        return "?"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def triage(cands: dict[str, dict], model: str, batch: int = 30, force: bool = False) -> dict[str, dict]:
    src = load_sources()
    decisions: dict[str, dict] = read_json(TRIAGE_PATH, default={}) or {}
    todo = [c for vid, c in sorted(cands.items()) if force or vid not in decisions]
    log(f"{len(cands)} eligible candidates, {len(todo)} need triage")
    speakers = "\n".join(f"- {s['key']}: {s['name']}, {s['office']}. {s.get('detail', '')}" for s in src["speakers"])
    for i in range(0, len(todo), batch):
        chunk = todo[i : i + batch]
        events = sorted(
            {(d["event_key"], d.get("event_label", "")) for d in decisions.values() if d.get("keep")}
        )
        ev_txt = "\n".join(f"- {k}: {lbl}" for k, lbl in events) or "(none yet)"
        lines = []
        for c in chunk:
            desc = re.sub(r"\s+", " ", c.get("description") or "")[:300]
            lines.append(
                f"{c['id']} | {c.get('upload_date')} | {c.get('channel')} | {_fmt_dur(c.get('duration'))} | "
                f"{c.get('title')} | {desc}"
            )
        prompt = TRIAGE_PROMPT.format(
            election=src["election_label"],
            today=dt.date.today().isoformat(),
            speakers=speakers,
            events=ev_txt,
            candidates="\n".join(lines),
            kinds=", ".join(KINDS),
        )
        log(f"  triage batch {i // batch + 1}: {len(chunk)} videos")
        text, cost = ask_claude(prompt, model)
        parsed = extract_json(text) or {}
        got = {d.get("id"): d for d in parsed.get("decisions", []) if isinstance(d, dict)}
        for c in chunk:
            d = got.get(c["id"])
            if not d:
                log(f"    no decision for {c['id']}; will retry next run")
                continue
            if d.get("keep"):
                if d.get("kind") not in KINDS:
                    d["kind"] = "remarks"
                if d.get("completeness") not in {"full", "partial", "clip"}:
                    d["completeness"] = "partial"
                d["speakers"] = [k for k in d.get("speakers") or [] if k in {s["key"] for s in src["speakers"]}]
                if not d["speakers"] or not d.get("event_key"):
                    d["keep"] = False
                    d["reason"] = (d.get("reason") or "") + " [no tracked speaker/event]"
            decisions[c["id"]] = d
            mark = "+" if d.get("keep") else "-"
            log(f"    {mark} {c.get('title', '')[:80]}  ({d.get('event_key') or d.get('reason', '')[:60]})")
        write_json(TRIAGE_PATH, decisions)
        log(f"    cost={cost}")
    return decisions


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def _rank(c: dict, d: dict, preferred: set[str]) -> tuple:
    comp = {"full": 2, "partial": 1, "clip": 0}[d.get("completeness", "partial")]
    return (
        comp,
        (c.get("channel") or "") in preferred,
        bool(youtube_id(c["url"])),  # YouTube supports timestamp links + captions
        c.get("duration") or 0,
    )


def build_inventory(cands: dict[str, dict], decisions: dict[str, dict]) -> dict:
    src = load_sources()
    preferred = set(src.get("preferred_channels", []))
    prev = read_json(INVENTORY_PATH, default={}) or {}
    prev_events = {e["event_key"]: e for e in prev.get("events", [])}
    excluded = src.get("exclude_ids", {})
    overrides = src.get("event_overrides", {})  # manual fixes to triage grouping
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for vid, d in decisions.items():
        if not d.get("keep") or vid not in cands or vid in excluded:
            continue
        if vid in overrides:
            d = {**d, **{k: v for k, v in overrides[vid].items() if k in ("event_key", "completeness")}}
        groups.setdefault(d["event_key"], []).append((cands[vid], d))

    events = []
    for key, members in groups.items():
        members.sort(key=lambda cd: _rank(cd[0], cd[1], preferred), reverse=True)
        c, d = members[0]
        old = prev_events.get(key, {})
        # Keep an already-transcribed canonical unless a strictly better one appeared.
        if old.get("canonical_id") and old.get("transcript_path"):
            for oc, od in members:
                if oc["id"] == old["canonical_id"] and _rank(oc, od, preferred)[:2] >= _rank(c, d, preferred)[:2]:
                    c, d = oc, od
                    break
        speakers: list[str] = []
        for _, md in members:
            for k in md["speakers"]:
                if k not in speakers:
                    speakers.append(k)
        ev = {
            "event_key": key,
            "label": d.get("event_label") or c.get("title"),
            "event_date": d.get("event_date") or c.get("upload_date"),
            "kind": d.get("kind"),
            "speakers": d["speakers"] if set(d["speakers"]) >= set(speakers) else speakers,
            "canonical_id": c["id"],
            "url": c["url"],
            "title": c.get("title"),
            "channel": c.get("channel"),
            "duration": c.get("duration"),
            "upload_date": c.get("upload_date"),
            "completeness": d.get("completeness"),
            "is_live": c.get("is_live", False),
            "alternates": [
                {"id": oc["id"], "url": oc["url"], "channel": oc.get("channel"), "title": oc.get("title"),
                 "duration": oc.get("duration"), "completeness": od.get("completeness")}
                for oc, od in members[1:]
            ],
        }
        if old.get("canonical_id") == ev["canonical_id"]:
            for k in ("transcript_path", "transcript_source", "segments", "status"):
                if k in old:
                    ev[k] = old[k]
        events.append(ev)
    events.sort(key=lambda e: (e["event_date"] or "", e["label"]))
    inv = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "events": events}
    write_json(INVENTORY_PATH, inv)
    log(f"inventory: {len(events)} events")
    for e in events:
        log(f"  {e['event_date']}  {e['label']}  [{e['channel']}, {_fmt_dur(e['duration'])}, "
            f"{e['completeness']}, +{len(e['alternates'])} alt]")
    return inv


def run(model: str = DEFAULT_MODEL, refresh: bool = True, retriage: bool = False) -> dict:
    cands = gather_candidates(refresh=refresh)
    pool = eligible(cands)
    decisions = triage(pool, model, force=retriage)
    return build_inventory(cands, decisions)
