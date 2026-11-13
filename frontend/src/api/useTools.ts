// Client for the backend tools (see TOOLS_API.md): old->new article finder, article history, contract checker, calculator basis, guides.
import { call, ApiError } from "./legalrag";

export interface DiffSeg { op: "equal" | "insert" | "delete"; text: string }
export interface ToolArticle {
  provision_id: string; instrument_id?: string; number: string; text: string; valid_from?: string | null; valid_to?: string | null;
  trust?: string; law?: string | null; why?: string; path?: string | null;
}
export interface FinderMatch extends ToolArticle { score: number; vector_similarity: number; word_overlap: number; same_number: boolean }
export interface FinderResult {
  label: "derived"; confidence: "high" | "medium" | "low"; note: string; method: string;
  old: ToolArticle & { label: string };
  target: { instrument_id: string; title_ar?: string | null; title_fr?: string | null; same_law_new_edition: boolean };
  matches: FinderMatch[]; diff_with_best: DiffSeg[];
}
export interface HistoryPeriod {
  valid_from: string; valid_to: string | null; text: string; trust: string; in_force_on_date: boolean;
  amended_by: { instrument_id: string; number?: string | null; bo_number?: string | null } | null;
  sources: { instrument_id: string; edition: string }[];
  diff_from_previous: DiffSeg[] | null; change_summary: { words_added: number; words_removed: number } | null;
}
export interface HistoryResult {
  article: { instrument_id: string; provision_id: string; label: string }; family: string[]; as_of: string; periods: HistoryPeriod[]; changes: number;
  in_force: number | null; ended_on?: string; note: string;
  continued_in?: { confidence: string; target: string; matches: { provision_id: string; number: string; score: number; text: string }[] };
}
export interface ContractFinding {
  clause: number; verdict: "conflicts" | "check" | "consistent"; why: string; quote: string; provision_id: string; law: string; article: string; trust: string; valid_from: string;
}
export interface ContractResult {
  status: "checked" | "retrieved_only"; note?: string; notice: string; as_of: string;
  clauses: { n: number; title: string; text: string; passages: string[] }[];
  passages: Record<string, { law: string; article: string; text: string; provision_id: string; trust: string }>;
  cited_in_document: { reference: string; provision_id: string | null; in_force_on_date: boolean; text: string | null; note: string | null }[];
  findings: ContractFinding[]; findings_dropped_unverified?: number; summary?: Record<string, number>;
}
export interface GuideResult {
  topic: string; status: "generated" | "articles_only"; note?: string; cached: boolean; notice: string;
  articles: { id: string; provision_id: string; law: string; article: string; text: string; valid_from: string; trust?: string }[];
  steps: { title: string; text: string; articles: { id: string; provision_id: string; law: string; article: string }[] }[];
}

const qs = (o: Record<string, string | number | undefined>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");

export const findNewArticle = (p: { ref: string; asOf?: string; target?: string }, s?: AbortSignal) =>
  call<FinderResult>(`/v1/tools/concordance?${qs({ ref: p.ref, as_of: p.asOf, target: p.target, k: 5 })}`, {}, s);
export const articleHistory = (p: { ref: string; asOf?: string }, s?: AbortSignal) =>
  call<HistoryResult>(`/v1/tools/history?${qs({ ref: p.ref, as_of: p.asOf })}`, {}, s);
export const checkContract = (p: { text?: string; docId?: string; asOf?: string; lang: string }, s?: AbortSignal) =>
  call<ContractResult>("/v1/tools/contract-check", { method: "POST", body: JSON.stringify({ text: p.text, doc_id: p.docId, as_of: p.asOf, lang: p.lang }) }, s);
export const makeGuide = (p: { situation?: string; topic?: string; asOf?: string; lang: string }, s?: AbortSignal) =>
  call<GuideResult>("/v1/tools/guides", { method: "POST", body: JSON.stringify({ situation: p.situation, topic: p.topic, as_of: p.asOf, lang: p.lang }) }, s);

/** Readable message from a backend error (`detail: {code, message}`), else the plain message. */
export function toolError(e: unknown): string {
  if (e instanceof ApiError) {
    const d = (e.body as { detail?: { code?: string; message?: string } | string } | null)?.detail;
    if (d && typeof d === "object" && d.message) return d.message;
    if (typeof d === "string") return d;
  }
  return (e as Error)?.message || String(e);
}
