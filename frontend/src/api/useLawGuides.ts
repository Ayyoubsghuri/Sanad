import { useEffect, useState } from "react";
import { API_URL, getToken } from "./legalrag";
import type { ConcordanceRule } from "../types/agent";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal, headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as T;
}
async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST", signal, body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as T;
}

// ------------------------------------------------------------------ situation navigator
export const SITUATION_TO_BACKEND: Record<string, string> = {
  "sit-unpaid-wages": "unpaid_wages",
  "sit-rental-eviction": "rent",
  "sit-divorce-nafaka": "divorce",
  "sit-cheque-unpaid": "bounced_cheque",
};

export interface NavArticle {
  id: string;
  law: string;
  article: string;
  text: string;
  valid_from: string;
  in_force_on_as_of?: boolean;
  trust?: string;
  bo?: { number?: string | null; date?: string | null };
}

export function useNavigatorArticles(situationId: string | undefined, asOf: string, enabled: boolean) {
  const [articles, setArticles] = useState<NavArticle[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const backendId = situationId ? SITUATION_TO_BACKEND[situationId] : undefined;
  useEffect(() => {
    setArticles(null);
    setError(null);
    if (!enabled || !backendId) return;
    const ctl = new AbortController();
    get<{ articles: NavArticle[] }>(`/v1/navigator/${backendId}?as_of=${asOf}&lang=fr`, ctl.signal)
      .then((r) => setArticles(r.articles))
      .catch((e) => { if ((e as Error).name !== "AbortError") setError("Serveur local indisponible."); });
    return () => ctl.abort();
  }, [backendId, asOf, enabled]);
  return { articles, error, supported: !!backendId };
}

// ------------------------------------------------------------------ concordance + transitional rules
export interface TransitionalHit {
  instrument_id: string;
  title: string;
  rules: { note: string; date_comparison?: string; cutoff_date?: string; applies_when: string }[];
}

interface WizardOut {
  transitional_rules: { note: string; date_comparison?: string; cutoff_date?: string; applies_when: string }[];
}
interface Inst { instrument_id: string; title_fr?: string | null; title_ar?: string | null; effective_date?: string | null }
interface ConcRow { old_provision_id: string; new_provision_id: string; note: string; old_instrument: string; new_instrument: string; old_number: string; new_number: string; source: string }

export function useConcordance(enabled: boolean) {
  const [rules, setRules] = useState<ConcordanceRule[]>([]);
  useEffect(() => {
    if (!enabled) return;
    const ctl = new AbortController();
    (async () => {
      try {
        const [insts, conc] = await Promise.all([
          get<Inst[]>("/v1/instruments", ctl.signal),
          get<{ rows: ConcRow[] }>("/v1/concordance", ctl.signal),
        ]);
        const by = new Map(insts.map((i) => [i.instrument_id, i]));
        setRules(
          conc.rows.map((r, n) => ({
            id: `pack-conc-${n}`,
            topic: `[Pack, ${r.source}] ${r.note}`,
            oldLaw: by.get(r.old_instrument)?.title_fr || r.old_instrument,
            oldArticle: `Art. ${r.old_number}`,
            newLaw: by.get(r.new_instrument)?.title_fr || r.new_instrument,
            newArticle: `Art. ${r.new_number}`,
            effectiveDate: by.get(r.new_instrument)?.effective_date || "",
            transitionalRuleText: "",
            oldSummary: r.old_provision_id,
            newSummary: r.new_provision_id,
            keyChange: r.note,
          }))
        );
      } catch { /* offline: static rules only */ }
    })();
    return () => ctl.abort();
  }, [enabled]);
  return rules;
}

export function useTransitionalRules(filingDate: string, enabled: boolean) {
  const [hits, setHits] = useState<TransitionalHit[] | null>(null);
  useEffect(() => {
    setHits(null);
    if (!enabled) return;
    const ctl = new AbortController();
    (async () => {
      try {
        const insts = await get<Inst[]>("/v1/instruments", ctl.signal);
        const out: TransitionalHit[] = [];
        await Promise.all(
          insts.slice(0, 40).map(async (i) => {
            const w = await post<WizardOut>("/v1/wizard/which-rules-apply", { instrument_id: i.instrument_id, filing_date: filingDate, judgment_date: filingDate }, ctl.signal);
            if (w.transitional_rules?.length) out.push({ instrument_id: i.instrument_id, title: i.title_fr || i.title_ar || i.instrument_id, rules: w.transitional_rules });
          })
        );
        setHits(out);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setHits(null);
      }
    })();
    return () => ctl.abort();
  }, [filingDate, enabled]);
  return hits;
}
