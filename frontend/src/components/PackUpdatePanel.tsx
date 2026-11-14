// "Law pack" panel of the update window: shows the installed and the published law pack, and installs the published one.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Database, Download, Loader2, RefreshCw } from "lucide-react";
import { tr } from "../i18n";
import { PackCheck, PackJob, cancelPackUpdate, checkPackUpdate, getPackUpdateJob, startPackUpdate } from "../api/pack";

const gb = (n?: number) => (n ? `${(n / 1e9).toFixed(2)} GB` : "");

export function PackUpdatePanel({ onInstalled, busy }: { onInstalled?: () => void; busy?: boolean }) {
  const [check, setCheck] = useState<PackCheck | null>(null);
  const [job, setJob] = useState<PackJob | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const wasRunning = useRef(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const c = await checkPackUpdate();
      setCheck(c);
      setJob(c.job);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const running = job?.state === "running" || job?.state === "queued";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(async () => {
      try {
        setJob((await getPackUpdateJob()).job);
      } catch {
        /* the next tick retries */
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  useEffect(() => {
    if (running) wasRunning.current = true;
    else if (wasRunning.current) {
      wasRunning.current = false;
      if (job?.state === "done") onInstalled?.();
      refresh();
    }
  }, [running, job, onInstalled, refresh]);

  const start = async () => {
    setErr(null);
    try {
      setJob(await startPackUpdate());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const problems = check?.problems ?? [];
  const pct = Math.round((job?.progress ?? 0) * 100);
  const stepText: Record<PackJob["step"], string> = {
    check: tr("Reading the published pack description"),
    download: tr("Downloading the law pack"),
    verify: tr("Checking the SHA-256 and the publisher's signature"),
    install: tr("Installing the law pack"),
  };
  const upToDate = check && check.update_available === false && !running;
  const canInstall = !!check?.published_version && check.key_matches !== false && problems.length === 0 && !busy;

  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-canvas)" }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-heading)" }}>
          <Database className="w-4 h-4" style={{ color: "var(--accent-primary)" }} />
          {tr("Law pack")}
        </div>
        <button type="button" onClick={refresh} disabled={loading || running} title={tr("Check for a new law pack")}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs cursor-pointer hover:opacity-85 disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          {tr("Check")}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div style={{ color: "var(--text-muted)" }}>{tr("Installed")}</div>
          <div className="font-code mt-0.5 break-all" style={{ color: "var(--text-heading)" }}>{check?.installed_version ?? tr("none")}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>{tr("Published")}</div>
          <div className="font-code mt-0.5 break-all" style={{ color: "var(--text-heading)" }}>
            {check?.published_version ?? (loading ? "…" : "—")}
            {check?.size_bytes ? <span style={{ color: "var(--text-muted)" }}> · {gb(check.size_bytes)}</span> : null}
          </div>
        </div>
      </div>

      {problems.length > 0 && (
        <ul className="list-disc pl-5 text-xs space-y-1" style={{ color: "var(--text-muted)" }}>
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
      {check?.error && <div className="text-xs" style={{ color: "#c0392b" }}>{check.error}</div>}
      {check?.key_matches === false && (
        <div className="text-xs" style={{ color: "#c0392b" }}>{tr("The published pack is signed with a different key than the one this app trusts: it will not be installed.")}</div>
      )}
      {err && <div className="text-xs" style={{ color: "#c0392b" }}>{err}</div>}

      {running && job && (
        <div>
          <div className="flex justify-between text-xs mb-1.5" style={{ color: "var(--text-muted)" }}>
            <span className="truncate">
              {stepText[job.step]}
              {job.step === "download" && job.total_bytes ? ` · ${gb(job.done_bytes)} / ${gb(job.total_bytes)}` : ""}
            </span>
            <span className="font-code">{pct}%</span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: "var(--bg-muted)" }} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: "var(--accent-primary)" }} />
          </div>
        </div>
      )}
      {!running && job?.state === "done" && (
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-heading)" }}>
          <CheckCircle2 className="w-4 h-4" style={{ color: "var(--accent-primary)" }} />
          {tr("Law pack {0} installed. The previous one is kept as previous.db.", [job.installed_version ?? ""])}
        </div>
      )}
      {!running && job?.state === "error" && job.error && <div className="text-xs" style={{ color: "#c0392b" }}>{job.error}</div>}
      {!running && job?.state === "cancelled" && <div className="text-xs" style={{ color: "var(--text-muted)" }}>{tr("Stopped. Click again to continue the download.")}</div>}

      <div className="flex items-center justify-between gap-3">
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {upToDate ? tr("Your law pack is up to date.") : check?.update_available ? tr("A newer law pack is available.") : ""}
        </span>
        {running ? (
          <button type="button" onClick={() => cancelPackUpdate().catch(() => {})}
            className="px-3 py-1.5 rounded-lg border text-xs font-medium cursor-pointer hover:opacity-85"
            style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
            {tr("Stop")}
          </button>
        ) : (
          <button type="button" onClick={start} disabled={!canInstall}
            title={upToDate ? tr("Downloads the published pack again and replaces the installed one, including texts added here with Update BO.") : undefined}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            style={upToDate
              ? { border: "1px solid var(--border-strong)", color: "var(--text-heading)" }
              : { backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" }}>
            <Download className="w-3.5 h-3.5" />
            {upToDate ? tr("Reinstall") : tr("Download and install")}
          </button>
        )}
      </div>
    </div>
  );
}
