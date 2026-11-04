"""Classify each Speaker Hall presser transcript for attacks on hospitals.

One cached JSON per video in reports/hospital_attacks/analysis/. Every quote is
verified against the transcript before it can be counted.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import time

import typer

from common import (  # noqa: E402
    ANALYSIS_DIR,
    Transcript,
    hhmmss_to_seconds,
    load_hall_transcripts,
    normalize,
    read_json,
    ts_link,
    write_json,
)

MAX_TRANSCRIPT_CHARS = 200_000
DEFAULT_MODEL = "opus"

TAGS = [
    "brian_peters",
    "call_to_fire",
    "named_hospital",
    "named_ceo",
    "mha",
    "budget_cut",
    "340b",
    "transparency",
    "work_projects",
    "imlc",
    "con",
    "price_controls",
    "facility_fees",
    "executive_pay",
    "pricing",
    "consolidation",
    "charity_care",
    "medicaid",
    "other",
]

ATTACK_PROMPT = """\
Below is the transcript of a Michigan House Speaker Matt Hall press conference. Each line is \
prefixed with a [HH:MM:SS] timestamp. There are no speaker labels: Speaker Hall is the \
person at the podium, and reporters ask questions.

=== TRANSCRIPT START ===
{transcript}
=== TRANSCRIPT END ===

You are a careful, nonpartisan analyst working for the Michigan Health & Hospital \
Association (MHA). Find every place where SPEAKER HALL says something about hospitals, \
health systems, hospital executives, the MHA, or MHA CEO Brian Peters. Only count \
statements Hall himself makes. Skip reporter questions and skip Hall merely repeating a \
question back before answering. If another official is clearly speaking, skip them.

"Hospitals" includes: the word hospital(s); named hospitals or health systems (Henry Ford, \
Corewell, Beaumont, Trinity, McLaren, Sparrow, University of Michigan Health/Michigan \
Medicine, Munson, Bronson, Ascension, MyMichigan, Detroit Medical Center, etc.); their \
CEOs; the Michigan Health & Hospital Association / MHA; Brian Peters; hospital prices, \
rates, billing, facility fees, margins, executive pay, consolidation, charity care, \
340B, hospital transparency, certificate of need (CON), the Interstate Medical Licensure \
Compact (IMLC), hospital price controls / a hospital cost review board, hospital budget \
cuts or Medicaid rates paid to hospitals, and "work project" or capital funding for \
hospitals. Do NOT count generic healthcare, insurance, or Medicaid talk unless hospitals \
are specifically implicated.

Categories:
- "attack": Hall criticizes, blames, threatens, mocks, or disparages hospitals, a health \
system, a hospital executive, the MHA, or Brian Peters, or calls for someone to be fired \
or replaced, or frames hospitals as greedy, monopolistic, dishonest, overpaid, or the cause \
of high costs.
- "legislation": Hall introduces, describes, advocates, or announces action on a bill, \
budget provision, discharge motion, or policy that directly affects hospitals (budget \
cuts, price controls, facility fee bills, transparency bills, 340B, CON, IMLC, work \
projects), WITHOUT it also being an attack. If a statement is both, use "attack" and \
fill in the "bill" field.
- "mention": any other hospital-related remark by Hall, including neutral or positive ones.

Rules for each finding:
- "timestamp": the [HH:MM:SS] of the line where the quote BEGINS, copied exactly, no brackets.
- "quote": Hall's exact words copied verbatim from the transcript, one to three sentences, \
enough to stand alone as a citation. Never paraphrase, never fix grammar, never merge \
words from non-adjacent lines.
- "category": "attack" | "legislation" | "mention".
- "tags": zero or more of {tags}. Use "brian_peters" whenever Peters is named or clearly \
referenced (e.g. "the head of the hospital association"), "call_to_fire" when Hall says he \
should be fired, replaced, resign, or step down, "named_hospital" when a specific hospital \
or health system is named, "named_ceo" when a specific hospital executive is named or \
clearly referenced, "mha" for the association itself.
- "target": the named hospital, system, person, or organization, else null.
- "bill": bill number, budget item, or policy name if one is referenced, else null.
- "context": one neutral sentence describing what was said and why.

Distinctness: each finding is one distinct point. If Hall repeats the same point within \
about a minute, return it ONCE using the strongest quote. If he returns to the same theme \
later in the presser (more than a minute apart, or in a new answer), that is a separate \
finding.

Respond with STRICT JSON ONLY - no prose, no markdown fences - in exactly this shape:
{{"legislation_discussed": true, "findings": [{{"timestamp": "HH:MM:SS", "quote": "...", \
"category": "attack", "tags": ["brian_peters"], "target": "...", "bill": null, "context": "..."}}]}}

Set "legislation_discussed" to true if Hall introduced or spoke about any legislation, \
budget provision, or policy that impacts hospitals anywhere in this press conference. \
If hospitals are never mentioned, respond with {{"legislation_discussed": false, "findings": []}}\
"""


def _log(msg: str) -> None:
    typer.echo(msg, err=True)


def _extract_json(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def _ask_claude(prompt: str, model: str) -> tuple[str, float | None]:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    os.environ.pop("CLAUDECODE", None)  # allow running inside a Claude Code session
    # Corporate TLS interception (Zscaler) breaks Node's bundled CA store; trust the
    # exported root if present. See CLAUDE.md.
    from pathlib import Path

    ca = Path.home() / ".claude" / "certs" / "corporate-root-ca.pem"
    if ca.exists() and not os.environ.get("NODE_EXTRA_CA_CERTS"):
        os.environ["NODE_EXTRA_CA_CERTS"] = str(ca)
    collected = ""
    cost = None
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            model=model,
            max_turns=2,
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    collected += block.text
        elif isinstance(message, ResultMessage):
            if message.is_error:
                _log(f"  model error: {message.result}")
            cost = message.total_cost_usd
    return collected, cost


def ask_claude(prompt: str, model: str, attempts: int = 4) -> tuple[str, float | None]:
    """Call Claude via the Claude Code login; retry transient failures with backoff.

    Network blips (VPN, proxy SSL interception) surface as a crashed subprocess or an
    empty reply, so both are retried.
    """
    delay = 15
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            text, cost = asyncio.run(_ask_claude(prompt, model))
            if text.strip():
                return text, cost
            _log(f"  empty reply from model (attempt {attempt}/{attempts})")
        except Exception as e:  # noqa: BLE001
            last = e
            _log(f"  model call failed (attempt {attempt}/{attempts}): {str(e)[:160]}")
        if attempt < attempts:
            time.sleep(delay)
            delay = min(delay * 2, 120)
    if last:
        raise last
    return "", None


# ---------------------------------------------------------------------------
# Quote verification
# ---------------------------------------------------------------------------


def _locate_quote(t: Transcript, quote: str, hint_seconds: int, window: int = 90) -> int | None:
    """Return the seconds of the transcript entry where the quote begins, or None.

    Checks entries near the hinted timestamp first, then the whole transcript. Matches on
    the first eight normalized words of the quote against a rolling join of adjacent entries.
    """
    words = normalize(quote).split()
    if len(words) < 3:
        return None
    entries = t.entries
    n = len(entries)
    # Caption-style transcripts have ~5 words per line, so join enough lines to hold a probe.
    avg_words = sum(len(e.text.split()) for e in entries) / max(n, 1)
    span = 3 if avg_words > 12 else 8

    joined_cache: dict[int, str] = {}

    def joined(i: int, j: int | None = None) -> str:
        end = min(n, i + span) if j is None else j
        key = (i, end)
        if key not in joined_cache:
            joined_cache[key] = normalize(" ".join(e.text for e in entries[i:end]))
        return joined_cache[key]

    def tighten(i: int, probe: str) -> int:
        """The probe matched somewhere in entries[i:i+span]; return the latest start
        index that still contains it, so the link lands on the right line."""
        end = min(n, i + span)
        best = i
        for j in range(i + 1, end):
            if probe in joined(j, end):
                best = j
            else:
                break
        return best

    # Probes: the opening words (skipping up to two leading fillers the model may add),
    # then a slice from the middle, then the closing words, then a short opener.
    size = min(8, len(words))
    probes = [" ".join(words[k : k + size]) for k in range(0, min(3, len(words) - size + 1))]
    if len(words) > 12:
        mid = len(words) // 2
        probes.append(" ".join(words[mid - 4 : mid + 4]))
        probes.append(" ".join(words[-8:]))
    probes.append(" ".join(words[:5]))

    near = [i for i, e in enumerate(entries) if abs(e.seconds - hint_seconds) <= window]
    near_set = set(near)
    far = [i for i in range(n) if i not in near_set]
    for probe in probes:
        for i in near + far:
            if probe in joined(i):
                return entries[tighten(i, probe)].seconds
    return None


def _quote_end(t: Transcript, start_seconds: int, quote: str) -> int:
    n_words = len(quote.split())
    idx = next((i for i, e in enumerate(t.entries) if e.seconds >= start_seconds), None)
    if idx is None:
        return start_seconds + 30
    acc = 0
    for i in range(idx, len(t.entries)):
        acc += len(t.entries[i].text.split())
        if acc >= n_words:
            end = t.entries[i + 1].seconds if i + 1 < len(t.entries) else t.entries[i].seconds + 30
            return max(start_seconds + 8, min(end, start_seconds + 90))
    return start_seconds + 30


def verify_findings(t: Transcript, raw: list[dict]) -> list[dict]:
    out: list[dict] = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        quote = str(f.get("quote") or "").strip()
        ts = str(f.get("timestamp") or "").strip()
        hint = hhmmss_to_seconds(ts)
        located = _locate_quote(t, quote, hint) if quote else None
        category = str(f.get("category") or "mention").lower()
        if category not in {"attack", "legislation", "mention"}:
            category = "mention"
        tags = [x for x in (f.get("tags") or []) if x in TAGS]
        seconds = located if located is not None else hint
        item = {
            "timestamp": ts,
            "seconds": seconds,
            "end_seconds": _quote_end(t, seconds, quote),
            "link": ts_link(t.video_id, seconds),
            "quote": quote,
            "category": category,
            "tags": tags,
            "target": f.get("target") or None,
            "bill": f.get("bill") or None,
            "context": str(f.get("context") or "").strip(),
            "verified": located is not None,
            "timestamp_corrected": located is not None and abs(located - hint) > 20,
        }
        if item["timestamp_corrected"]:
            from common import seconds_to_hhmmss

            item["timestamp"] = seconds_to_hhmmss(located)
        out.append(item)
    out.sort(key=lambda x: x["seconds"])
    return out


# ---------------------------------------------------------------------------
# Per-video analysis
# ---------------------------------------------------------------------------


def analysis_path(video_id: str):
    return ANALYSIS_DIR / f"{video_id}.json"


def analyze_video(t: Transcript, model: str) -> dict:
    transcript = t.as_text()
    truncated = False
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n...[transcript truncated]..."
        truncated = True
        _log(f"  WARNING transcript truncated to {MAX_TRANSCRIPT_CHARS} chars")
    prompt = ATTACK_PROMPT.format(transcript=transcript, tags=", ".join(TAGS))

    start = time.time()
    text, cost = ask_claude(prompt, model)
    parsed = _extract_json(text)
    if parsed is None:
        # One retry: models occasionally wrap the JSON or emit prose.
        _log("  could not parse JSON; retrying once")
        text, cost2 = ask_claude(prompt + "\n\nReturn ONLY the JSON object.", model)
        cost = (cost or 0) + (cost2 or 0)
        parsed = _extract_json(text) or {"legislation_discussed": False, "findings": []}

    findings = verify_findings(t, parsed.get("findings") or [])
    unverified = [f for f in findings if not f["verified"]]
    attacks = sum(1 for f in findings if f["verified"] and f["category"] == "attack")
    _log(
        f"  {len(findings)} findings ({attacks} attacks, {len(unverified)} unverified) "
        f"in {time.time() - start:.0f}s cost={'$%.3f' % cost if cost else 'n/a'}"
    )
    for f in unverified:
        _log(f"    unverified @{f['timestamp']}: {f['quote'][:90]}")

    return {
        "video_id": t.video_id,
        "title": t.title,
        "event_date": t.event_date,
        "publish_date": t.publish_date,
        "url": t.url,
        "model": model,
        "analyzed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "transcript_path": str(t.path.name),
        "segments": len(t.entries),
        "truncated": truncated,
        "legislation_discussed": bool(parsed.get("legislation_discussed"))
        or any(f["category"] == "legislation" or f["bill"] for f in findings if f["verified"]),
        "findings": findings,
    }


def _skip_duplicates(transcripts: dict[str, Transcript]) -> dict[str, Transcript]:
    """Drop videos the backlog step marked as duplicate uploads."""
    from common import INVENTORY_PATH

    inv = read_json(INVENTORY_PATH) or {}
    dupes = {p["video_id"] for p in inv.get("pressers", []) if p.get("status") == "duplicate"}
    return {k: v for k, v in transcripts.items() if k not in dupes}


def reverify() -> None:
    """Re-run quote verification over cached analyses (no LLM calls)."""
    transcripts = load_hall_transcripts()
    fixed = still = 0
    for path in sorted(ANALYSIS_DIR.glob("*.json")):
        a = read_json(path)
        t = transcripts.get(a["video_id"]) if a else None
        if not a or not t:
            continue
        before = sum(1 for f in a["findings"] if not f.get("verified"))
        a["findings"] = verify_findings(t, a["findings"])
        after = sum(1 for f in a["findings"] if not f.get("verified"))
        a["legislation_discussed"] = bool(a.get("legislation_discussed")) or any(
            f["category"] == "legislation" or f["bill"] for f in a["findings"] if f["verified"]
        )
        write_json(path, a)
        fixed += before - after
        still += after
        for f in a["findings"]:
            if not f["verified"]:
                _log(f"  still unverified {a['event_date']} @{f['timestamp']}: {f['quote'][:90]}")
    _log(f"reverify: {fixed} quotes newly verified, {still} still unverified")


def run(
    model: str = DEFAULT_MODEL,
    force: bool = False,
    only: str | None = None,
    shard: str | None = None,
) -> dict[str, dict]:
    transcripts = _skip_duplicates(load_hall_transcripts())
    if only:
        transcripts = {k: v for k, v in transcripts.items() if k == only or only in v.title}
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    todo = sorted(transcripts.values(), key=lambda t: (t.event_date, t.video_id))
    if shard:
        # "i/n": process every n-th video starting at i (1-based), for parallel workers.
        i, n = (int(x) for x in shard.split("/"))
        todo = [t for idx, t in enumerate(todo) if idx % n == i - 1]
    _log(f"{len(todo)} pressers to consider")
    for i, t in enumerate(todo, 1):
        path = analysis_path(t.video_id)
        cached = read_json(path)
        if cached and not force and cached.get("segments") == len(t.entries):
            results[t.video_id] = cached
            continue
        _log(f"[{i}/{len(todo)}] {t.event_date}  {t.title}")
        result = analyze_video(t, model)
        write_json(path, result)
        results[t.video_id] = result
    return results


if __name__ == "__main__":
    run()
