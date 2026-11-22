import React, { useEffect, useState } from "react";
import { Check, Cloud, Cpu, ExternalLink, Loader2 } from "lucide-react";
import { tr } from "../i18n";
import { ComputeState, getCompute, setCompute, testCompute } from "../api/compute";

const field = "w-full px-3 py-2 rounded-lg border text-sm outline-none";
const fstyle = { backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" } as const;

/** In the API keys window: how Sanad searches by meaning (local models or Cloudflare Workers AI), and the Cloudflare account. */
export function SearchByMeaningPanel({ onChanged }: { onChanged?: (s: ComputeState) => void }) {
  const [st, setSt] = useState<ComputeState | null>(null);
  const [account, setAccount] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const apply = (s: ComputeState) => { setSt(s); setAccount(s.cloudflare_account); onChanged?.(s); };
  useEffect(() => { getCompute().then(apply).catch(() => undefined); }, []);
  if (!st) return null;

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setMsg(null);
    try { await fn(); } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }); } finally { setBusy(null); }
  };
  const save = () => run("save", async () => {
    apply(await setCompute({ account: account.trim(), ...(token.trim() ? { token: token.trim() } : {}) }));
    setToken("");
    setMsg({ ok: true, text: tr("Saved.") });
  });
  const test = () => run("test", async () => {
    const r = await testCompute();
    setMsg(r.ok ? { ok: true, text: tr("Cloudflare answered: search by meaning works.") } : { ok: false, text: r.error || "error" });
  });
  const choose = (source: "local" | "cloudflare") => run("source", async () => apply(await setCompute({ source })));

  const cf = st.source === "cloudflare";
  const opt = (active: boolean, disabled: boolean) => ({
    borderColor: active ? "var(--accent-primary)" : "var(--border-subtle)", backgroundColor: active ? "var(--bg-card)" : "transparent",
    color: "var(--text-heading)", opacity: disabled ? 0.5 : 1,
  });
  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: "var(--border-subtle)" }}>
      <div>
        <div className="text-sm font-medium" style={{ color: "var(--text-heading)" }}>{tr("Search by meaning")}</div>
        <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {tr("Finds the articles that match the meaning of your question, not only its words.")}
          {st.ram_gb ? " " + tr("This computer has {0} GB of memory.", [st.ram_gb]) : ""}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <button type="button" disabled={!st.local_models_installed || busy !== null} onClick={() => choose("local")}
          className="text-start rounded-lg border p-3 cursor-pointer disabled:cursor-not-allowed" style={opt(!cf, !st.local_models_installed)}>
          <div className="flex items-center gap-2 text-sm font-medium">{!cf ? <Check className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}{tr("Models on this computer")}</div>
          <div className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
            {st.local_models_installed ? tr("Works offline; needs 16 GB of memory.")
              : tr("Not installed. To install them, start «Sanad - repair setup» from the Start menu and choose «Install the models» (16 GB of memory needed).")}
          </div>
        </button>
        <button type="button" disabled={busy !== null} onClick={() => choose("cloudflare")}
          className="text-start rounded-lg border p-3 cursor-pointer" style={opt(cf, false)}>
          <div className="flex items-center gap-2 text-sm font-medium">{cf ? <Check className="w-4 h-4" /> : <Cloud className="w-4 h-4" />}{tr("Cloudflare Workers AI")}{st.low_ram ? ` · ${tr("recommended")}` : ""}</div>
          <div className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
            {tr("No models on the computer. The masked search text is sent to Cloudflare; Offline mode uses keyword search only.")}
          </div>
        </button>
      </div>
      {cf && (
        <div className="space-y-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="text-xs space-y-1" style={{ color: "var(--text-muted)" }}>
              {tr("Account ID")}
              <input className={field + " font-code"} style={fstyle} value={account} onChange={(e) => setAccount(e.target.value)} placeholder="0123456789abcdef…" maxLength={64} dir="ltr" />
            </label>
            <label className="text-xs space-y-1" style={{ color: "var(--text-muted)" }}>
              {tr("API token (Workers AI permission)")}
              <input className={field + " font-code"} style={fstyle} type="password" value={token} onChange={(e) => setToken(e.target.value)}
                placeholder={st.cloudflare_token_saved ? tr("saved (leave empty to keep it)") : "…"} dir="ltr" autoComplete="off" />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={save} disabled={busy !== null} className="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer inline-flex items-center gap-1.5"
              style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" }}>
              {busy === "save" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}{tr("Save")}
            </button>
            <button type="button" onClick={test} disabled={busy !== null || !st.cloudflare_ready || st.offline} className="px-3 py-1.5 rounded-lg border text-xs cursor-pointer inline-flex items-center gap-1.5 disabled:opacity-50"
              style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
              {busy === "test" ? <Loader2 className="w-3 h-3 animate-spin" /> : null}{tr("Test")}
            </button>
            <a href="https://dash.cloudflare.com/?to=/:account/ai/workers-ai" target="_blank" rel="noreferrer" className="text-xs underline inline-flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
              {tr("Get the ID and token")}<ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://developers.cloudflare.com/workers-ai/platform/pricing/" target="_blank" rel="noreferrer" className="text-xs underline inline-flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
              {tr("Prices and free allowance")}<ExternalLink className="w-3 h-3" />
            </a>
          </div>
          {st.offline && <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Offline mode: nothing is sent to Cloudflare, Sanad searches by keywords.")}</p>}
        </div>
      )}
      {msg && <p className="text-xs" style={{ color: msg.ok ? "var(--accent-primary)" : "#c0392b" }}>{msg.text}</p>}
    </div>
  );
}
