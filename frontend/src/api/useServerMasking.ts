import { useEffect, useState } from "react";
import { deleteCase, getVaultReveal, previewPseudonymise } from "./legalrag";
import type { PseudonymMapping } from "../types/agent";

export interface MaskEntry {
  placeholder: string;
  kind: string;
  original: string;
  category: PseudonymMapping["category"];
}

export interface ServerMasking {
  masked: string | null; // null until the backend answered (or when it is unreachable)
  entries: MaskEntry[];
  confidence: number | null;
  warnings: string[];
  error: string | null;
  loading: boolean;
}

export function kindToCategory(kind: string): PseudonymMapping["category"] {
  if (kind === "PERSON") return "person";
  if (kind === "ORG") return "org";
  if (kind === "PHONE" || kind === "EMAIL" || kind === "ADDRESS") return "contact";
  if (kind === "RIB") return "financial";
  return "secret";
}

/** Rules the user saved (active ones) are forwarded to the backend, which masks them with its own placeholders. */
export function rulesToTerms(mappings: PseudonymMapping[]): string[] {
  return mappings.filter((m) => m.active && m.original.trim().length >= 2).map((m) => m.original.trim());
}

/**
 * ONE masking engine: the local backend. Same detectors (rules + Arabic NER + your saved rules) as when the question is sent,
 * so the preview, the sandbox and the real send always agree.
 */
export function useServerMasking(text: string, extraTerms: string[], enabled: boolean): ServerMasking {
  const [state, setState] = useState<ServerMasking>({ masked: null, entries: [], confidence: null, warnings: [], error: null, loading: false });
  const termsKey = JSON.stringify(extraTerms);
  useEffect(() => {
    if (!enabled || !text.trim()) {
      setState({ masked: null, entries: [], confidence: null, warnings: [], error: null, loading: false });
      return;
    }
    const ctl = new AbortController();
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(async () => {
      try {
        const p = await previewPseudonymise(text, extraTerms, ctl.signal);
        const v = await getVaultReveal(p.case_id, ctl.signal);
        deleteCase(p.case_id).catch(() => {}); // the preview case is throw-away: do not keep originals around
        setState({
          masked: p.text,
          entries: v.entries.map((e) => ({ ...e, category: kindToCategory(e.kind) })),
          confidence: p.confidence,
          warnings: p.warnings,
          error: null,
          loading: false,
        });
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setState({ masked: null, entries: [], confidence: null, warnings: [], error: (e as Error).message, loading: false });
      }
    }, 300);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, termsKey, enabled]);
  return state;
}

/** Turns backend detections into saved rules (skips originals that already have a rule). */
export function entriesToMappings(entries: MaskEntry[], existing: PseudonymMapping[]): PseudonymMapping[] {
  const have = new Set(existing.map((m) => m.original.trim().toLowerCase()));
  const out: PseudonymMapping[] = [];
  for (const e of entries) {
    const key = e.original.trim().toLowerCase();
    if (!key || have.has(key)) continue;
    have.add(key);
    out.push({
      id: `map-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      original: e.original.trim(),
      replacement: e.placeholder,
      category: e.category,
      detectedAt: `Detected ${new Date().toLocaleTimeString()}`,
      active: true,
    });
  }
  return out;
}
