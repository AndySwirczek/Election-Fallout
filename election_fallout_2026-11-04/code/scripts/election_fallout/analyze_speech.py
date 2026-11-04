"""Per-event analysis: healthcare statements and stated priorities, verified to transcript.

One cached JSON per event in reports/election_fallout/analysis/<event_key>.json.
"""

from __future__ import annotations

import datetime as dt
import time

from ef_common import (
    ANALYSIS_DIR,
    DEFAULT_MODEL,
    INVENTORY_PATH,
    KINDS,
    PROJECT_ROOT,
    TOPICS,
    Transcript,
    ask_claude,
    extract_json,
    hhmmss_to_seconds,
    link_at,
    load_transcript,
    locate_quote,
    log,
    quote_end,
    read_json,
    seconds_to_hhmmss,
    short_ts,
    speakers_by_key,
    write_json,
)

MAX_CHARS = 200_000
TYPES = {"commitment", "criticism", "framing", "policy", "personal_story"}

PROMPT = """\
Below is a transcript of a video recorded after Michigan's Nov. 3, 2026 general election, in \
which Democrats won the governorship, both legislative chambers, and the open U.S. Senate seat. \
Each line starts with a [HH:MM:SS] timestamp. There are no speaker labels.

Event: {label} ({kind}), {date}. Recording: "{title}" ({channel}).
Tracked people expected to speak (key: name, office):
{speakers}

=== TRANSCRIPT START ===
{transcript}
=== TRANSCRIPT END ===

You are a careful, nonpartisan policy analyst for the Michigan Health & Hospital Association \
(MHA). Work out who is speaking from context (introductions, "thank you, governor", content). \
Ignore news anchors, reporters' questions, emcees, and anyone not in the tracked list.

Return:
1. "headline": one neutral sentence on the main message of the tracked speaker(s).
2. "health_summary": two or three neutral sentences on what the tracked speaker(s) said about \
health and health care. If they said nothing about it, say so plainly.
3. "priorities": the agenda items each tracked speaker says they will pursue or fight for \
(any policy area, not only health), at most 6 per speaker, most emphasized first.
4. "findings": EVERY distinct statement by a tracked speaker about health or health care. \
Count: health care / health insurance / coverage; Medicaid or the Healthy Michigan Plan; \
Medicare; the ACA and premiums; prescription drugs, PBMs, pharma; hospitals, doctors, nurses, \
clinics; the cost of care or medical bills; federal health cuts (H.R. 1, "One Big Beautiful \
Bill"); public health, vaccines, science; mental or behavioral health and addiction; \
reproductive health and abortion; long-term care and seniors' care; disability services; \
rural access; medical debt; insurers or private equity in health care; personal stories about \
illness or care. A generic "lower costs" line counts ONLY if health care is named in it.

Rules for each finding and priority:
- "speaker": the tracked key.
- "timestamp": the [HH:MM:SS] of the line where the quote BEGINS, copied exactly, no brackets.
- "quote": the speaker's exact words copied verbatim from the transcript, one to three \
sentences, enough to stand alone. Never paraphrase, never fix grammar, never join words from \
non-adjacent lines.
Findings also need:
- "topics": one or more of {topics}.
- "type": "commitment" (a promise or plan), "policy" (describes a specific policy, bill, or \
program), "criticism" (attacks an opponent, Washington, or a policy), "framing" (values or \
rhetoric), or "personal_story".
- "hospital_relevance": "high" (directly affects hospital finances, Medicaid or coverage \
levels, prices, workforce, or regulation), "medium" (affects the broader health system), or \
"low" (rhetorical).
- "context": one neutral sentence describing what was said.
- "why_it_matters": one sentence on what it could mean for Michigan hospitals, grounded only \
in what was said. No speculation beyond the words.
Priorities need: "label" (2-6 words, e.g. "Lower health care costs").
If the same point repeats within about a minute, return it once with the strongest quote.

Respond with STRICT JSON ONLY, no prose, no markdown fences:
{{"headline": "...", "health_summary": "...", "priorities": [{{"speaker": "benson", \
"label": "...", "timestamp": "HH:MM:SS", "quote": "..."}}], "findings": [{{"speaker": \
"benson", "timestamp": "HH:MM:SS", "quote": "...", "topics": ["costs"], "type": "commitment", \
"hospital_relevance": "medium", "context": "...", "why_it_matters": "..."}}]}}\
"""


def analysis_path(key: str):
    return ANALYSIS_DIR / f"{key}.json"


def _verify(t: Transcript, url: str, items: list[dict], valid_speakers: set[str]) -> list[dict]:
    out = []
    for f in items:
        if not isinstance(f, dict):
            continue
        quote = str(f.get("quote") or "").strip()
        ts = str(f.get("timestamp") or "").strip()
        hint = hhmmss_to_seconds(ts)
        located = locate_quote(t, quote, hint) if quote else None
        seconds = located if located is not None else hint
        item = dict(f)
        item.update(
            quote=quote,
            speaker=f.get("speaker") if f.get("speaker") in valid_speakers else None,
            seconds=seconds,
            timestamp=seconds_to_hhmmss(seconds),
            ts_label=short_ts(seconds),
            end_seconds=quote_end(t, seconds, quote),
            link=link_at(url, seconds),
            verified=located is not None,
        )
        if "topics" in f:
            item["topics"] = [x for x in f.get("topics") or [] if x in TOPICS] or ["other_health"]
            item["type"] = f.get("type") if f.get("type") in TYPES else "framing"
            item["hospital_relevance"] = (
                f.get("hospital_relevance") if f.get("hospital_relevance") in {"high", "medium", "low"} else "low"
            )
        out.append(item)
    out.sort(key=lambda x: x["seconds"])
    return out


def analyze_event(ev: dict, t: Transcript, model: str) -> dict:
    spk = speakers_by_key()
    names = "\n".join(
        f"- {k}: {spk[k]['name']}, {spk[k]['office']}" for k in ev["speakers"] if k in spk
    )
    # Allow any tracked person to be attributed (e.g. Whitmer introducing Benson).
    others = [k for k in spk if k not in ev["speakers"]]
    names += "\nAlso tracked if they speak: " + ", ".join(f"{k} ({spk[k]['name']})" for k in others)
    text = t.as_text()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...[truncated]..."
    prompt = PROMPT.format(
        label=ev["label"],
        kind=KINDS.get(ev.get("kind"), ev.get("kind")),
        date=ev["event_date"],
        title=ev.get("title"),
        channel=ev.get("channel"),
        speakers=names,
        transcript=text,
        topics=", ".join(TOPICS),
    )
    start = time.time()
    raw, cost = ask_claude(prompt, model)
    parsed = extract_json(raw)
    if parsed is None:
        log("  could not parse JSON; retrying once")
        raw, cost2 = ask_claude(prompt + "\n\nReturn ONLY the JSON object.", model)
        cost = (cost or 0) + (cost2 or 0)
        parsed = extract_json(raw) or {}
    valid = set(spk)
    findings = _verify(t, ev["url"], parsed.get("findings") or [], valid)
    priorities = _verify(t, ev["url"], parsed.get("priorities") or [], valid)
    bad = [f for f in findings + priorities if not f["verified"]]
    log(
        f"  {len(findings)} health findings, {len(priorities)} priorities, {len(bad)} unverified "
        f"in {time.time() - start:.0f}s cost={'$%.3f' % cost if cost else 'n/a'}"
    )
    for f in bad:
        log(f"    unverified @{f['timestamp']}: {f['quote'][:90]}")
    return {
        "event_key": ev["event_key"],
        "canonical_id": ev["canonical_id"],
        "url": ev["url"],
        "model": model,
        "analyzed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "segments": len(t.entries),
        "headline": str(parsed.get("headline") or "").strip(),
        "health_summary": str(parsed.get("health_summary") or "").strip(),
        "priorities": priorities,
        "findings": findings,
    }


def _events_with_transcripts():
    inv = read_json(INVENTORY_PATH) or {}
    for ev in inv.get("events", []):
        if not ev.get("transcript_path"):
            continue
        t = load_transcript(PROJECT_ROOT / ev["transcript_path"], ev["url"], ev["canonical_id"], ev.get("title", ""))
        if t and t.entries:
            yield ev, t


def run(model: str = DEFAULT_MODEL, force: bool = False, only: str | None = None) -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    for ev, t in _events_with_transcripts():
        if only and only not in ev["event_key"]:
            continue
        path = analysis_path(ev["event_key"])
        cached = read_json(path)
        if (
            cached
            and not force
            and cached.get("segments") == len(t.entries)
            and cached.get("canonical_id") == ev["canonical_id"]
        ):
            continue
        log(f"analyzing {ev['event_date']}  {ev['label']}")
        write_json(path, analyze_event(ev, t, model))


def reverify() -> None:
    spk = set(speakers_by_key())
    for ev, t in _events_with_transcripts():
        path = analysis_path(ev["event_key"])
        a = read_json(path)
        if not a:
            continue
        a["findings"] = _verify(t, ev["url"], a["findings"], spk)
        a["priorities"] = _verify(t, ev["url"], a["priorities"], spk)
        write_json(path, a)
        bad = sum(1 for f in a["findings"] + a["priorities"] if not f["verified"])
        log(f"{ev['event_key']}: {bad} unverified")
