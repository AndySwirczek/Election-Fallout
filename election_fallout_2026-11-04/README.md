# Election fallout: what Michigan's new majority said about health care

Bundle prepared November 4, 2026 by the Michigan Health & Hospital Association (prepared with Claude Code).
For internal MHA use.

What Michigan's newly elected Democratic leaders said about health care in their
election-night speeches and first press appearances after the Nov. 3, 2026 general
election. Built on the research notes in
https://github.com/AndySwirczek/Election-Fallout. The full transcripts were contributed
back to that repo in PR #2: https://github.com/AndySwirczek/Election-Fallout/pull/2

## Start here

- `report/election_health_2026-11-04.pdf`: the 20-page briefing. Every quote links to the
  video at the moment it was said.
- `report/election_health_2026-11-04.html`: the same report as a web page.

## At a glance

- 9 speeches, press events and interviews (79 minutes of video), 6 leaders on camera.
- 28 health statements, each verified against its transcript. 12 have direct hospital
  stakes. Only 3 leaders talked about health care on camera: El-Sayed (21 statements),
  Dingell (5) and Benson (2).
- Puri and Camilleri had no video. Their quotes from news articles appear separately in
  the report, marked with the outlet, and are not counted in these totals.
- No post-election video was found for Savit, the U.S. House flips (McCann, Lawrence,
  Hines, Moss), or Whitmer.

## What's inside

| Folder | Contents |
|---|---|
| `report/` | The PDF and HTML report |
| `transcripts/` | One markdown file per event: source video, AI summary, health-statement and priority tables with timestamped YouTube links, then the full transcript. `README.md` indexes them. |
| `transcripts/raw/` | Plain-text timestamped transcripts as the pipeline produced them (YouTube captions, or Whisper for one video) |
| `data/data.json` | Everything the report renders: stats, findings, print quotes, narrative |
| `data/inventory.json` | Events found: canonical recording plus every other upload of the same event |
| `data/analysis/` | Per-event analysis: health statements and stated priorities, each with a verification flag and timestamp |
| `data/triage.json`, `data/candidates.json` | Every YouTube result considered, and why each was kept or rejected |
| `code/` | The pipeline as it sits in the `youtube_transcript_scraper` repo (paths preserved) |

## How it was made

1. **Discover:** search YouTube for each tracked leader. Claude then screens each result
   (keeping only speeches, press events and interviews from after polls closed) and groups
   re-uploads, so each event is analyzed once from its most complete recording.
2. **Transcribe:** YouTube captions where available, Whisper otherwise.
3. **Analyze:** Claude lists every health statement and each leader's stated priorities.
   Quotes that can't be found in the transcript are dropped.
4. **Summarize:** an executive summary and "signals for hospitals", constrained to what was
   said. Automated checks reject invented counts and overstatements such as "bipartisan"
   or "first legislative action".
5. **Render:** React and Tailwind, printed to PDF with Playwright.

Manual curation lives in `code/scripts/election_fallout/sources.json`:
- an exclusion for a 13abc news package that was not Savit's speech;
- a regrouping of a WXYZ upload that was a cut of Benson's victory speech;
- the news quotes for Puri and Camilleri, each checked against the article.

## Rerunning (inside the youtube_transcript_scraper repo)

```powershell
.venv\Scripts\python scripts\election_fallout\run.py all              # refresh everything
.venv\Scripts\python scripts\election_fallout\run.py summarize --keep-summary
.venv\Scripts\python scripts\election_fallout\run.py render
.venv\Scripts\python scripts\election_fallout\run.py export <dir>     # markdown transcripts
```

Reruns only fetch what's new. They also check Puri's, the House Democrats' and Camilleri's
YouTube channels directly. The code needs the repo's `transcriber/` package and
`scripts/hospital_attacks/` helpers (both included under `code/`), plus `claude-agent-sdk`,
`yt-dlp` and bun.

**YouTube caution:** a few hundred rapid requests trigger YouTube's "confirm you're not a
bot" block, which also stops audio downloads. The pipeline is throttled to avoid it; don't
loosen that.

## Caveats

Transcripts are machine-generated and not proofread. Check the video before quoting
externally. All-caps broadcast captions are shown in sentence case in the report (no words
changed); the raw transcripts keep the original casing.
