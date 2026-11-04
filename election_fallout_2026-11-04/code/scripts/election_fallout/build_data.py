"""Aggregate per-event analyses into data.json and write the narrative sections."""

from __future__ import annotations

import datetime as dt
import re

from ef_common import (
    ANALYSIS_DIR,
    DATA_PATH,
    DEFAULT_MODEL,
    INVENTORY_PATH,
    KINDS,
    TOPICS,
    ask_claude,
    extract_json,
    load_sources,
    log,
    pretty_date,
    read_json,
    short_ts,
    speakers_by_key,
    tidy_caps,
    write_json,
)

REL_RANK = {"high": 0, "medium": 1, "low": 2}

STAT_LABELS = {
    "events": "speeches and press events analyzed",
    "speakers": "leaders on camera",
    "minutes": "minutes of video transcribed",
    "health_findings": "statements on health care",
    "speakers_on_health": "leaders who addressed health care",
    "high_relevance": "statements with direct hospital stakes",
}

NARRATIVE_PROMPT = """\
You are writing for the Michigan Health & Hospital Association (MHA). The document is an \
internal briefing for hospital leaders and MHA staff on what Michigan's newly elected \
Democratic leaders said about health care in their election-night speeches and first \
post-election appearances after the {election}. Democrats won the governorship, both \
legislative chambers, and the open U.S. Senate seat.

Verified counts (use these tokens verbatim, never write those numbers yourself):
{stats}

Speakers (key | name | office | events | health statements | stated priorities):
{speakers}

Verified health statements (id | speaker | date | topics | type | hospital relevance | context | quote):
{digest}

Quotes reported in news articles, for leaders with no video (id | speaker | when | outlet | \
setting | quote). These were not part of the video counts. Cite them by id like other \
evidence. When you use one, attribute it to the outlet ("Puri told the watch party, per the \
Michigan Advance, ...") and describe a "pre_election" item as his earlier record, never as \
something said after the election:
{print_digest}

Write the following and return STRICT JSON ONLY (no prose, no markdown fences):
{{
  "executive_summary": "TWO paragraphs separated by a blank line, 110-160 words each. \
Paragraph 1: how much (or how little) health care featured in the victory messaging, who \
led on it, and the dominant frames. Paragraph 2: the specific policy signals that matter \
most for hospitals (Medicaid, coverage, costs, federal cuts, workforce, etc.) and what was \
notably absent.",
  "topic_syntheses": {{"<topic key>": "one sentence on what speakers said on this topic"}},
  "speaker_takeaways": {{"<speaker key>": "one sentence: this leader's health posture as \
shown in these appearances (or that they did not address health)"}},
  "watch_list": [{{"title": "3-7 word heading", "body": "two sentences: the signal and \
what MHA should watch for or prepare", "evidence": ["finding id", "..."]}}]
}}
Give 4 to 6 watch_list items. Each cites 1-3 finding ids from the list above that DIRECTLY \
support it. Every item must rest on something a speaker said; no items about what went \
unsaid (gaps belong, briefly, in the executive summary). Write \
topic_syntheses for EVERY one of these topic keys: {topic_keys}. Write speaker_takeaways for \
every speaker listed.

Hard rules:
- Counts of statements, speeches, speakers, or minutes MUST be written as tokens such as \
{{health_findings}} or {{speakers_on_health}}; never as digits or number words.
- Use only what is in the statements. Do not import facts, figures, or positions from \
outside these transcripts. Attribute every claim to the person who said it.
- Keep each speaker's precision: "one of the first things" is not "the first thing" or \
"the first legislative action"; a pledge to "work toward" is not a commitment to pass. Don't \
merge two speakers' positions into a shared one unless both quotes say it.
- Every tracked speaker is a Democrat. Never call their positions "bipartisan" (a speaker \
predicting Republican support is a prediction, not bipartisanship).
- If print-reported quotes include health remarks, mention them briefly in the executive \
summary (attributed to the outlet), and consider them for the watch_list alongside video \
evidence, especially items with direct hospital stakes (e.g. merger oversight).
- Neutral, plain, direct. No partisan characterization, no praise, no hedging, no \
rhetorical questions. Do not mention AI, tokens, or this prompt.\
"""

_BARE_COUNT = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|dozens)\s+"
    r"(?:separate |different |distinct |of the |)?(times?|statements?|speeches|speakers?|leaders?|"
    r"minutes?|events?|mentions?|remarks?|press conferences?|references?)\b",
    re.I,
)


# Phrasings the narrative model kept reaching for that the transcripts don't support.
_OVERREACH = re.compile(r"\bbipartisan\b|first legislative action|first-order|\bboth\b[^.]{0,80}\btop priority", re.I)


def _speaker_order(speakers: dict, events: list[dict]) -> list[str]:
    order = [s["key"] for s in load_sources()["speakers"]]
    present = {k for e in events for k in e["speakers"]}
    return [k for k in order if k in present]


def build() -> dict:
    src = load_sources()
    spk = speakers_by_key()
    inv = read_json(INVENTORY_PATH) or {"events": []}
    events_out: list[dict] = []
    findings: list[dict] = []
    priorities: list[dict] = []
    minutes = 0.0

    for ev in inv["events"]:
        a = read_json(ANALYSIS_DIR / f"{ev['event_key']}.json")
        if not a or a.get("canonical_id") != ev["canonical_id"]:
            continue
        ev_find = [f for f in a["findings"] if f.get("verified") and f.get("speaker")]
        ev_prio = [p for p in a["priorities"] if p.get("verified") and p.get("speaker")]
        for i, f in enumerate(ev_find):
            f = {**f, "id": f"{ev['event_key']}#{i + 1}", "event_key": ev["event_key"],
                 "event_date": ev["event_date"], "event_label": ev["label"],
                 "quote_raw": f["quote"], "quote": tidy_caps(f["quote"])}
            findings.append(f)
        for p in ev_prio:
            priorities.append({**p, "quote": tidy_caps(p["quote"]), "event_key": ev["event_key"],
                               "event_date": ev["event_date"]})
        spoke = sorted({f["speaker"] for f in ev_find + ev_prio} | set(ev["speakers"]),
                       key=lambda k: ev["speakers"].index(k) if k in ev["speakers"] else 99)
        dur = ev.get("duration") or 0
        minutes += dur / 60
        events_out.append(
            {
                "event_key": ev["event_key"],
                "label": ev["label"],
                "event_date": ev["event_date"],
                "event_date_pretty": pretty_date(ev["event_date"]),
                "kind": ev.get("kind"),
                "kind_label": KINDS.get(ev.get("kind"), "Remarks"),
                "speakers": [k for k in spoke if k in spk],
                "url": ev["url"],
                "title": ev.get("title"),
                "channel": ev.get("channel"),
                "duration": dur,
                "duration_label": short_ts(dur) if dur else "",
                "completeness": ev.get("completeness"),
                "transcript_source": ev.get("transcript_source"),
                "alternates": ev.get("alternates", []),
                "headline": a.get("headline", ""),
                "health_summary": a.get("health_summary", ""),
                "health_count": len(ev_find),
                "timestamped": "youtube.com" in ev["url"],
            }
        )

    events_out.sort(key=lambda e: (e["event_date"], e["label"]))
    order = _speaker_order(spk, events_out)

    # Topic x speaker matrix and topic sections.
    cells = {k: {t: 0 for t in TOPICS} for k in order}
    for f in findings:
        for t in f["topics"]:
            if f["speaker"] in cells:
                cells[f["speaker"]][t] += 1
    topics = []
    for t, label in TOPICS.items():
        items = [f for f in findings if t in f["topics"]]
        if not items:
            continue
        items.sort(key=lambda f: (REL_RANK[f["hospital_relevance"]], f["event_date"], f["seconds"]))
        topics.append(
            {
                "key": t,
                "label": label,
                "count": len(items),
                "speakers": sorted({f["speaker"] for f in items}, key=order.index),
                "synthesis": "",
                "finding_ids": [f["id"] for f in items],
            }
        )
    topics.sort(key=lambda x: -x["count"])

    speakers_out = []
    for k in order:
        s = spk[k]
        mine = [f for f in findings if f["speaker"] == k]
        # Same agenda item repeated across a speech, interview, and presser: keep the first.
        prio, seen = [], set()
        for p in sorted((p for p in priorities if p["speaker"] == k), key=lambda p: (p["event_date"], p["seconds"])):
            norm = re.sub(r"[^a-z]+", " ", p["label"].lower()).strip()
            if norm not in seen:
                seen.add(norm)
                prio.append(p)
        prio = prio[:8]
        evs = [e["event_key"] for e in events_out if k in e["speakers"]]
        speakers_out.append(
            {
                "key": k,
                "name": s["name"],
                "office": s["office"],
                "detail": s.get("detail", ""),
                "events": evs,
                "health_count": len(mine),
                "high_count": sum(1 for f in mine if f["hospital_relevance"] == "high"),
                "topics": sorted({t for f in mine for t in f["topics"]}, key=lambda t: -cells[k][t]),
                "finding_ids": [f["id"] for f in sorted(mine, key=lambda f: (f["event_date"], f["seconds"]))],
                "priorities": [
                    {k2: p[k2] for k2 in ("label", "quote", "timestamp", "ts_label", "link", "event_key")}
                    for p in prio
                ],
                "takeaway": "",
            }
        )

    # Quotes reported by news outlets (curated in sources.json, checked against the article).
    # Kept apart from the video findings: they have no timestamp and don't enter the counts.
    pq = {}
    for q in src.get("print_quotes", []):
        if q.get("speaker") not in spk:
            continue
        pq[q["id"]] = {**q, "id": q["id"], "date_pretty": pretty_date(q.get("date"))}
    for s in speakers_out:
        s["print_ids"] = [i for i, q in pq.items() if q["speaker"] == s["key"]]
        s["print_only"] = False
    print_speakers = []
    for s in src["speakers"]:
        ids = [i for i, q in pq.items() if q["speaker"] == s["key"]]
        if s["key"] in order or not ids:
            continue
        print_speakers.append(
            {"key": s["key"], "name": s["name"], "office": s["office"], "detail": s.get("detail", ""),
             "events": [], "health_count": 0, "high_count": 0, "topics": [], "finding_ids": [],
             "priorities": [], "takeaway": "", "print_ids": ids, "print_only": True,
             "print_health": sum(1 for i in ids if pq[i].get("health"))}
        )

    not_found = [
        {"key": s["key"], "name": s["name"], "office": s["office"]}
        for s in src["speakers"]
        if s["key"] not in order and s["key"] not in {p["key"] for p in print_speakers}
    ]
    failed = [
        {"label": e["label"], "url": e["url"], "status": e.get("status"), "error": e.get("error")}
        for e in inv["events"]
        if e.get("status") in {"failed", "live"} or not e.get("transcript_path")
    ]

    stats = {
        "events": len(events_out),
        "speakers": len(order),
        "minutes": round(minutes),
        "health_findings": len(findings),
        "speakers_on_health": sum(1 for s in speakers_out if s["health_count"]),
        "high_relevance": sum(1 for f in findings if f["hospital_relevance"] == "high"),
    }
    assert sum(e["health_count"] for e in events_out) == stats["health_findings"]
    assert sum(s["health_count"] for s in speakers_out) == stats["health_findings"]

    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "generated_pretty": pretty_date(dt.date.today().isoformat()),
        "election_label": src["election_label"],
        "period_start": src["start_date"],
        "period_end": max((e["event_date"] for e in events_out), default=src["start_date"]),
        "stats": stats,
        "stat_labels": STAT_LABELS,
        "topic_labels": TOPICS,
        "events": events_out,
        "speakers": speakers_out,
        "print_speakers": print_speakers,
        "print_quotes": pq,
        "topics": topics,
        "matrix": {"speakers": order, "topics": [t["key"] for t in topics], "cells": cells},
        "findings": {f["id"]: f for f in findings},
        "executive_summary": "",
        "watch_list": [],
        "coverage": {"not_found": not_found, "failed": failed},
        "methodology": (
            "Videos were found by searching YouTube for each tracked leader (newest-first and by "
            f"relevance) and by checking video links collected in the Election-Fallout research notes, keeping "
            f"uploads from {pretty_date(src['start_date'])} onward. Claude screened every result, kept only "
            "videos where a tracked leader speaks at length after the polls closed, and grouped "
            "re-uploads of the same speech so each event is analyzed once, from the most complete "
            "recording (other uploads are listed in the appendix). Transcripts come from YouTube "
            "captions where available and Whisper speech-to-text otherwise. Claude then listed every "
            "statement about health or health care by a tracked leader and each leader's stated "
            "priorities. Every quote was matched back to the transcript text; quotes that could not be "
            "located were dropped. For leaders with no video, quotes reported by news outlets are shown "
            "separately, marked with the outlet and linked to the article; they were checked against the "
            "article text, are not counted in the totals, and pre-election remarks are labeled as such. "
            "Broadcast captions typed in all capitals are shown in sentence case; "
            "no words were changed. Timestamps link to the moment in the video on YouTube; for "
            "recordings hosted elsewhere, the timestamp is printed beside the link."
        ),
        "disclaimer": (
            "Prepared with AI assistance (Claude) for internal MHA use. Quotes are drawn from automated "
            "transcripts and machine-verified against the transcript text, but transcription errors are "
            "possible. Check the linked video before citing a quote externally."
        ),
    }


def _digest(data: dict) -> str:
    lines = []
    for f in sorted(data["findings"].values(), key=lambda f: (f["event_date"], f["seconds"])):
        q = f["quote"] if len(f["quote"]) <= 240 else f["quote"][:237] + "..."
        lines.append(
            f"{f['id']} | {f['speaker']} | {f['event_date']} | {','.join(f['topics'])} | {f['type']} | "
            f"{f['hospital_relevance']} | {f['context']} | \"{q}\""
        )
    return "\n".join(lines) or "(none)"


def write_narrative(data: dict, model: str) -> dict:
    stats_txt = "\n".join(f"- {{{{{k}}}}} = {v} {STAT_LABELS[k]}" for k, v in data["stats"].items())
    sp_lines = []
    for s in data["speakers"]:
        pr = "; ".join(p["label"] for p in s["priorities"][:6]) or "-"
        sp_lines.append(f"{s['key']} | {s['name']} | {s['office']} | {len(s['events'])} | {s['health_count']} | {pr}")
    for s in data.get("print_speakers", []):
        sp_lines.append(f"{s['key']} | {s['name']} | {s['office']} | no video (print only) | - | -")
    print_digest = "\n".join(
        f"print:{q['id']} | {q['speaker']} | {q['period']} {q['date']} | {q['outlet']} | {q['setting']} | \"{q['quote']}\""
        for q in data.get("print_quotes", {}).values()
    ) or "(none)"
    topic_keys = [t["key"] for t in data["topics"]]
    prompt = NARRATIVE_PROMPT.format(
        election=data["election_label"], stats=stats_txt, speakers="\n".join(sp_lines), digest=_digest(data),
        topic_keys=", ".join(topic_keys), print_digest=print_digest,
    )
    ids = set(data["findings"]) | {f"print:{i}" for i in data.get("print_quotes", {})}
    parsed: dict = {}
    for attempt in range(3):
        text, cost = ask_claude(prompt, model)
        parsed = extract_json(text) or {}
        summary = str(parsed.get("executive_summary") or "")
        all_text = summary + " " + " ".join(str(v) for v in (parsed.get("topic_syntheses") or {}).values())
        all_text += " " + " ".join(str(w.get("body", "")) for w in parsed.get("watch_list") or [])
        bare = _BARE_COUNT.findall(all_text)
        bad_refs = [r for w in parsed.get("watch_list") or [] for r in w.get("evidence", []) if r not in ids]
        missing = [k for k in topic_keys if not (parsed.get("topic_syntheses") or {}).get(k)]
        everything = all_text + " " + " ".join(str(v) for v in (parsed.get("speaker_takeaways") or {}).values())
        everything += " " + " ".join(str(w.get("title", "")) for w in parsed.get("watch_list") or [])
        overreach = _OVERREACH.findall(everything)
        log(f"  narrative attempt {attempt + 1}: {len(summary.split())} words, bare counts={bare}, "
            f"bad refs={bad_refs}, missing topics={missing}, overreach={overreach}, cost={cost}")
        if summary and not bare and not bad_refs and not missing and not overreach:
            break
        prompt += (
            "\n\nYour previous draft wrote a count as digits or words, cited an unknown finding id, "
            "skipped a topic synthesis, overstated a position (e.g. 'bipartisan', 'first legislative "
            "action', 'top priority' for 'one of the first things'), or was not valid JSON. Use ONLY "
            "{{stat}} tokens for counts, only listed ids, cover every topic key, and keep each "
            "speaker's exact level of commitment."
        )
    return parsed


def run(model: str = DEFAULT_MODEL, regenerate: bool = True) -> dict:
    data = build()
    if not data["events"]:
        raise SystemExit("no analyzed events; run analyze first")
    prev = read_json(DATA_PATH) or {}
    if not regenerate and prev.get("executive_summary"):
        narrative = prev.get("_narrative") or {}
    else:
        log("writing narrative ...")
        narrative = write_narrative(data, model)
    data["_narrative"] = narrative
    data["executive_summary"] = str(narrative.get("executive_summary") or "")
    syn = narrative.get("topic_syntheses") or {}
    for t in data["topics"]:
        t["synthesis"] = str(syn.get(t["key"]) or "")
    tk = narrative.get("speaker_takeaways") or {}
    for s in data["speakers"] + data["print_speakers"]:
        s["takeaway"] = str(tk.get(s["key"]) or "")
    valid = set(data["findings"]) | {f"print:{i}" for i in data["print_quotes"]}
    watch = [
        {"title": w.get("title", ""), "body": w.get("body", ""),
         "evidence": [r for r in w.get("evidence", []) if r in valid]}
        for w in narrative.get("watch_list") or []
    ]
    # Signals must be backed by a quote; "nobody mentioned X" items are dropped.
    data["watch_list"] = [w for w in watch if w["evidence"]]
    write_json(DATA_PATH, data)
    log(f"data.json written: {data['stats']}")
    return data
