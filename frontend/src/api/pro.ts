import { call } from "./legalrag";

export type L3 = { en: string; fr: string; ar: string };
export interface ProField {
  id: string;
  kind: "textarea" | "text" | "choice";
  required?: boolean;
  label: L3;
  placeholder?: L3;
  options?: { id: string; label: L3 }[];
}
export interface ProTool {
  id: string;
  group: string;
  kind: "courtroom" | "report" | "finder";
  icon: string;
  label: L3;
  description: L3;
  fields: ProField[];
  sections: string[];
  uses_rulings: boolean;
  featured: boolean;
}
export interface ProCatalog {
  groups: { id: string; label: L3 }[];
  tools: ProTool[];
  rulings_available: boolean;
}
export interface ProStep {
  id: string;
  label: L3;
  status: "running" | "done" | "failed";
  ms?: number;
}
export interface ArticleSource {
  id: string;
  law: string;
  article: string;
  text: string;
  valid_from?: string | null;
  valid_to?: string | null;
  in_force_on_as_of?: boolean;
  provision_id: string;
}
export interface RulingCard {
  id: string;
  ruling_id: string;
  number: string;
  date: string;
  file_number: string;
  chamber: string;
  case_type?: string | null;
  outcome: string;
  outcome_ar: string;
  petitioner_won: boolean | null;
  keywords: string;
  principle: string;
  facts: string;
  grounds: { ground: string; answer: string; accepted: boolean | null }[];
  verdict: string;
  ocr: boolean;
  source_url?: string | null;
}
export interface Cited {
  sources: string[];
  unsourced?: boolean;
}
export interface ReportItem extends Cited {
  text: string;
  tag?: string;
}
export interface ReportOutput {
  title: string;
  summary: string;
  sections: { heading: string; items: ReportItem[] }[];
  missing_information?: string[];
}
export interface Argument extends Cited {
  title: string;
  argument: string;
  strength: "strong" | "medium" | "weak";
}
export interface CourtroomOutput {
  side: "claimant" | "defendant";
  lawyer_a: { position: string; arguments: Argument[]; evidence_needed?: string[] };
  lawyer_b: {
    position: string;
    rebuttals: ({ target: number; rebuttal: string } & Cited)[];
    counter_arguments: Argument[];
  };
  judge: {
    issues: ({ issue: string; finding: string; favours: "A" | "B" | "uncertain" } & Cited)[];
    verdict: string;
    chance_of_success: number;
    confidence: "low" | "medium" | "high";
    chance_reasoning: string;
    risks: ({ risk: string } & Cited)[];
    recommendations: string[];
    what_would_change?: string[];
  };
}
export interface ProResult {
  tool: string;
  kind: ProTool["kind"];
  as_of: string;
  issues: string[];
  case_summary: string;
  articles: ArticleSource[];
  rulings: RulingCard[];
  similar_outcomes: Record<string, number>;
  rulings_db: number;
  warnings: string[];
  status: "sources_only" | "generated";
  output: ReportOutput | CourtroomOutput | null;
  unsupported_citations?: number;
  articles_not_used?: number;
  notice: string;
}
export interface ProJob {
  job_id: string;
  tool: string;
  kind: ProTool["kind"];
  status: "preview" | "running" | "done" | "error";
  as_of: string;
  preview: { field: string; label: L3; text: string }[];
  entity_counts: Record<string, number>;
  planned_calls: number;
  model?: string | null;
  mode: string;
  phone_unmasked?: boolean;
  steps: ProStep[];
  result: ProResult | null;
  error: { code: string; message: string } | null;
}

export const proCatalog = () => call<ProCatalog>("/v1/pro/catalog");
export const prepareJob = (tool: string, fields: Record<string, string>, as_of: string, lang: string) =>
  call<ProJob>("/v1/pro/jobs", { method: "POST", body: JSON.stringify({ tool, fields, as_of, lang }) });
export const runJob = (id: string, edited?: Record<string, string>) =>
  call<ProJob>(`/v1/pro/jobs/${id}/run`, { method: "POST", body: JSON.stringify({ edited: edited || null }) });
export const getJob = (id: string, signal?: AbortSignal) => call<ProJob>(`/v1/pro/jobs/${id}`, {}, signal);
export const getRuling = (id: string) => call<RulingCard & { full_text: string }>(`/v1/pro/rulings/${encodeURIComponent(id)}`);

export interface RulingsUpdate {
  installed_version: string | null;
  published_version?: string;
  size_bytes?: number;
  rulings?: number;
  period?: { from?: string; to?: string };
  update_available?: boolean;
  problem?: string;
  error?: string;
  job: RulingsJob | null;
}
export interface RulingsJob {
  state: "idle" | "queued" | "running" | "done" | "error" | "cancelled";
  step?: string;
  progress?: number;
  done_bytes?: number;
  total_bytes?: number;
  error?: string | null;
}
export const rulingsUpdateCheck = () => call<RulingsUpdate>("/v1/pro/rulings/update");
export const rulingsUpdateStart = () => call<RulingsJob>("/v1/pro/rulings/update", { method: "POST" });
export const rulingsUpdateJob = () => call<RulingsJob>("/v1/pro/rulings/update/job");
export const rulingsUpdateCancel = () => call<{ cancelled: boolean }>("/v1/pro/rulings/update/cancel", { method: "POST" });
