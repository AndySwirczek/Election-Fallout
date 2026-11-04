import type { ReactNode } from "react";
import type { EventRow, Finding, PrintQuote, ReportData, Speaker, StatKey } from "../types";
import { REL_LABELS, TYPE_LABELS, initials, shortDate } from "../types";

export function SectionHead({ n, title, kicker, id }: { n: string; title: string; kicker?: string; id?: string }) {
  return (
    <header id={id} className="avoid-break mb-5">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[11px] font-semibold tracking-[0.12em] text-teal">{n}</span>
        <span className="h-px flex-1 bg-line" />
      </div>
      <h2 className="font-display mt-2 text-[27px] font-bold leading-[1.08] tracking-[-0.02em] text-deep">{title}</h2>
      {kicker && <p className="mt-1.5 max-w-[6.4in] text-[13px] leading-snug text-mute">{kicker}</p>}
    </header>
  );
}

export function Monogram({ name, size = 30, tone = "deep" }: { name: string; size?: number; tone?: "deep" | "light" }) {
  const cls = tone === "deep" ? "bg-deep text-mint" : "bg-teal-soft text-teal";
  return (
    <span
      className={"font-display inline-flex shrink-0 items-center justify-center rounded-full font-bold " + cls}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
    >
      {initials(name)}
    </span>
  );
}

export function Ts({ href, label, external }: { href: string; label: string; external?: boolean }) {
  return (
    <a href={href} className="ts" title={external ? "Open the video page; jump to this time" : "Play from this moment"}>
      {label}
    </a>
  );
}

export function Badge({ children, tone }: { children: ReactNode; tone: "coral" | "amber" | "teal" | "gray" }) {
  const cls = {
    coral: "bg-coral-soft text-coral",
    amber: "bg-amber-soft text-amber",
    teal: "bg-teal-soft text-teal",
    gray: "bg-wash text-slate",
  }[tone];
  return (
    <span className={"inline-block rounded-[4px] px-1.5 py-[1.5px] text-[9.5px] font-semibold uppercase tracking-[0.07em] " + cls}>
      {children}
    </span>
  );
}

export function RelBadge({ rel }: { rel: Finding["hospital_relevance"] }) {
  return <Badge tone={rel === "high" ? "coral" : rel === "medium" ? "amber" : "gray"}>{REL_LABELS[rel]}</Badge>;
}

/** Replace {{stat}} tokens with bold numbers. */
export function Tokenized({ text, stats }: { text: string; stats: ReportData["stats"] }) {
  const parts = text.split(/(\{\{[a-z_]+\}\})/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\{\{([a-z_]+)\}\}$/);
        if (m && m[1] in stats) {
          return (
            <strong key={i} className="font-semibold text-deep">
              {stats[m[1] as StatKey]}
            </strong>
          );
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

export function FindingCard({
  f,
  data,
  showSpeaker = true,
}: {
  f: Finding;
  data: ReportData;
  showSpeaker?: boolean;
}) {
  const sp = data.speakers.find((s) => s.key === f.speaker);
  const ev = data.events.find((e) => e.event_key === f.event_key);
  return (
    <article className="avoid-break flex gap-3 border-t border-line py-3.5">
      {showSpeaker && sp && <Monogram name={sp.name} size={30} />}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
          {showSpeaker && sp && (
            <>
              <span className="font-display font-bold text-ink">{sp.name}</span>
              <span className="text-mute">{sp.office}</span>
            </>
          )}
          <span className="ml-auto flex gap-1">
            <RelBadge rel={f.hospital_relevance} />
            <Badge tone="teal">{TYPE_LABELS[f.type]}</Badge>
          </span>
        </div>
        <p className="q mt-1 text-[15px] leading-[1.5] text-ink">{f.quote}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-mute">
          <Ts href={f.link} label={f.ts_label} external={!ev?.timestamped} />
          <span>
            {ev?.label ?? f.event_label} &middot; {shortDate(f.event_date)}
            {!ev?.timestamped && " · seek to this time on the video page"}
          </span>
        </div>
        {f.why_it_matters && (
          <p className="mt-2 border-l-2 border-teal pl-2.5 text-[12px] leading-snug text-slate">
            <span className="font-semibold text-teal">For hospitals: </span>
            {f.why_it_matters}
          </p>
        )}
      </div>
    </article>
  );
}

export function speakerName(data: ReportData, key: string): string {
  return [...data.speakers, ...(data.print_speakers ?? [])].find((s: Speaker) => s.key === key)?.name ?? key;
}

export function allSpeakers(data: ReportData): Speaker[] {
  return [...data.speakers, ...(data.print_speakers ?? [])];
}

/** Outlet chip: the print counterpart of the timestamp chip. */
export function OutletChip({ q }: { q: PrintQuote }) {
  return (
    <a
      href={q.url}
      className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-amber-soft px-2 py-[2px] text-[10.5px] font-semibold text-amber"
      title={q.headline}
    >
      ¶ {q.outlet}
    </a>
  );
}

export function PrintCard({ q, data, showSpeaker = true }: { q: PrintQuote; data: ReportData; showSpeaker?: boolean }) {
  const sp = allSpeakers(data).find((s) => s.key === q.speaker);
  return (
    <article className="avoid-break flex gap-3 border-t border-line py-3.5">
      {showSpeaker && sp && <Monogram name={sp.name} size={30} tone="light" />}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
          {showSpeaker && sp && (
            <>
              <span className="font-display font-bold text-ink">{sp.name}</span>
              <span className="text-mute">{sp.office}</span>
            </>
          )}
          <span className="ml-auto flex gap-1">
            {q.period === "pre_election" ? <Badge tone="gray">Pre-election record</Badge> : <Badge tone="amber">Election night &middot; print</Badge>}
            {q.hospital_relevance && <RelBadge rel={q.hospital_relevance} />}
          </span>
        </div>
        <p className="q mt-1 text-[15px] leading-[1.5] text-ink">{q.quote}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-mute">
          <OutletChip q={q} />
          <span>{q.setting}</span>
        </div>
        {q.variant && <p className="mt-1 text-[11px] italic leading-snug text-mute">{q.variant}</p>}
        {q.why_it_matters && (
          <p className="mt-2 border-l-2 border-teal pl-2.5 text-[12px] leading-snug text-slate">
            <span className="font-semibold text-teal">For hospitals: </span>
            {q.why_it_matters}
          </p>
        )}
      </div>
    </article>
  );
}

export function eventByKey(data: ReportData, key: string): EventRow | undefined {
  return data.events.find((e) => e.event_key === key);
}
