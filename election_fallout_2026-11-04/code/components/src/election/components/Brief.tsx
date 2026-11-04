/**
 * Short (2-3 page) version of the election-fallout report for org leaders.
 * Same data and styles as Report.tsx: header, executive summary, signals for hospitals
 * (one supporting quote each), and a one-row-per-leader table.
 */
import type { ReportData, Speaker, StatKey } from "../types";
import { shortDate } from "../types";
import { Badge, Monogram, OutletChip, SectionHead, Tokenized, Ts, eventByKey, speakerName } from "./bits";

const BRIEF_STATS: StatKey[] = ["events", "minutes", "health_findings", "high_relevance"];

function clip(s: string, n = 190): string {
  return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "").replace(/[,;:]$/, "") + " …" : s;
}

function Header({ data }: { data: ReportData }) {
  const a = shortDate(data.period_start);
  const b = shortDate(data.period_end);
  return (
    <header className="avoid-break relative overflow-hidden rounded-[12px] bg-deep px-7 pb-6 pt-5 text-white">
      <div className="cover-grid" />
      <div className="relative">
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.18em] text-mint">
          <span>MHA Advocacy Briefing &middot; Short version</span>
          <span>
            {a} – {b}, {data.period_end.slice(0, 4)}
          </span>
        </div>
        <div className="mt-4 h-[4px] w-[0.7in] bg-coral" />
        <h1 className="font-display mt-3 text-[30px] font-extrabold leading-[1.02] tracking-[-0.03em]">
          What Michigan&rsquo;s new majority said about health care
        </h1>
        <p className="mt-2 max-w-[6in] text-[12.5px] leading-[1.45] text-white/80">
          The key points from election-night speeches and first interviews. Full quotes, themes and leader
          profiles are in the 20-page report.
        </p>
        <div className="mt-4 grid grid-cols-4 gap-px overflow-hidden rounded-[8px] bg-white/15">
          {BRIEF_STATS.map((k) => (
            <div key={k} className="bg-deep/90 px-3 pb-2.5 pt-2">
              <div className={"num text-[28px] font-bold " + (k === "high_relevance" ? "text-[#ff9d7e]" : "text-white")}>
                {data.stats[k].toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] leading-snug text-white/70">{data.stat_labels[k]}</div>
            </div>
          ))}
        </div>
      </div>
    </header>
  );
}

function BottomLine({ data }: { data: ReportData }) {
  const paras = data.executive_summary.split(/\n\s*\n/).filter(Boolean);
  return (
    <section className="mt-7">
      <SectionHead n="01" title="The bottom line" />
      <div className="space-y-3 text-[12.5px] leading-[1.58] text-slate">
        {paras.map((p, i) => (
          <p key={i}>
            <Tokenized text={p} stats={data.stats} />
          </p>
        ))}
      </div>
    </section>
  );
}

function Signals({ data }: { data: ReportData }) {
  if (!data.watch_list.length) return null;
  return (
    <section className="mt-7">
      <SectionHead n="02" title="Signals for hospitals" kicker="What MHA should watch for or prepare for, with one statement behind each." />
      <div className="space-y-3">
        {data.watch_list.map((w, i) => {
          const id = w.evidence[0];
          const f = id && !id.startsWith("print:") ? data.findings[id] : undefined;
          const p = id?.startsWith("print:") ? data.print_quotes?.[id.slice(6)] : undefined;
          return (
            <div key={i} className="avoid-break grid grid-cols-[0.42in_1fr] gap-2.5 rounded-[10px] border border-line px-3.5 py-3">
              <div className="num text-[26px] font-bold text-coral">{String(i + 1).padStart(2, "0")}</div>
              <div>
                <h3 className="font-display text-[14.5px] font-bold leading-snug text-deep">{w.title}</h3>
                <p className="mt-0.5 text-[12px] leading-[1.5] text-slate">{w.body}</p>
                {f && (
                  <div className="mt-1.5 flex items-start gap-2 text-[11px] leading-snug">
                    <Ts href={f.link} label={f.ts_label} external={!eventByKey(data, f.event_key)?.timestamped} />
                    <span className="text-slate">
                      <span className="font-semibold text-ink">{speakerName(data, f.speaker)}:</span>{" "}
                      <span className="q italic">{clip(f.quote)}</span>
                    </span>
                  </div>
                )}
                {p && (
                  <div className="mt-1.5 flex items-start gap-2 text-[11px] leading-snug">
                    <OutletChip q={p} />
                    <span className="text-slate">
                      <span className="font-semibold text-ink">{speakerName(data, p.speaker)}:</span>{" "}
                      <span className="q italic">{clip(p.excerpt ?? p.quote)}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LeaderRow({ s, printOnly }: { s: Speaker; printOnly?: boolean }) {
  return (
    <tr className="avoid-break border-t border-line align-top">
      <td className="py-2 pr-3">
        <div className="flex items-center gap-2">
          <Monogram name={s.name} size={24} tone={s.health_count || (printOnly && s.print_health) ? "deep" : "light"} />
          <div className="leading-tight">
            <div className="text-[12px] font-semibold text-ink">{s.name}</div>
            <div className="text-[10px] text-mute">{s.office}</div>
          </div>
        </div>
      </td>
      <td className="py-2 pr-3 text-center">
        {printOnly ? (
          <Badge tone="amber">News quote</Badge>
        ) : (
          <>
            <div className="font-display text-[17px] font-bold text-deep">{s.health_count || "–"}</div>
            {s.high_count > 0 && <div className="text-[9.5px] text-coral">{s.high_count} high stakes</div>}
          </>
        )}
      </td>
      <td className="py-2 text-[11.5px] leading-snug text-slate">{s.takeaway}</td>
    </tr>
  );
}

function WhoSaidWhat({ data }: { data: ReportData }) {
  const speakers = [...data.speakers].sort((a, b) => b.health_count - a.health_count);
  return (
    <section className="mt-7">
      <SectionHead n="03" title="Who said what" kicker="Health statements per leader across the appearances reviewed." />
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-left text-[9.5px] font-semibold uppercase tracking-[0.1em] text-mute">
            <th className="w-[2in] pb-1.5">Leader</th>
            <th className="w-[0.85in] pb-1.5 text-center">Health statements</th>
            <th className="pb-1.5">Takeaway</th>
          </tr>
        </thead>
        <tbody>
          {speakers.map((s) => (
            <LeaderRow key={s.key} s={s} />
          ))}
          {(data.print_speakers ?? []).map((s) => (
            <LeaderRow key={s.key} s={s} printOnly />
          ))}
        </tbody>
      </table>
      {data.coverage.not_found.length > 0 && (
        <p className="mt-3 text-[10.5px] leading-snug text-mute">
          <span className="font-semibold text-slate">No post-election video found for: </span>
          {data.coverage.not_found.map((s) => s.name).join(", ")}.
        </p>
      )}
      <p className="mt-4 border-t border-line pt-3 text-[10px] leading-snug text-mute">{data.disclaimer}</p>
    </section>
  );
}

export function Brief({ data }: { data: ReportData }) {
  return (
    <main className="report brief font-body text-ink">
      <div className="sheet">
        <Header data={data} />
        <BottomLine data={data} />
        <Signals data={data} />
        <WhoSaidWhat data={data} />
      </div>
    </main>
  );
}
