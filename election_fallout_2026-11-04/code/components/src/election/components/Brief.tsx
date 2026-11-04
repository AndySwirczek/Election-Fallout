/**
 * Short version of the election-fallout report for org leaders: what was said, and a plain
 * summary of it. No recommendations, relevance ratings or analysis.
 *
 * Text comes from data/brief.json (attached as data.brief by render.tsx --brief); quotes and
 * timestamps come from data.json.
 */
import type { ReportData, StatKey } from "../types";
import { shortDate } from "../types";
import { Badge, Monogram, OutletChip, SectionHead, Tokenized, Ts, eventByKey, speakerName } from "./bits";

export interface BriefContent {
  summary: string[];
  speakers: Record<string, string>;
  quote_ids: string[];
  extra_speakers?: { key: string; name: string; office: string; source: string; said: string }[];
}
export type BriefData = ReportData & { brief: BriefContent };

const BRIEF_STATS: StatKey[] = ["events", "minutes", "speakers_on_health", "health_findings"];

function Header({ data }: { data: BriefData }) {
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
          What the winners said in election-night speeches and first interviews, and a summary of it. The full
          20-page report has every statement and transcript.
        </p>
        <div className="mt-4 grid grid-cols-4 gap-px overflow-hidden rounded-[8px] bg-white/15">
          {BRIEF_STATS.map((k) => (
            <div key={k} className="bg-deep/90 px-3 pb-2.5 pt-2">
              <div className="num text-[28px] font-bold text-white">{data.stats[k].toLocaleString()}</div>
              <div className="mt-1 text-[10px] leading-snug text-white/70">{data.stat_labels[k]}</div>
            </div>
          ))}
        </div>
      </div>
    </header>
  );
}

function Summary({ data }: { data: BriefData }) {
  return (
    <section className="mt-7">
      <SectionHead n="01" title="Summary of what was said" />
      <div className="space-y-3 text-[12.5px] leading-[1.58] text-slate">
        {data.brief.summary.map((p, i) => (
          <p key={i}>
            <Tokenized text={p} stats={data.stats} />
          </p>
        ))}
      </div>
    </section>
  );
}

function Row({ name, office, count, badge, said, active }: {
  name: string; office: string; count?: number; badge?: string; said: string; active: boolean;
}) {
  return (
    <tr className="avoid-break border-t border-line align-top">
      <td className="py-2 pr-3">
        <div className="flex items-center gap-2">
          <Monogram name={name} size={24} tone={active ? "deep" : "light"} />
          <div className="leading-tight">
            <div className="text-[12px] font-semibold text-ink">{name}</div>
            <div className="text-[10px] text-mute">{office}</div>
          </div>
        </div>
      </td>
      <td className="py-2 pr-3 text-center">
        {badge ? <Badge tone="amber">{badge}</Badge> : <div className="font-display text-[17px] font-bold text-deep">{count || "–"}</div>}
      </td>
      <td className="py-2 text-[11.5px] leading-snug text-slate">{said}</td>
    </tr>
  );
}

function Leaders({ data }: { data: BriefData }) {
  const speakers = [...data.speakers].sort((a, b) => b.health_count - a.health_count);
  const said = (k: string, fallback: string) => data.brief.speakers[k] ?? fallback;
  return (
    <section className="mt-7">
      <SectionHead n="02" title="What each leader said" kicker="Health statements counted across each leader's appearances on video, Nov. 3–4." />
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-left text-[9.5px] font-semibold uppercase tracking-[0.1em] text-mute">
            <th className="w-[2in] pb-1.5">Leader</th>
            <th className="w-[0.85in] pb-1.5 text-center">Health statements</th>
            <th className="pb-1.5">What they said</th>
          </tr>
        </thead>
        <tbody>
          {speakers.map((s) => (
            <Row key={s.key} name={s.name} office={s.office} count={s.health_count} said={said(s.key, s.takeaway)} active={s.health_count > 0} />
          ))}
          {(data.print_speakers ?? []).map((s) => (
            <Row key={s.key} name={s.name} office={s.office} badge="News quote" said={said(s.key, s.takeaway)} active={(s.print_health ?? 0) > 0} />
          ))}
          {(data.brief.extra_speakers ?? []).map((s) => (
            <Row key={s.key} name={s.name} office={s.office} badge={s.source} said={s.said} active={false} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Quotes({ data }: { data: BriefData }) {
  return (
    <section className="mt-7">
      <SectionHead n="03" title="In their words" kicker="Selected health care statements, verbatim. Timestamps open the video at that moment." />
      <div className="space-y-2.5">
        {data.brief.quote_ids.map((id) => {
          if (id.startsWith("print:")) {
            const p = data.print_quotes?.[id.slice(6)];
            if (!p) return null;
            return (
              <div key={id} className="avoid-break flex items-start gap-2.5 border-b border-line pb-2.5 text-[12px] leading-snug">
                <OutletChip q={p} />
                <div>
                  <div className="text-[10.5px] font-semibold text-ink">
                    {speakerName(data, p.speaker)} <span className="font-normal text-mute">&middot; {p.setting}</span>
                  </div>
                  <div className="q mt-0.5 italic text-slate">{p.quote}</div>
                </div>
              </div>
            );
          }
          const f = data.findings[id];
          if (!f) return null;
          return (
            <div key={id} className="avoid-break flex items-start gap-2.5 border-b border-line pb-2.5 text-[12px] leading-snug">
              <Ts href={f.link} label={f.ts_label} external={!eventByKey(data, f.event_key)?.timestamped} />
              <div>
                <div className="text-[10.5px] font-semibold text-ink">
                  {speakerName(data, f.speaker)} <span className="font-normal text-mute">&middot; {f.event_label}</span>
                </div>
                <div className="q mt-0.5 italic text-slate">{f.quote}</div>
              </div>
            </div>
          );
        })}
      </div>
      {data.coverage.not_found.length > 0 && (
        <p className="mt-4 text-[10.5px] leading-snug text-mute">
          <span className="font-semibold text-slate">No post-election video found for: </span>
          {data.coverage.not_found.map((s) => s.name).join(", ")}.
        </p>
      )}
      <p className="mt-4 border-t border-line pt-3 text-[10px] leading-snug text-mute">{data.disclaimer}</p>
    </section>
  );
}

export function Brief({ data }: { data: BriefData }) {
  return (
    <main className="report brief font-body text-ink">
      <div className="sheet">
        <Header data={data} />
        <Summary data={data} />
        <Leaders data={data} />
        <Quotes data={data} />
      </div>
    </main>
  );
}
