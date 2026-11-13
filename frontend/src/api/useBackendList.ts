import { useEffect, useState } from "react";
import { API_URL, getToken } from "./legalrag";

/** GET a list/object once when `enabled` turns true. `error` is a short human message (never throws). */
export function useBackendGet<T>(path: string, enabled: boolean): { data: T | null; error: string | null } {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    if (!enabled) return;
    const ctl = new AbortController();
    fetch(`${API_URL}${path}`, { signal: ctl.signal, headers: { Authorization: `Bearer ${getToken()}` } })
      .then(async (r) => {
        if (!r.ok) {
          let detail = "";
          try {
            const b = await r.json();
            detail = typeof b?.detail === "string" ? b.detail : b?.detail?.reason || "";
          } catch { /* ignore */ }
          throw new Error(detail || `Backend error ${r.status}`);
        }
        return (await r.json()) as T;
      })
      .then((data) => setState({ data, error: null }))
      .catch((e) => {
        if ((e as Error).name !== "AbortError") setState({ data: null, error: (e as Error).message });
      });
    return () => ctl.abort();
  }, [path, enabled]);
  return state;
}
