/**
 * Short version of the election-fallout report for org leaders, in two parts:
 *   Part 1: key post-election themes across lawmakers, with verbatim examples.
 *   Part 2: health care focus (summary, per-leader table, trimmed quotes).
 * Reports only what was said: no recommendations, relevance ratings or analysis.
 *
 * Text comes from data/brief.json (attached as data.brief by render.tsx --brief). Every quote
 * fragment in it was checked verbatim against data.json or the cited article.
 */
import type { ReportData, StatKey } from "../types";
import { shortDate } from "../types";
import { Badge, Monogram, SectionHead, Tokenized, Ts, eventByKey, speakerName } from "./bits";

/** A verbatim quote (fragments joined with " … "), from video (ts) or a news outlet. */
export interface BriefQuote {
  speaker: string;
  text: string;
  link: string;
  ts?: string;
  event?: string;
  outlet?: string;
}
export interface BriefTheme {
  title: string;
  summary: string;
  leaders: string[];
  examples: BriefQuote[];
}
export interface BriefContent {
  summary: string[];
  speakers: Record<string, string>;
  themes: BriefTheme[];
  quotes: BriefQuote[];
  names?: Record<string, string>;
  extra_speakers?: { key: string; name: string; office: string; source: string; said: string }[];
  silent?: { name: string; office: string; headline: string; facts: string[]; note?: string; sources: { label: string; url: string }[] };
}
export type BriefData = ReportData & { brief: BriefContent };

const BRIEF_STATS: StatKey[] = ["events", "speakers", "minutes", "health_findings"];

const nameOf = (data: BriefData, key: string) => data.brief.names?.[key] ?? speakerName(data, key);

function PartBand({ n, title, kicker }: { n: string; title: string; kicker: string }) {
  return (
    <div className="avoid-break mb-5 flex items-baseline gap-3 rounded-[8px] bg-wash px-4 py-2.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-coral">Part {n}</span>
      <span className="font-display text-[15px] font-bold text-deep">{title}</span>
      <span className="ml-auto text-[10.5px] text-mute">{kicker}</span>
    </div>
  );
}

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
          What Michigan&rsquo;s new majority said after the election
        </h1>
        <p className="mt-2 max-w-[6.2in] text-[12.5px] leading-[1.45] text-white/80">
          Part 1 covers the main themes across lawmakers&rsquo; election-night speeches and first interviews.
          Part 2 focuses on what they said about health care. Quotes are verbatim; the full 20-page report has
          every statement and transcript.
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

function SourceChip({ q, data }: { q: BriefQuote; data: BriefData }) {
  if (q.ts) {
    const ev = q.event ? eventByKey(data, q.event) : undefined;
    return <Ts href={q.link} label={q.ts} external={!ev?.timestamped} />;
  }
  return (
    <a href={q.link} className="inline-flex shrink-0 items-center whitespace-nowrap rounded-full bg-amber-soft px-2 py-[2px] text-[10px] font-semibold text-amber">
      ¶ {q.outlet}
    </a>
  );
}

function QuoteLine({ q, data }: { q: BriefQuote; data: BriefData }) {
  const name = nameOf(data, q.speaker);
  return (
    <div className="avoid-break flex items-start gap-2 text-[11.5px] leading-snug">
      <SourceChip q={q} data={data} />
      <span className="text-slate">
        <span className="font-semibold text-ink">{name}</span>
        <span className="font-semibold text-ink">:</span> <span className="q italic">{q.text}</span>
      </span>
    </div>
  );
}

function Themes({ data }: { data: BriefData }) {
  return (
    <section className="mt-6">
      <PartBand n="1" title="Post-election themes" kicker="Across all lawmakers reviewed" />
      <SectionHead n="01" title="Key themes across lawmakers" kicker="What came up across speeches and interviews, with examples in their own words." />
      <div className="space-y-3">
        {data.brief.themes.map((t, i) => (
          <div key={i} className="avoid-break rounded-[10px] border border-line px-4 py-3">
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="font-display text-[14.5px] font-bold leading-snug text-deep">{t.title}</h3>
              <span className="shrink-0 text-[10px] text-mute">{t.leaders.map((k) => nameOf(data, k).split(" ").slice(-1)[0]).join(" · ")}</span>
            </div>
            <p className="mt-0.5 text-[12px] leading-[1.5] text-slate">{t.summary}</p>
            <div className="mt-2 space-y-1.5">
              {t.examples.map((q, j) => (
                <QuoteLine key={j} q={q} data={data} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Silent({ data }: { data: BriefData }) {
  const h = data.brief.silent;
  if (!h) return null;
  return (
    <section className="avoid-break mt-8">
      <div className="rounded-[10px] border border-line bg-wash px-4 py-3.5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-coral">One more thing</div>
        <div className="mt-1.5 flex items-center gap-3">
          <Monogram name={h.name} size={30} tone="light" />
          <div>
            <h3 className="font-display text-[15px] font-bold leading-snug text-deep">{h.headline}</h3>
            <div className="text-[11px] text-mute">{h.office}</div>
          </div>
        </div>
        <div className="mt-2 space-y-1 text-[12px] leading-[1.5] text-slate">
          {h.facts.map((f, i) => (
            <p key={i}>{f}</p>
          ))}
        </div>
      </div>
    </section>
  );
}

function HealthSummary({ data }: { data: BriefData }) {
  return (
    <section className="page-break">
      <PartBand n="2" title="Health care focus" kicker="What was said about health care" />
      <SectionHead n="02" title="Summary of what was said on health care" />
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

function Row({ name, office, count, badge, said, active, quotes = [], data }: {
  name: string; office: string; count?: number; badge?: string; said: string; active: boolean;
  quotes?: BriefQuote[]; data: BriefData;
}) {
  return (
    <tr className="avoid-break border-t border-line align-top">
      <td className="py-1.5 pr-3">
        <div className="flex items-center gap-2">
          <Monogram name={name} size={24} tone={active ? "deep" : "light"} />
          <div className="leading-tight">
            <div className="text-[12px] font-semibold text-ink">{name}</div>
            <div className="text-[10px] text-mute">{office}</div>
          </div>
        </div>
      </td>
      <td className="py-1.5 pr-3 text-center">
        {badge ? <Badge tone={badge === "No statement" ? "coral" : "amber"}>{badge}</Badge> : <div className="font-display text-[17px] font-bold text-deep">{count || "–"}</div>}
      </td>
      <td className="py-1.5 text-[11.5px] leading-snug text-slate">
        <div>{said}</div>
        {quotes.length > 0 && (
          <div className="mt-1 space-y-0.5">
            {quotes.map((q, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px] leading-snug">
                <SourceChip q={q} data={data} />
                <span className="q italic text-slate">{q.text}</span>
              </div>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

function Leaders({ data }: { data: BriefData }) {
  const speakers = [...data.speakers].sort((a, b) => b.health_count - a.health_count);
  const said = (k: string, fallback: string) => data.brief.speakers[k] ?? fallback;
  const quotesOf = (k: string) => data.brief.quotes.filter((q) => q.speaker === k);
  return (
    <section className="page-break">
      <SectionHead n="03" title="What each leader said on health care" kicker="Health statements on video, Nov. 3–4, with key lines in their own words." />
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
            <Row key={s.key} name={s.name} office={s.office} count={s.health_count} said={said(s.key, s.takeaway)} active={s.health_count > 0} quotes={quotesOf(s.key)} data={data} />
          ))}
          {(data.print_speakers ?? []).map((s) => (
            <Row key={s.key} name={s.name} office={s.office} badge="News quote" said={said(s.key, s.takeaway)} active={(s.print_health ?? 0) > 0} quotes={quotesOf(s.key)} data={data} />
          ))}
          {(data.brief.extra_speakers ?? []).map((s) => (
            <Row key={s.key} name={s.name} office={s.office} badge={s.source} said={s.said} active={false} data={data} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Footer({ data }: { data: BriefData }) {
  return (
    <footer className="avoid-break">
      {data.coverage.not_found.length > 0 && (
        <p className="mt-4 text-[10.5px] leading-snug text-mute">
          <span className="font-semibold text-slate">No post-election video found for: </span>
          {data.coverage.not_found.map((s) => s.name).join(", ")}.
        </p>
      )}
      <p className="mt-4 border-t border-line pt-3 text-[10px] leading-snug text-mute">{data.disclaimer}</p>
    </footer>
  );
}

export function Brief({ data }: { data: BriefData }) {
  return (
    <main className="report brief font-body text-ink">
      <div className="sheet">
        <Header data={data} />
        <Themes data={data} />
        <HealthSummary data={data} />
        <Leaders data={data} />
        <Silent data={data} />
        <Footer data={data} />
      </div>
    </main>
  );
}
