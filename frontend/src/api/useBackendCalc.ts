import { useEffect, useState } from "react";
import { runCalc, ApiError, type CalcResult } from "./legalrag";

export interface BackendCalc {
  data: CalcResult | null;
  error: string | null;
  loading: boolean;
}

/** Debounced call to POST /v1/calculators/run. `inputs = null` disables it. */
export function useBackendCalc(tool: string, inputs: Record<string, unknown> | null, active: boolean): BackendCalc {
  const [state, setState] = useState<BackendCalc>({ data: null, error: null, loading: false });
  const key = JSON.stringify(inputs);
  useEffect(() => {
    if (!active || !inputs) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    const ctl = new AbortController();
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(() => {
      runCalc(tool, inputs, ctl.signal)
        .then((data) => setState({ data, error: null, loading: false }))
        .catch((e) => {
          if ((e as Error).name === "AbortError") return;
          const body = e instanceof ApiError ? (e.body as { detail?: { message?: string } } | null) : null;
          setState({ data: null, error: body?.detail?.message || (e as Error).message, loading: false });
        });
    }, 300);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool, key, active]);
  return state;
}
