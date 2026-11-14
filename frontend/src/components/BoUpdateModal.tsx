import React, { useCallback, useEffect, useRef, useState } from "react";
import { tr } from "../i18n";
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, MinusCircle, RefreshCw, X, XCircle, DownloadCloud } from "lucide-react";
import { BoJob, BoStatus, BoStep, cancelBoUpdate, getBoJob, getBoStatus, startBoUpdate } from "../api/bo";
import { PackUpdatePanel } from "./PackUpdatePanel";

interface BoUpdateModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** called once an update has installed new texts, so the app can refresh what it shows about the law pack */
  onInstalled?: () => void;
}

// translated at render time (the language is not known when this module loads)
const stepLabel = (id: BoStep["id"], fallback: string): string =>
  ({
    check: tr("Recherche de nouveaux numéros sur le site du SGG"),
    download: tr("Téléchargement des PDF"),
    extract: tr("Lecture des PDF (extraction du texte arabe)"),
    ingest: tr("Découpage en articles et indexation"),
    install: tr("Installation du pack de lois mis à jour"),
  } as Record<string, string>)[id] ?? fallback;

function StepIcon({ s }: { s: BoStep["status"] }) {
  if (s === "running") return <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--accent-primary)" }} />;
  if (s === "done") return <CheckCircle2 className="w-4 h-4" style={{ color: "var(--accent-primary)" }} />;
  if (s === "error") return <XCircle className="w-4 h-4" style={{ color: "#c0392b" }} />;
  if (s === "skipped") return <MinusCircle className="w-4 h-4 opacity-50" />;
  return <CircleDashed className="w-4 h-4 opacity-40" />;
}

export function BoUpdateModal({ isOpen, onClose, onInstalled }: BoUpdateModalProps) {
  const [status, setStatus] = useState<BoStatus | null>(null);
  const [job, setJob] = useState<BoJob | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const wasRunning = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const st = await getBoStatus();
      setStatus(st);
      setJob(st.job);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (isOpen) refresh();
  }, [isOpen, refresh]);

  const running = job?.state === "running" || job?.state === "queued";

  // poll while a job runs (every second); tell the app once when it finishes with new texts
  useEffect(() => {
    if (!isOpen || !running) return;
    const id = window.setInterval(async () => {
      try {
        setJob(await getBoJob());
      } catch {
        /* keep the last state; the next tick retries */
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [isOpen, running]);

  useEffect(() => {
    if (running) wasRunning.current = true;
    else if (wasRunning.current && job?.state === "done") {
      wasRunning.current = false;
      if ((job.added.articles ?? 0) > 0) onInstalled?.();
      refresh();
    }
  }, [running, job, onInstalled, refresh]);

  if (!isOpen) return null;

  const problems = status?.problems ?? [];
  const start = async (dry: boolean) => {
    setStarting(true);
    setErr(null);
    try {
      setJob(await startBoUpdate(dry));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };
  const pct = Math.round((job?.progress ?? 0) * 100);
  const finished = job && !running;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5" style={{ backgroundColor: "rgba(27, 22, 20, 0.55)" }}>
      <div
        className="relative w-full max-w-2xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[90vh] sanad-liquid-modal"
        style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-strong)" }}
        role="dialog"
        aria-label={tr("Mise à jour du Bulletin Officiel")}
      >
        <div className="p-5 border-b flex items-center justify-between" style={{ borderColor: "var(--border-subtle)" }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ backgroundColor: "var(--bg-card)", color: "var(--accent-primary)" }}>
              <DownloadCloud className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-lg font-editorial font-medium" style={{ color: "var(--text-heading)" }}>
                {tr("Mise à jour du Bulletin Officiel")}
              </h2>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                {status?.newest_local
                  ? tr("Dernier numéro connu : {0} · {1} numéros en base", [status.newest_local, status.issues_local])
                  : tr("Recherche les nouveaux numéros publiés par le SGG, les télécharge et les ajoute à votre base.")}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer" style={{ color: "var(--text-muted)" }} aria-label={tr("Fermer")}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4 flex-1">
          <PackUpdatePanel onInstalled={onInstalled} busy={running} />

          <div className="text-sm font-medium pt-1" style={{ color: "var(--text-heading)" }}>{tr("Mise à jour du Bulletin Officiel")}</div>
          {problems.length > 0 && !running && (
            <div className="rounded-xl border p-3 text-xs space-y-1.5" style={{ borderColor: "var(--border-strong)", backgroundColor: "var(--bg-card)", color: "var(--text-heading)" }}>
              <div className="flex items-center gap-2 font-medium">
                <AlertTriangle className="w-4 h-4" style={{ color: "var(--accent-warm)" }} />
                {tr("La mise à jour ne peut pas démarrer pour l'instant")}
              </div>
              <ul className="list-disc pl-5 space-y-1" style={{ color: "var(--text-muted)" }}>
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          )}

          {err && (
            <div className="rounded-xl border p-3 text-xs" style={{ borderColor: "#c0392b", color: "#c0392b" }}>
              {err}
            </div>
          )}

          {job && (
            <>
              <div>
                <div className="flex justify-between text-xs mb-1.5" style={{ color: "var(--text-muted)" }}>
                  <span>
                    {job.state === "running" || job.state === "queued"
                      ? job.dry_run ? tr("Vérification en cours…") : tr("Mise à jour en cours…")
                      : job.state === "done" ? tr("Terminé")
                      : job.state === "cancelled" ? tr("Arrêté") : tr("Échec")}
                  </span>
                  <span className="font-code">{pct}%</span>
                </div>
                <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: "var(--bg-muted)" }} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                  <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: job.state === "error" ? "#c0392b" : "var(--accent-primary)" }} />
                </div>
              </div>

              <ol className="space-y-2">
                {job.steps.map((s) => (
                  <li key={s.id} className="flex items-start gap-2.5 text-sm" style={{ color: s.status === "pending" ? "var(--text-muted)" : "var(--text-heading)" }}>
                    <span className="mt-0.5 shrink-0"><StepIcon s={s.status} /></span>
                    <div className="min-w-0">
                      <div>{stepLabel(s.id, s.label)}</div>
                      {s.detail && (s.status === "running" || s.status === "done" || s.status === "skipped" || s.status === "error") && (
                        <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                          {s.detail}
                          {s.status === "running" && s.total > 1 ? ` · ${s.done}/${s.total}` : ""}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>

              {job.found.length > 0 && (
                <div className="text-xs rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-canvas)", color: "var(--text-heading)" }}>
                  <div className="font-medium mb-1">{tr("Nouveaux numéros trouvés ({0})", [job.found.length])}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {job.found.map((f) => (
                      <span key={f.name} className="font-code px-1.5 py-0.5 rounded" style={{ backgroundColor: "var(--bg-muted)" }}>{f.name.replace("BO_", "").replace("_Ar", "")}</span>
                    ))}
                  </div>
                </div>
              )}

              {job.state === "done" && (job.added.articles ?? 0) > 0 && (
                <div className="text-sm rounded-xl border p-3" style={{ borderColor: "var(--accent-primary)", backgroundColor: "var(--bg-card)", color: "var(--text-heading)" }}>
                  {tr("{0} articles ajoutés ({1} textes, {2} passages indexés). Ils sont déjà utilisables dans vos recherches.", [job.added.articles, job.added.instruments, job.added.chunks])}
                </div>
              )}
              {job.state === "done" && (job.added.articles ?? 0) === 0 && job.found.length === 0 && (
                <div className="text-sm rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)", color: "var(--text-heading)" }}>
                  {tr("Votre base est à jour : aucun nouveau numéro.")}
                </div>
              )}
              {job.error && (
                <div className="text-sm rounded-xl border p-3" style={{ borderColor: "#c0392b", color: "#c0392b" }}>{job.error}</div>
              )}
              {job.warnings.length > 0 && (
                <details className="text-xs" style={{ color: "var(--text-muted)" }}>
                  <summary className="cursor-pointer">{tr("Avertissements ({0})", [job.warnings.length])}</summary>
                  <ul className="list-disc pl-5 mt-1.5 space-y-1">
                    {job.warnings.map((w, i) => (<li key={i}>{w}</li>))}
                  </ul>
                </details>
              )}
            </>
          )}

          {!job && problems.length === 0 && !err && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {tr("Un clic suffit : l'application cherche les nouveaux numéros, les télécharge, lit le texte, l'indexe et l'ajoute à votre base. Rien n'est remplacé avant que tout soit prêt, et la version précédente est conservée.")}
            </p>
          )}
        </div>

        <div className="p-4 border-t flex items-center justify-end gap-2" style={{ borderColor: "var(--border-subtle)" }}>
          {running ? (
            <button type="button" onClick={() => cancelBoUpdate().catch(() => {})} className="px-4 py-2 rounded-xl border text-xs font-medium cursor-pointer hover:opacity-85" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
              {tr("Arrêter")}
            </button>
          ) : (
            <>
              <button type="button" disabled={starting || problems.length > 0} onClick={() => start(true)} className="px-4 py-2 rounded-xl border text-xs font-medium cursor-pointer hover:opacity-85 disabled:opacity-40 disabled:cursor-not-allowed" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
                {tr("Seulement vérifier")}
              </button>
              <button type="button" disabled={starting || problems.length > 0} onClick={() => start(false)} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed" style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" }}>
                {starting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                {finished ? tr("Relancer") : tr("Chercher et ajouter les nouveaux BO")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
