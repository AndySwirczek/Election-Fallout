import type { ReportData, StatKey } from "../types";
import { shortDate } from "../types";
import {
  Badge,
  FindingCard,
  Monogram,
  OutletChip,
  PrintCard,
  SectionHead,
  Tokenized,
  Ts,
  eventByKey,
  speakerName,
} from "./bits";

const COVER_STATS: StatKey[] = ["events", "speakers", "minutes", "health_findings", "speakers_on_health", "high_relevance"];

function periodLabel(data: ReportData): string {
  const a = shortDate(data.period_start);
  const b = shortDate(data.period_end);
  const y = data.period_end.slice(0, 4);
  return a === b ? `${a}, ${y}` : `${a} – ${b}, ${y}`;
}

function Cover({ data }: { data: ReportData }) {
  return (
    <section className="cover">
      <div className="cover-grid" />
      <div className="cover-glow" />
      <div className="relative flex h-full min-h-[11in] flex-col px-[0.75in] pb-[0.6in] pt-[0.7in]">
        <div className="flex items-center justify-between text-[10.5px] font-semibold uppercase tracking-[0.18em] text-mint">
          <span>MHA Advocacy Briefing</span>
          <span>Post-election &middot; {periodLabel(data)}</span>
        </div>
        <div className="mt-[1.5in]">
          <div className="h-[5px] w-[0.9in] bg-coral" />
          <h1 className="font-display mt-6 text-[52px] font-extrabold leading-[0.98] tracking-[-0.035em]">
            What Michigan&rsquo;s new majority said about health care
          </h1>
          <p className="mt-5 max-w-[5.6in] text-[16px] leading-[1.45] text-white/80">
            Election-night speeches and first press appearances from the Democratic leaders who won the
            governorship, the Legislature, and Michigan&rsquo;s open U.S. Senate seat, transcribed, analyzed,
            and linked to the moment each line was spoken.
          </p>
        </div>

        <div className="mt-auto">
          <div className="grid grid-cols-3 gap-px overflow-hidden rounded-[10px] bg-white/15">
            {COVER_STATS.map((k) => (
              <div key={k} className="bg-deep/90 px-4 pb-4 pt-3.5">
                <div className={"num text-[44px] font-bold " + (k === "high_relevance" ? "text-[#ff9d7e]" : "text-white")}>
                  {data.stats[k].toLocaleString()}
                </div>
                <div className="mt-1.5 text-[11.5px] leading-snug text-white/70">{data.stat_labels[k]}</div>
              </div>
            ))}
          </div>
          <div className="mt-6 flex items-end justify-between border-t border-white/20 pt-4 text-[11px] text-white/60">
            <div>
              <div className="font-semibold uppercase tracking-[0.14em] text-mint">Inside</div>
              <div className="mt-1.5 leading-relaxed">
                Executive summary &middot; Signals for hospitals &middot; Themes &amp; quotes
                &middot; Leader profiles &middot; Source videos
              </div>
            </div>
            <div className="text-right">
              Michigan Health &amp; Hospital Association
              <br />
              Prepared {data.generated_pretty}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Summary({ data }: { data: ReportData }) {
  const paras = data.executive_summary.split(/\n\s*\n/).filter(Boolean);
  const top = data.topics.slice(0, 5);
  return (
    <section>
      <SectionHead n="01" title="Executive summary" />
      <div className="grid grid-cols-[1fr_2.15in] gap-7">
        <div className="space-y-3.5 text-[13.5px] leading-[1.62] text-slate">
          {paras.map((p, i) => (
            <p key={i} className={i === 0 ? "first-letter:font-display first-letter:float-left first-letter:mr-1.5 first-letter:text-[44px] first-letter:font-bold first-letter:leading-[0.85] first-letter:text-deep" : ""}>
              <Tokenized text={p} stats={data.stats} />
            </p>
          ))}
        </div>
        <aside className="avoid-break self-start rounded-[8px] bg-wash p-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal">Most-discussed topics</div>
          <ol className="mt-3 space-y-2.5">
            {top.map((t, i) => {
              const max = top[0]?.count || 1;
              return (
                <li key={t.key}>
                  <div className="flex items-baseline justify-between gap-2 text-[11.5px] font-semibold leading-tight text-ink">
                    <span>
                      <span className="mr-1 font-mono text-[10px] text-mute">{i + 1}</span>
                      {t.label}
                    </span>
                    <span className="font-mono text-teal">{t.count}</span>
                  </div>
                  <div className="mt-1 h-[5px] rounded-full bg-line">
                    <div className="h-full rounded-full bg-teal" style={{ width: `${(t.count / max) * 100}%` }} />
                  </div>
                </li>
              );
            })}
          </ol>
          <p className="mt-3 text-[10px] leading-snug text-mute">Statements can carry more than one topic.</p>
        </aside>
      </div>
    </section>
  );
}

// Topic x leader dot grid. Not rendered (removed from the report on request); kept for reuse.
export function Matrix({ data }: { data: ReportData }) {
  const topics = data.matrix.topics;
  const max = Math.max(1, ...data.matrix.speakers.flatMap((s) => topics.map((t) => data.matrix.cells[s]?.[t] ?? 0)));
  return (
    <section className="avoid-break mt-10">
      <SectionHead
        n="02"
        title="Who talked health, and about what"
        kicker="Each dot is a leader's statements on a topic, sized by count. Rows with no dots are leaders whose appearances did not touch health care."
      />
      <table className="matrix w-full border-collapse text-[11px]">
        <thead>
          <tr>
            <th className="w-[1.9in]" />
            {topics.map((t) => (
              <th key={t} className="rot h-[1.35in] px-0 align-bottom font-medium text-slate">
                <div className="mx-auto pb-1.5 text-left text-[10px] leading-none">{data.topic_labels[t]}</div>
              </th>
            ))}
            <th className="w-[0.55in] align-bottom pb-1.5 text-right text-[10px] font-semibold uppercase tracking-[0.06em] text-mute">
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {data.matrix.speakers.map((s) => {
            const sp = data.speakers.find((x) => x.key === s)!;
            return (
              <tr key={s} className="border-t border-line">
                <td className="py-1.5 pr-2">
                  <div className="flex items-center gap-2">
                    <Monogram name={sp.name} size={20} tone={sp.health_count ? "deep" : "light"} />
                    <div className="leading-tight">
                      <div className="font-semibold text-ink">{sp.name}</div>
                      <div className="text-[9.5px] text-mute">{sp.office}</div>
                    </div>
                  </div>
                </td>
                {topics.map((t) => {
                  const n = data.matrix.cells[s]?.[t] ?? 0;
                  const d = n ? 9 + (n / max) * 13 : 0;
                  return (
                    <td key={t} className="text-center align-middle">
                      {n ? (
                        <span
                          className="inline-flex items-center justify-center rounded-full bg-teal font-mono text-[8.5px] font-semibold text-white"
                          style={{ width: d, height: d }}
                        >
                          {n > 1 ? n : ""}
                        </span>
                      ) : (
                        <span className="inline-block h-[3px] w-[3px] rounded-full bg-line" />
                      )}
                    </td>
                  );
                })}
                <td className="text-right font-display text-[15px] font-bold text-deep">{sp.health_count || "–"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function WatchList({ data }: { data: ReportData }) {
  if (!data.watch_list.length) return null;
  return (
    <section className="page-break">
      <SectionHead
        n="02"
        title="Signals for hospitals"
        kicker="What these first appearances suggest MHA should watch for or prepare for, each tied to the statements behind it."
      />
      <div className="space-y-4">
        {data.watch_list.map((w, i) => (
          <div key={i} className="avoid-break grid grid-cols-[0.5in_1fr] gap-3 rounded-[10px] border border-line p-4">
            <div className="num text-[34px] font-bold text-coral">{String(i + 1).padStart(2, "0")}</div>
            <div>
              <h3 className="font-display text-[16.5px] font-bold leading-snug text-deep">{w.title}</h3>
              <p className="mt-1 text-[13px] leading-[1.55] text-slate">{w.body}</p>
              <div className="mt-2.5 space-y-1.5">
                {w.evidence.map((id) => {
                  if (id.startsWith("print:")) {
                    const p = data.print_quotes?.[id.slice(6)];
                    if (!p) return null;
                    const pq = p.excerpt
                      ? "… " + p.excerpt
                      : p.quote.length > 170 ? p.quote.slice(0, 170).replace(/\s+\S*$/, "").replace(/[,;:]$/, "") + " …" : p.quote;
                    return (
                      <div key={id} className="flex items-start gap-2 text-[11.5px] leading-snug">
                        <OutletChip q={p} />
                        <span className="text-slate">
                          <span className="font-semibold text-ink">{speakerName(data, p.speaker)}</span>
                          {p.period === "pre_election" && <span className="text-mute"> (pre-election, {p.date_pretty})</span>}
                          <span className="font-semibold text-ink">:</span> <span className="q italic">{pq}</span>
                        </span>
                      </div>
                    );
                  }
                  const f = data.findings[id];
                  if (!f) return null;
                  const q = f.quote.length > 170 ? f.quote.slice(0, 170).replace(/\s+\S*$/, "").replace(/[,;:]$/, "") + " …" : f.quote;
                  return (
                    <div key={id} className="flex items-start gap-2 text-[11.5px] leading-snug">
                      <Ts href={f.link} label={f.ts_label} external={!eventByKey(data, f.event_key)?.timestamped} />
                      <span className="text-slate">
                        <span className="font-semibold text-ink">{speakerName(data, f.speaker)}:</span>{" "}
                        <span className="q italic">{q}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Themes({ data }: { data: ReportData }) {
  return (
    <section className="page-break">
      <SectionHead
        n="03"
        title="Themes and what was said"
        kicker="Every verified health statement, grouped by topic and ordered by how directly it bears on hospitals. A statement tagged with several topics appears under the first."
      />
      {(() => {
        const shown = new Set<string>();
        return data.topics.map((t) => {
          const ids = t.finding_ids.filter((id) => !shown.has(id));
          ids.forEach((id) => shown.add(id));
          if (!ids.length) return null;
          return (
            <div key={t.key} className="mb-7">
              <div className="avoid-break flex items-end justify-between gap-4 border-b-2 border-deep pb-1.5">
                <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-deep">{t.label}</h3>
                <div className="shrink-0 text-[11px] text-mute">
                  {t.count} {t.count === 1 ? "statement" : "statements"} &middot;{" "}
                  {t.speakers.map((k) => speakerName(data, k)).join(", ")}
                </div>
              </div>
              {t.synthesis && <p className="mt-2 mb-1 text-[13px] leading-snug text-slate">{t.synthesis}</p>}
              {ids.map((id) => (
                <FindingCard key={id} f={data.findings[id]} data={data} />
              ))}
            </div>
          );
        });
      })()}
      {(() => {
        const printHealth = Object.values(data.print_quotes ?? {}).filter((q) => q.health);
        if (!printHealth.length) return null;
        return (
          <div className="mb-7">
            {/* Heading, intro, and first quote travel together so the heading is never stranded. */}
            <div className="avoid-break">
              <div className="flex items-end justify-between gap-4 border-b-2 border-amber pb-1.5">
                <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-deep">Reported in print</h3>
                <div className="shrink-0 text-[11px] text-mute">leaders with no video found &middot; not in the counts above</div>
              </div>
              <p className="mt-2 mb-1 text-[13px] leading-snug text-slate">
                Health remarks by leaders whose speeches were not posted on video, as quoted by news outlets and checked
                against the article. Follow the outlet link for the source.
              </p>
              <PrintCard q={printHealth[0]} data={data} />
            </div>
            {printHealth.slice(1).map((q) => (
              <PrintCard key={q.id} q={q} data={data} />
            ))}
          </div>
        );
      })()}
    </section>
  );
}

function Profiles({ data }: { data: ReportData }) {
  return (
    <section className="page-break">
      <SectionHead
        n="04"
        title="Leader profiles"
        kicker="Each leader's stated agenda in these appearances (any policy area) next to what they said about health. Timestamps open the video at that moment."
      />
      {data.speakers.map((s) => {
        const evs = s.events.map((k) => eventByKey(data, k)!).filter(Boolean);
        return (
          <article key={s.key} className="mb-6 rounded-[10px] border border-line">
            <header className="avoid-break flex items-center gap-3 rounded-t-[10px] bg-wash px-4 py-3">
              <Monogram name={s.name} size={38} />
              <div className="min-w-0 flex-1">
                <h3 className="font-display text-[18px] font-bold leading-tight text-deep">{s.name}</h3>
                <div className="text-[11.5px] text-mute">
                  {s.office} &middot; {s.detail}
                </div>
              </div>
              <div className="text-right">
                <div className="num text-[30px] font-bold text-teal">{s.health_count}</div>
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-mute">health statements</div>
              </div>
            </header>
            <div className="px-4 pb-4 pt-3">
              {s.takeaway && <p className="avoid-break text-[13px] font-medium leading-snug text-ink">{s.takeaway}</p>}
              <div className="mt-3 grid grid-cols-2 gap-6">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal">Stated priorities</div>
                  <ul className="mt-1.5">
                    {s.priorities.length === 0 && <li className="text-[12px] text-mute">None stated.</li>}
                    {s.priorities.map((p, i) => (
                      <li key={i} className="avoid-break flex items-start justify-between gap-2 border-b border-line py-1.5 text-[12px]">
                        <span className="font-medium text-ink">{p.label}</span>
                        <Ts href={p.link} label={p.ts_label} external={!eventByKey(data, p.event_key)?.timestamped} />
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal">On health care</div>
                  <ul className="mt-1.5">
                    {s.finding_ids.length === 0 && (
                      <li className="text-[12px] leading-snug text-mute">
                        Did not address health care in the appearances reviewed.
                      </li>
                    )}
                    {s.finding_ids.map((id) => {
                      const f = data.findings[id];
                      return (
                        <li key={id} className="avoid-break flex items-start justify-between gap-2 border-b border-line py-1.5 text-[12px] leading-snug">
                          <span className="text-slate">
                            {f.hospital_relevance === "high" && <span className="mr-1 inline-block h-[7px] w-[7px] rounded-full bg-coral align-middle" />}
                            {f.context}
                          </span>
                          <Ts href={f.link} label={f.ts_label} external={!eventByKey(data, f.event_key)?.timestamped} />
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-mute">
                {evs.map((e) => (
                  <a key={e.event_key} href={e.url} className="link-u">
                    {e.label} ({e.duration_label}) ↗
                  </a>
                ))}
              </div>
            </div>
          </article>
        );
      })}
      {(data.print_speakers ?? []).map((s) => (
        <article key={s.key} className="mb-6 rounded-[10px] border border-dashed border-amber/60">
          <header className="avoid-break flex items-center gap-3 rounded-t-[10px] bg-amber-soft/60 px-4 py-3">
            <Monogram name={s.name} size={38} tone="light" />
            <div className="min-w-0 flex-1">
              <h3 className="font-display text-[18px] font-bold leading-tight text-deep">{s.name}</h3>
              <div className="text-[11.5px] text-mute">
                {s.office} &middot; {s.detail}
              </div>
            </div>
            <div className="text-right">
              <Badge tone="amber">Print coverage only</Badge>
              <div className="mt-1 text-[9.5px] uppercase tracking-[0.08em] text-mute">no video found</div>
            </div>
          </header>
          <div className="px-4 pb-2 pt-3">
            {s.takeaway && <p className="avoid-break text-[13px] font-medium leading-snug text-ink">{s.takeaway}</p>}
            {(s.print_ids ?? []).map((id) => {
              const q = data.print_quotes[id];
              return q ? <PrintCard key={id} q={q} data={data} showSpeaker={false} /> : null;
            })}
          </div>
        </article>
      ))}
      <p className="text-[10.5px] text-mute">
        <span className="mr-1 inline-block h-[7px] w-[7px] rounded-full bg-coral align-middle" />
        marks statements with direct hospital stakes. Dashed cards are leaders known only from news quotes.
      </p>
    </section>
  );
}

function Sources({ data }: { data: ReportData }) {
  return (
    <section className="page-break">
      <SectionHead
        n="A"
        title="Source videos"
        kicker="One recording per event was transcribed (the most complete available). Other uploads of the same event are counted under Alt."
      />
      <table className="src-table w-full border-collapse text-[10.5px] leading-snug">
        <thead>
          <tr className="border-b-2 border-deep text-left text-[9.5px] uppercase tracking-[0.07em] text-mute">
            <th>Date</th>
            <th>Event</th>
            <th>Speakers</th>
            <th>Length</th>
            <th>Recording</th>
            <th className="text-right">Health</th>
            <th className="text-right">Alt</th>
          </tr>
        </thead>
        <tbody>
          {data.events.map((e) => (
            <tr key={e.event_key} className="avoid-break">
              <td className="whitespace-nowrap font-mono text-[10px]">{shortDate(e.event_date)}</td>
              <td>
                <a href={e.url} className="font-semibold text-ink">
                  {e.label}
                </a>
                <div className="text-mute">{e.kind_label}</div>
              </td>
              <td className="text-slate">{e.speakers.map((k) => speakerName(data, k)).join(", ")}</td>
              <td className="whitespace-nowrap font-mono text-[10px]">{e.duration_label}</td>
              <td>
                <a href={e.url} className="link-u">
                  {(e.channel || "video").split("|")[0].trim()} ↗
                </a>
                <div className="text-mute">
                  {e.transcript_source?.startsWith("openai") || e.transcript_source === "whisper" ? "Whisper transcript" : "Captions"}
                  {e.completeness !== "full" && <> &middot; {e.completeness}</>}
                </div>
              </td>
              <td className="text-right font-display text-[13px] font-bold text-deep">{e.health_count}</td>
              <td className="text-right text-mute">{e.alternates.length || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {(data.coverage.not_found.length > 0 || data.coverage.failed.length > 0) && (
        <div className="avoid-break mt-6 rounded-[8px] bg-wash p-4 text-[11.5px] leading-snug text-slate">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal">Searched for, not found</div>
          {data.coverage.not_found.length > 0 && (
            <p className="mt-1.5">
              No qualifying post-election video was found for:{" "}
              {data.coverage.not_found.map((s) => `${s.name} (${s.office})`).join("; ")}. Their remarks may exist only
              as print quotes or in live broadcasts not posted separately. Print quotes for several of them are
              collected in the Election-Fallout research notes (github.com/AndySwirczek/Election-Fallout). Rerunning
              the pipeline picks up any videos posted later.
              {(data.print_speakers ?? []).length > 0 && (
                <>
                  {" "}
                  {data.print_speakers.map((s) => s.name).join(" and ")} also had no video; their news-reported quotes
                  appear in the leader profiles.
                </>
              )}
            </p>
          )}
          {data.coverage.failed.length > 0 && (
            <p className="mt-1.5">
              Found but not yet transcribed: {data.coverage.failed.map((f) => f.label).join("; ")}.
            </p>
          )}
        </div>
      )}

      <div className="avoid-break mt-7 grid grid-cols-[1.3in_1fr] gap-4 border-t border-line pt-4 text-[11px] leading-[1.55] text-slate">
        <div className="font-display text-[13px] font-bold text-deep">Methodology</div>
        <p>{data.methodology}</p>
        <div className="font-display text-[13px] font-bold text-deep">Note</div>
        <p>{data.disclaimer}</p>
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-2 text-[10px] text-mute">
        <Badge tone="coral">Direct hospital stakes</Badge>
        <Badge tone="amber">Health system</Badge>
        <Badge tone="gray">Rhetorical</Badge>
        <span>relevance of each statement to hospitals, as classified by the analysis</span>
      </div>
    </section>
  );
}

export function Report({ data }: { data: ReportData }) {
  return (
    <main className="report font-body text-ink">
      <Cover data={data} />
      <div className="sheet">
        <Summary data={data} />
        <WatchList data={data} />
        <Themes data={data} />
        <Profiles data={data} />
        <Sources data={data} />
      </div>
    </main>
  );
}
