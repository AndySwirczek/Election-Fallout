export type StatKey =
  | "events"
  | "speakers"
  | "minutes"
  | "health_findings"
  | "speakers_on_health"
  | "high_relevance";

export type Relevance = "high" | "medium" | "low";

export interface Finding {
  id: string;
  speaker: string;
  event_key: string;
  event_date: string;
  event_label: string;
  timestamp: string;
  ts_label: string;
  seconds: number;
  link: string;
  quote: string;
  topics: string[];
  type: "commitment" | "policy" | "criticism" | "framing" | "personal_story";
  hospital_relevance: Relevance;
  context: string;
  why_it_matters: string;
}

export interface Priority {
  label: string;
  quote: string;
  timestamp: string;
  ts_label: string;
  link: string;
  event_key: string;
}

export interface EventRow {
  event_key: string;
  label: string;
  event_date: string;
  event_date_pretty: string;
  kind: string;
  kind_label: string;
  speakers: string[];
  url: string;
  title: string;
  channel: string;
  duration: number;
  duration_label: string;
  completeness: string;
  transcript_source: string;
  alternates: { id: string; url: string; channel: string; title: string; duration: number; completeness: string }[];
  headline: string;
  health_summary: string;
  health_count: number;
  timestamped: boolean;
}

export interface Speaker {
  key: string;
  name: string;
  office: string;
  detail: string;
  events: string[];
  health_count: number;
  high_count: number;
  topics: string[];
  finding_ids: string[];
  priorities: Priority[];
  takeaway: string;
  print_ids?: string[];
  print_only?: boolean;
  print_health?: number;
}

export interface PrintQuote {
  id: string;
  speaker: string;
  period: "election_night" | "pre_election";
  setting: string;
  date: string;
  date_pretty: string;
  quote: string;
  excerpt?: string;
  outlet: string;
  author?: string;
  headline?: string;
  url: string;
  variant?: string;
  health: boolean;
  type?: Finding["type"];
  hospital_relevance?: Relevance;
  context: string;
  why_it_matters?: string;
}

export interface Topic {
  key: string;
  label: string;
  count: number;
  speakers: string[];
  synthesis: string;
  finding_ids: string[];
}

export interface WatchItem {
  title: string;
  body: string;
  evidence: string[];
}

export interface ReportData {
  generated: string;
  generated_pretty: string;
  election_label: string;
  period_start: string;
  period_end: string;
  stats: Record<StatKey, number>;
  stat_labels: Record<StatKey, string>;
  topic_labels: Record<string, string>;
  events: EventRow[];
  speakers: Speaker[];
  print_speakers: Speaker[];
  print_quotes: Record<string, PrintQuote>;
  topics: Topic[];
  matrix: { speakers: string[]; topics: string[]; cells: Record<string, Record<string, number>> };
  findings: Record<string, Finding>;
  executive_summary: string;
  watch_list: WatchItem[];
  coverage: {
    not_found: { key: string; name: string; office: string }[];
    failed: { label: string; url: string; status?: string; error?: string }[];
  };
  methodology: string;
  disclaimer: string;
}

export const TYPE_LABELS: Record<Finding["type"], string> = {
  commitment: "Commitment",
  policy: "Policy",
  criticism: "Criticism",
  framing: "Framing",
  personal_story: "Personal story",
};

export const REL_LABELS: Record<Relevance, string> = {
  high: "Direct hospital stakes",
  medium: "Health system",
  low: "Rhetorical",
};

export function initials(name: string): string {
  const parts = name.replace(/[^A-Za-z\s-]/g, "").split(/[\s-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function shortDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
