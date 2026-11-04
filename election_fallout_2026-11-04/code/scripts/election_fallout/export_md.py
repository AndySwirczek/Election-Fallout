"""Export each event's full transcript as markdown (for the Election-Fallout research repo).

Each file has a source header, an index of verified health statements and stated
priorities with timestamped links, then the full timestamped transcript.
"""

from __future__ import annotations

from pathlib import Path

from ef_common import (
    ANALYSIS_DIR,
    INVENTORY_PATH,
    PROJECT_ROOT,
    TOPICS,
    link_at,
    load_transcript,
    log,
    pretty_date,
    read_json,
    short_ts,
    speakers_by_key,
)


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def render_event(ev: dict, analysis: dict | None, spk: dict) -> str:
    t = load_transcript(PROJECT_ROOT / ev["transcript_path"], ev["url"], ev["canonical_id"])
    names = ", ".join(f"{spk[k]['name']} ({spk[k]['office']})" for k in ev["speakers"] if k in spk)
    yt = "youtube.com" in ev["url"]
    src = ev.get("transcript_source") or ""
    how = "Whisper speech-to-text" if src == "whisper" or src.startswith("openai") else f"YouTube captions ({src})"
    lines = [
        f"# {ev['label']}",
        "",
        f"- **Speakers:** {names}",
        f"- **Date:** {pretty_date(ev['event_date'])}",
        f"- **Video:** [{ev.get('title')}]({ev['url']}) ({ev.get('channel')}, {short_ts(ev.get('duration') or 0)})",
        f"- **Transcript:** full, machine-generated via {how}. Not proofread; check the video before quoting.",
    ]
    if not yt:
        lines.append("- **Timestamps:** this player does not support deep links; seek to the time shown.")
    if ev.get("alternates"):
        alts = "; ".join(f"[{a.get('channel') or 'video'}]({a['url']})" for a in ev["alternates"][:8])
        lines.append(f"- **Other uploads of the same event:** {alts}")
    lines.append("")

    if analysis:
        if analysis.get("headline"):
            lines += ["## Summary (AI-generated)", "", analysis["headline"], ""]
            if analysis.get("health_summary"):
                lines += [analysis["health_summary"], ""]
        found = [f for f in analysis.get("findings", []) if f.get("verified")]
        lines += ["## Health-care statements", ""]
        if not found:
            lines += ["None found in this recording.", ""]
        else:
            lines += ["| Time | Speaker | Topics | Quote |", "|---|---|---|---|"]
            for f in found:
                who = spk.get(f.get("speaker"), {}).get("name", "")
                topics = ", ".join(TOPICS.get(x, x) for x in f.get("topics", []))
                lines.append(
                    f"| [{f['ts_label']}]({f['link']}) | {who} | {topics} | \"{_md_escape(f['quote'])}\" |"
                )
            lines.append("")
        pr = [p for p in analysis.get("priorities", []) if p.get("verified")]
        if pr:
            lines += ["## Stated priorities", ""]
            for p in pr:
                who = spk.get(p.get("speaker"), {}).get("name", "")
                lines.append(f"- [{p['ts_label']}]({p['link']}) **{p['label']}** ({who}): \"{p['quote']}\"")
            lines.append("")

    lines += ["## Full transcript", ""]
    for e in t.entries if t else []:
        stamp = f"[{short_ts(e.seconds)}]({link_at(ev['url'], e.seconds)})" if yt else f"[{short_ts(e.seconds)}]"
        lines.append(f"{stamp} {e.text}  ")
    return "\n".join(lines).rstrip() + "\n"


def run(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    spk = speakers_by_key()
    inv = read_json(INVENTORY_PATH) or {"events": []}
    index = ["# Full transcripts of post-election remarks", "",
             "Machine transcripts of each recording, with timestamp links. Health statements are listed first in each file.", "",
             "| Date | Event | Speakers | Health statements |", "|---|---|---|---|"]
    n = 0
    for ev in inv["events"]:
        if not ev.get("transcript_path"):
            continue
        a = read_json(ANALYSIS_DIR / f"{ev['event_key']}.json")
        if a and a.get("canonical_id") != ev["canonical_id"]:
            a = None
        name = f"{ev['event_key']}.md"
        (dest / name).write_text(render_event(ev, a, spk), encoding="utf-8")
        hc = sum(1 for f in (a or {}).get("findings", []) if f.get("verified"))
        who = ", ".join(spk[k]["name"] for k in ev["speakers"] if k in spk)
        index.append(f"| {ev['event_date']} | [{ev['label']}]({name}) | {who} | {hc} |")
        n += 1
    (dest / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    log(f"exported {n} transcripts to {dest}")
