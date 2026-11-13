import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, getToken } from "./legalrag";
import type { BilingualArticle, ContestedStatus, ImplementingStatus, TrustLevel } from "../types/agent";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal, headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as T;
}

interface Inst {
  instrument_id: string;
  number?: string | null;
  short_code?: string | null;
  title_ar?: string | null;
  title_fr?: string | null;
  bo_number?: string | null;
  bo_date?: string | null;
  status_flag?: string | null;
  implementation_status?: string | null;
}
interface Prov {
  provision_id: string;
  instrument_id: string;
  number: string;
  path: string;
}

const TRUST: Record<string, TrustLevel> = {
  verified: "verified",
  single_source: "single_source",
  derived: "derived",
  disputed: "disputed",
  draft: "draft",
};

export interface LawFilter {
  id: string;
  label: string;
}

/**
 * Loads instruments + provision lists from the backend (cheap metadata), and fetches the
 * bilingual text of an article lazily (loadArticle). Falls back to `fallback` when offline.
 */
export function useBackendArticles(enabled: boolean, asOf: string, fallback: BilingualArticle[]) {
  const [articles, setArticles] = useState<BilingualArticle[]>(fallback);
  const [insts, setInsts] = useState<Inst[]>([]);
  const [laws, setLaws] = useState<LawFilter[] | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loaded = useRef(new Set<string>());
  const lawLoaded = useRef(new Set<string>());
  const instsRef = useRef<Inst[]>([]);

  const toArticle = (i: Inst, pr: Prov): BilingualArticle => ({
    id: pr.provision_id,
    provisionId: pr.provision_id,
    instrumentId: i.instrument_id,
    lawNumber: i.short_code || i.number || i.instrument_id,
    lawTitle: i.title_fr || i.title_ar || i.instrument_id,
    titleAr: i.title_ar || undefined,
    articleNumber: `Art. ${pr.number}`,
    path: pr.path,
    validFrom: "",
    validTo: null,
    textAr: "",
    textFr: "",
    controllingLang: "ar",
    trustLevel: "single_source",
    dahirNumber: i.number || "",
    boNumber: i.bo_number ? `BO ${i.bo_number}` : "",
    boDate: i.bo_date || "",
    implementingStatus: (i.implementation_status as ImplementingStatus) || "unknown",
    contestedStatus: i.status_flag === "ACTIVE_CONTESTED" ? "active_contested" : "active",
  });

  // Only the list of laws is loaded up front (one request). The articles of a law are loaded when it is opened or searched.
  useEffect(() => {
    if (!enabled) return;
    const ctl = new AbortController();
    loaded.current = new Set();
    lawLoaded.current = new Set();
    (async () => {
      try {
        const list = await get<Inst[]>("/v1/instruments", ctl.signal);
        instsRef.current = list;
        setInsts(list);
        setArticles([]);
        setLaws(list.map((i) => ({ id: i.instrument_id, label: `${i.short_code || i.number || ""} ${i.title_fr || i.title_ar || ""}`.trim() || i.instrument_id })));
        setLive(true);
        setError(null);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setLive(false);
        setArticles(fallback);
        setError("Serveur local indisponible : textes de démonstration affichés.");
      }
    })();
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  /** the articles of one law (one request, cached) */
  const loadLaw = useCallback(async (instrumentId: string) => {
    if (lawLoaded.current.has(instrumentId)) return;
    const i = instsRef.current.find((x) => x.instrument_id === instrumentId);
    if (!i) return;
    lawLoaded.current.add(instrumentId);
    setBusy(true);
    try {
      const p = await get<Prov[]>(`/v1/instruments/${encodeURIComponent(instrumentId)}/provisions`);
      setArticles((prev) => {
        const have = new Set(prev.map((a) => a.id));
        return [...prev, ...p.filter((pr) => !have.has(pr.provision_id)).map((pr) => toArticle(i, pr))];
      });
    } catch {
      lawLoaded.current.delete(instrumentId);
    } finally {
      setBusy(false);
    }
  }, []);

  const loadArticle = useCallback(
    async (id: string) => {
      if (!live) return;
      const key = `${id}@${asOf}`;
      if (loaded.current.has(key)) return;
      loaded.current.add(key);
      try {
        const v = await get<{
          valid_from: string; valid_to: string | null; controlling_lang: "ar" | "fr"; verification_status: string; instrument_id: string;
          texts: Record<string, { text: string }>; source?: { url?: string } | null; status_flag?: string | null;
        }>(`/v1/provisions/${encodeURIComponent(id)}?as_of=${asOf}`);
        let transitional: string | undefined;
        let impl: ImplementingStatus | undefined;
        try {
          const card = await get<{ transitional_rules?: { note: string }[]; implementation?: { status: string } }>(
            `/v1/instruments/${encodeURIComponent(v.instrument_id)}/status?as_of=${asOf}`
          );
          transitional = card.transitional_rules?.map((r) => r.note).join("\n") || undefined;
          impl = (card.implementation?.status as ImplementingStatus) || undefined;
        } catch { /* optional */ }
        setArticles((prev) =>
          prev.map((a) =>
            a.id === id
              ? {
                  ...a,
                  validFrom: v.valid_from,
                  validTo: v.valid_to,
                  textAr: v.texts.ar?.text || "",
                  textFr: v.texts.fr?.text || "",
                  controllingLang: v.controlling_lang,
                  trustLevel: TRUST[v.verification_status] || "single_source",
                  sourceUrl: v.source?.url,
                  transitionalRule: transitional,
                  implementingStatus: impl || a.implementingStatus,
                  contestedStatus: (v.status_flag === "ACTIVE_CONTESTED" ? "active_contested" : a.contestedStatus) as ContestedStatus,
                }
              : a
          )
        );
      } catch {
        loaded.current.delete(key);
        setArticles((prev) =>
          prev.map((a) => (a.id === id ? { ...a, textFr: "Aucune version en vigueur à la date choisie dans le pack de lois.", textAr: "" } : a))
        );
      }
    },
    [live, asOf]
  );

  // a different as-of date means different text
  useEffect(() => {
    loaded.current = new Set();
  }, [asOf]);

  /** provision ids matching a free-text query (retrieval only, no LLM); the matching articles are added to the list */
  const search = useCallback(
    async (q: string, signal?: AbortSignal): Promise<Set<string>> => {
      if (!live) return new Set();
      const res = await fetch(`${API_URL}/v1/search`, {
        method: "POST", signal,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ query: q, as_of: asOf, limit: 30 }),
      });
      if (!res.ok) return new Set();
      const j = (await res.json()) as { results: { provision_id: string; instrument_id: string; article: string; path: string; kind?: string }[] };
      const rows = j.results.filter((r) => r.kind !== "other_text");
      setArticles((prev) => {
        const have = new Set(prev.map((a) => a.id));
        const add: BilingualArticle[] = [];
        for (const r of rows) {
          const i = instsRef.current.find((x) => x.instrument_id === r.instrument_id);
          if (!i || have.has(r.provision_id)) continue;
          have.add(r.provision_id);
          add.push(toArticle(i, { provision_id: r.provision_id, instrument_id: r.instrument_id, number: r.article.replace(/^\D+/, "").trim() || r.article, path: r.path }));
        }
        return add.length ? [...prev, ...add] : prev;
      });
      return new Set(rows.map((r) => r.provision_id));
    },
    [live, asOf]
  );

  return { articles, laws, live, error, busy, loadArticle, loadLaw, search };
}
