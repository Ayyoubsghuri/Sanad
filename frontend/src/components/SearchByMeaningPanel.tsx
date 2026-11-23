import React, { useEffect, useState } from "react";
import { Check, Cloud, Cpu, ExternalLink, Loader2 } from "lucide-react";
import { tr } from "../i18n";
import { ComputeState, InstallJob, cancelInstall, getCompute, installJob, installModels, setCompute, testCompute } from "../api/compute";

const field = "w-full px-3 py-2 rounded-lg border text-sm outline-none";
const fstyle = { backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" } as const;

/** In the API keys window: how Sanad searches by meaning (local models or Cloudflare Workers AI), and the Cloudflare account. */
export function SearchByMeaningPanel({ onChanged }: { onChanged?: (s: ComputeState) => void }) {
  const [st, setSt] = useState<ComputeState | null>(null);
  const [account, setAccount] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [job, setJob] = useState<InstallJob | null>(null);
  const apply = (s: ComputeState) => { setSt(s); setAccount(s.cloudflare_account); onChanged?.(s); if (s.install) setJob(s.install); };
  useEffect(() => { getCompute().then(apply).catch(() => undefined); }, []);
  const installing = !!job && (job.state === "queued" || job.state === "running");
  useEffect(() => {   // follow a model download until it ends
    if (!installing) return;
    const t = setInterval(() => {
      installJob().then((j) => {
        setJob(j);
        if (j.state !== "running" && j.state !== "queued") getCompute().then(apply).catch(() => undefined);
      }).catch(() => undefined);
    }, 1500);
    return () => clearInterval(t);
  }, [installing]);
  if (!st) return null;
  const install = (what: "small" | "full") => run("install", async () => setJob(await installModels(what)));

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
              : st.low_ram ? tr("Not available: they need 16 GB of memory.") : tr("Not installed yet: about 5 GB to download.")}
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
      {(installing || (job && job.state !== "done" && job.state !== "idle")) && (
        <div className="rounded-lg border p-3 space-y-1.5 text-xs" style={{ borderColor: "var(--border-subtle)", color: "var(--text-heading)" }}>
          <div className="flex items-center gap-2">
            {installing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            <span className="font-medium flex-1">
              {installing ? tr(job?.step === "libraries" ? "Installing the libraries…" : "Downloading the model…")
                : job?.state === "cancelled" ? tr("Stopped: click Install again to continue.") : tr("The download did not finish.")}
            </span>
            {installing && <button type="button" onClick={() => cancelInstall().then(() => installJob().then(setJob))} className="px-2 py-0.5 rounded border cursor-pointer" style={{ borderColor: "var(--border-strong)" }}>{tr("Stop")}</button>}
          </div>
          {job?.detail && <div className="font-code text-[10px] truncate" style={{ color: "var(--text-muted)" }} dir="ltr">{job.detail}</div>}
          {job?.error && <div className="text-[11px]" style={{ color: "#c0392b" }}>{job.error}</div>}
        </div>
      )}
      {!st.local_models_installed && !st.low_ram && !installing && (
        <button type="button" onClick={() => install("full")} disabled={busy !== null || st.offline}
          className="px-3 py-1.5 rounded-lg border text-xs cursor-pointer disabled:opacity-50" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
          {tr("Install the models on this computer (about 5 GB)")}
        </button>
      )}
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
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
            <span>{st.small_reranker_installed ? tr("Sorting the results: a small model on this computer (works offline).") : tr("Sorting the results: by keywords.")}</span>
            {!st.small_reranker_installed && !installing && (
              <button type="button" onClick={() => install("small")} disabled={busy !== null || st.offline}
                className="px-2.5 py-1 rounded-lg border cursor-pointer disabled:opacity-50" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
                {tr("Install the small model (about 1 GB)")}
              </button>
            )}
          </div>
        </div>
      )}
      {msg && <p className="text-xs" style={{ color: msg.ok ? "var(--accent-primary)" : "#c0392b" }}>{msg.text}</p>}
    </div>
  );
}
