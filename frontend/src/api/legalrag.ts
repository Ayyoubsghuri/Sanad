// Client for the local LegalRAG FastAPI backend (see legalrag-backend/README.md).
// Pairing is automatic (POST /pair). Optional overrides via Vite env vars (e.g. in .env.local):
//   VITE_LEGALRAG_URL=http://127.0.0.1:8765
//   VITE_LEGALRAG_TOKEN=<token printed by `legalrag` on startup>
// The token can also be set at runtime: localStorage.setItem("legalrag_token", "...")

const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};

export const API_URL = (env.VITE_LEGALRAG_URL || "http://127.0.0.1:8765").replace(/\/$/, "");

export function getToken(): string {
  try {
    return localStorage.getItem("legalrag_token") || env.VITE_LEGALRAG_TOKEN || memToken;
  } catch {
    return env.VITE_LEGALRAG_TOKEN || memToken;
  }
}

// ---- automatic pairing --------------------------------------------------------------------------
// The user never copies a token. If none is stored, the app asks the local backend for it (POST /pair, which the backend only
// answers to local origins). Every request to the backend goes through this wrapper: it attaches the token, pairs when needed
// and re-pairs once if the backend answers 401 (e.g. the data folder was reset and a new token was generated).
let pairing: Promise<string> | null = null;

function storeToken(t: string): void {
  try {
    localStorage.setItem("legalrag_token", t);
  } catch {
    /* private mode: kept in memory only */
  }
  memToken = t;
}
let memToken = "";

async function pair(): Promise<string> {
  if (!pairing) {
    pairing = nativeFetch(`${API_URL}/pair`, { method: "POST", headers: { "X-LegalRAG-Pair": "1" } })
      .then(async (r) => {
        if (!r.ok) throw new Error(`pairing refused (${r.status})`);
        const t = ((await r.json()) as { token?: string }).token || "";
        if (t) storeToken(t);
        return t;
      })
      .finally(() => {
        pairing = null;
      });
  }
  return pairing;
}

const nativeFetch: typeof fetch = typeof window !== "undefined" ? window.fetch.bind(window) : (undefined as unknown as typeof fetch);

if (typeof window !== "undefined" && !(window as unknown as { __legalragFetch?: boolean }).__legalragFetch) {
  (window as unknown as { __legalragFetch?: boolean }).__legalragFetch = true;
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const ours = url.startsWith(API_URL) && !/\/(pair|health)(\?|$)/.test(url);
    if (!ours) return nativeFetch(input, init);
    const send = (tok: string) => {
      const h = new Headers(init?.headers);
      if (tok) h.set("Authorization", `Bearer ${tok}`);
      return nativeFetch(input, { ...init, headers: h });
    };
    let tok = getToken();
    if (!tok) {
      try {
        tok = await pair();
      } catch {
        /* backend down: let the normal request fail with its own error */
      }
    }
    let res = await send(tok);
    if (res.status === 401) {
      try {
        const fresh = await pair();
        if (fresh && fresh !== tok) res = await send(fresh);
      } catch {
        /* keep the 401 */
      }
    }
    return res;
  };
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
  }
}

export async function call<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    signal,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    const b = body as { detail?: unknown; message?: string; code?: string } | null;
    const detail =
      typeof b?.detail === "string"
        ? b.detail
        : (b?.detail as { reason?: string } | undefined)?.reason || b?.message || b?.code;
    const msg =
      res.status === 401
        ? "Backend rejected the API token and automatic pairing failed. Restart the backend and reload the page."
        : `Backend error ${res.status}${detail ? `: ${detail}` : ""}`;
    throw new ApiError(res.status, body, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- types (subset of the backend responses) ---------------------------------------------------
export interface PreparedQuery {
  query_id: string;
  case_id: string;
  mode: string;
  pseudonymised_text: string;
  confidence: number;
  warnings: string[];
  requires_review: boolean;
  requires_approval: boolean;
  planned_outbound_calls: unknown;
}

export interface SourceEntry {
  id: string;
  law: string;
  article: string;
  path?: string;
  text: string;
  title_ar?: string;
  title_fr?: string;
  bo?: { number?: string | null; date?: string | null };
  valid_from: string;
  valid_to?: string | null;
  in_force_on_as_of?: boolean;
  trust?: string;
  trust_note?: string;
  contested?: boolean;
  status_note?: string | null;
  source?: { url?: string } | string | null;
  other_language?: { lang: string; text: string } | null;
  provision_id?: string;
  chunk_id?: number;
  /** "article" = a whole article; "other_text" = a preamble / annex / table passage shown with its own text */
  kind?: "article" | "other_text";
  /** the retrieval chunk that matched (`text` is always the whole article) */
  chunk_text?: string;
  pages?: { start: number; end: number } | null;
  has_pdf?: boolean;
  relevance?: number;
}

export interface AnswerClaim {
  type?: string;
  text: string;
  sources: string[];
  calculators: string[];
  verified: boolean;
}

export interface AnswerRuling {
  ruling_id: string;
  number?: string | null;
  date?: string | null;
  file_number?: string | null;
  chamber?: string | null;
  outcome?: string | null;
  outcome_ar?: string | null;
  keywords?: string | null;
  principle?: string | null;
  source_url?: string | null;
}
export interface AnswerRulings {
  similar: number;
  by_outcome: Record<string, number>;
  items: AnswerRuling[];
}

export interface NextStep {
  title: string;
  text: string;
  deadline?: string;
  where?: string;
  documents?: string[];
  sources?: string[];
}
export interface NextSteps {
  steps: NextStep[];
  professional?: string;
}

export interface WebResults {
  query?: string;
  results?: { title: string; url: string; site: string; snippet: string }[];
  skipped?: string;
  error?: string;
}

export interface QueryAnswer {
  web?: WebResults | null;
  rulings?: AnswerRulings | null;
  next_steps?: NextSteps | null;
  status:
    | "answered" | "partial" | "extractive_only" | "abstained" | "needs_clarification"
    | "needs_input" | "review_required" | "unavailable" | "payload_preview" | "cancelled";
  query_id?: string;
  language?: string;
  as_of?: string;
  as_of_assumption?: string;
  mode?: string;
  notices?: string[];
  assumptions?: string[];
  claims?: AnswerClaim[];
  sources?: SourceEntry[];
  calculators?: { id?: string; tool: string; status: string; message?: string; [k: string]: unknown }[];
  clarifying_question?: string;
  needs_input?: { tool: string; message: string; missing: string[] };
  abstain?: { reason: string; bring_to_professional?: string[] };
  reason?: string;
  pseudonymised_text?: string;
  verification?: Record<string, unknown>;
  steps?: ProgressStep[];
  research?: { depth: string; rounds: { round: number; verdict?: string; missing?: string; queries?: string[]; added?: number[]; error?: string }[] };
  fallbacks?: string[];
  could_not_verify?: boolean;
  trace_id?: string;
}

export interface BackendStatus {
  mode: string;
  pack: { loaded: boolean; usable?: boolean; version?: string; stale?: boolean; error?: string | null };
}

// ---- endpoints ----------------------------------------------------------------------------------
export const health = () => fetch(`${API_URL}/health`).then((r) => r.json());
export const getStatus = () => call<BackendStatus>("/v1/status");

/** An earlier message of the same chat; the backend uses it to understand follow-ups ("and the next article?"). */
export interface HistoryTurn {
  role: "user" | "assistant";
  text: string;
  cited?: string[];
}

export const prepareQuery = (
  body: { question: string; as_of?: string | null; case_id?: string | null; extra_sensitive_terms?: string[]; document_ids?: string[]; history?: HistoryTurn[]; session_id?: string; new_topic?: boolean; mask?: boolean },
  signal?: AbortSignal
) => call<PreparedQuery>("/v1/queries", { method: "POST", body: JSON.stringify(body) }, signal);

export const runQuery = (
  id: string,
  body: { approved?: boolean; edited_text?: string; review_confirmed?: boolean; depth?: "normal" | "deep" | "max"; web?: boolean } = {},
  signal?: AbortSignal
) => call<QueryAnswer>(`/v1/queries/${id}/run`, { method: "POST", body: JSON.stringify(body) }, signal);

export interface ProgressStep { id: string; kind: string; title: string; detail: string; status: "running" | "done"; duration_ms: number | null }
export const getProgress = (id: string, signal?: AbortSignal) => call<{ steps: ProgressStep[]; done: boolean }>(`/v1/queries/${id}/progress`, {}, signal);

export const cancelQuery = (id: string) => call(`/v1/queries/${id}/cancel`, { method: "POST" });

export const patchSettings = (body: Record<string, unknown>) =>
  call("/v1/settings", { method: "PATCH", body: JSON.stringify(body) });

export const searchLaw = (query: string, asOf?: string) =>
  call("/v1/search", { method: "POST", body: JSON.stringify({ query, as_of: asOf || null }) });

export const runCalculator = (tool: string, inputs: Record<string, unknown>) =>
  call("/v1/calculators/run", { method: "POST", body: JSON.stringify({ tool, inputs }) });

export const listCalculators = () => call("/v1/calculators");
export const listInstruments = () => call("/v1/instruments");
export const getTrace = (id: string) => call(`/v1/traces/${id}`);

// ---- mapping to frontend settings -----------------------------------------------------------------
export const toBackendMode = (m: string) => (m === "cloud-assisted" ? "hybrid" : m.replace("-", "_")); // cloud-assisted mode is disabled

export interface CalcResult {
  tool: string;
  result: Record<string, unknown>;
  formula: string;
  legal_basis: string[];
  steps: string[];
  warnings: string[];
  verification: string;
  as_of?: string;
  table_rows: Record<string, unknown>[];
}
export const runCalc = (tool: string, inputs: Record<string, unknown>, signal?: AbortSignal) =>
  call<CalcResult>("/v1/calculators/run", { method: "POST", body: JSON.stringify({ tool, inputs }) }, signal);

export interface TraceDetail {
  trace_id: string;
  status: string;
  pseudonymised_question?: string | null;
  as_of?: string | null;
  mode?: string | null;
  model?: string | null;
  provider?: string | null;
  pack_version?: string | null;
  prompt_version?: string | null;
  retrieved?: { chunk_id: number | string; provision_id: string; valid_from: string; trust: string; score: number }[];
  checks?: { checks?: Record<string, unknown>; claims_total?: number; claims_passed?: number; failures?: string[]; unanswered_sub_questions?: number[] } | null;
  claims?: unknown[] | null;
  elapsed_ms?: number;
}
export const listTraces = (limit = 30) => call<{ trace_id: string; created_at: string; status: string }[]>(`/v1/traces?limit=${limit}`);
export const getTraceDetail = (id: string) => call<TraceDetail>(`/v1/traces/${id}`);
export const clearHistory = () => call("/v1/history", { method: "DELETE" });
export const createErrorReport = (body: { trace_id?: string | null; what_is_wrong: string; correct_source: string }) =>
  call<{ report_id: string }>("/v1/error-reports", { method: "POST", body: JSON.stringify(body) });

export interface PseudoPreview {
  case_id: string;
  text: string;
  confidence: number;
  warnings: string[];
  entity_counts: Record<string, number>;
}
export const previewPseudonymise = (text: string, extraTerms: string[] = [], signal?: AbortSignal) =>
  call<PseudoPreview>(
    "/v1/pseudonymise/preview",
    { method: "POST", body: JSON.stringify({ text, extra_sensitive_terms: extraTerms }) },
    signal
  );
export const getVaultReveal = (caseId: string, signal?: AbortSignal) =>
  call<{ entries: { placeholder: string; kind: string; original: string }[] }>(
    `/v1/cases/${caseId}/vault?reveal=true`,
    {},
    signal
  );
export const deleteCase = (caseId: string) => call(`/v1/cases/${caseId}`, { method: "DELETE" });

/** One page of the official PDF as an object URL (the image route needs the token, so a plain <img src> cannot be used). */
export async function fetchPageImageUrl(provisionId: string, page: number, asOf?: string, signal?: AbortSignal): Promise<string> {
  const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
  const res = await fetch(`${API_URL}/v1/provisions/${encodeURIComponent(provisionId)}/page/${page}${q}`, { signal, headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, null, `page image ${res.status}`);
  return URL.createObjectURL(await res.blob());
}
