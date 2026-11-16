import React, { useCallback, useEffect, useState } from "react";
import { tr } from "../i18n";
import { AlertTriangle, Check, Eye, EyeOff, KeyRound, Loader2, Plus, ShieldCheck, Trash2, X } from "lucide-react";
import {
  Provider,
  ProviderKind,
  ProvidersState,
  deleteProvider,
  listProviders,
  saveProvider,
  setActiveProvider,
  setOfflineProvider,
  localModels,
  setCheckerProvider,
  testProvider,
} from "../api/providers";

interface ApiKeysModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 28) || "provider";

export function ApiKeysModal({ isOpen, onClose }: ApiKeysModalProps) {
  const [state, setState] = useState<ProvidersState | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<string, { ok: boolean; text: string }>>({});
  // add / edit form
  const [kind, setKind] = useState<ProviderKind>("openai");
  const [label, setLabel] = useState("OpenAI");
  const [model, setModel] = useState("gpt-4o");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [found, setFound] = useState<{ models: string[]; error?: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await listProviders());
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    if (isOpen) load();
  }, [isOpen, load]);
  useEffect(() => {   // in Offline mode the form opens on the local model: the online presets are disabled
    if (isOpen && state?.mode === "offline" && kind !== "local" && !editingId) {
      const lp = state.presets.find((x) => x.kind === "local");
      setKind("local"); setLabel(tr("Modèle local")); setModel(lp?.models[0] ?? ""); setBaseUrl(lp?.base_url ?? "http://127.0.0.1:11434/v1"); setFound(null); setApiKey("");
    }
  }, [isOpen, state?.mode]);

  // a key that was typed but not saved must not outlive the window
  useEffect(() => {
    if (!isOpen) {
      setApiKey("");
      setShowKey(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const off = state?.mode === "offline";   // Offline mode: online providers are never called, only a local model can be used
  const preset = state?.presets.find((p) => p.kind === kind);
  const pickKind = (k: ProviderKind) => {
    setKind(k);
    const p = state?.presets.find((x) => x.kind === k);
    setLabel(k === "openai" ? "OpenAI" : k === "anthropic" ? "Anthropic" : k === "local" ? tr("Modèle local") : tr("Autre fournisseur"));
    setModel(p?.models[0] ?? "");
    setBaseUrl(k === "local" ? p?.base_url ?? "http://127.0.0.1:11434/v1" : "");
    setFound(null);
    setEditingId(null);
    setApiKey("");
  };
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const edit = (p: Provider) => {
    setEditingId(p.id);
    setKind(p.kind);
    setLabel(p.label);
    setModel(p.model);
    setBaseUrl(p.base_url ?? "");
    setApiKey("");
  };
  const save = () =>
    run("save", async () => {
      const id = editingId ?? slug(label);
      await saveProvider(id, { kind, label: label.trim(), model: model.trim(), base_url: kind === "openai_compat" || kind === "local" ? baseUrl.trim() : null, api_key: kind === "local" ? null : apiKey.trim() || null });
      if (kind === "local" && !state?.offline) await setOfflineProvider(id);   // the first local model is the one Offline mode uses
      setApiKey("");
      setEditingId(null);
    });
  const canSave = label.trim() && model.trim() && (editingId || kind === "openai_compat" || kind === "local" || apiKey.trim().length >= 8) && (kind !== "openai_compat" || /^https?:\/\//.test(baseUrl.trim()))
    && (kind !== "local" || /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?/.test(baseUrl.trim()));
  const findModels = () =>
    run("find", async () => {
      const r = await localModels(baseUrl.trim() || "http://127.0.0.1:11434/v1");
      setFound({ models: r.models, error: r.ok ? undefined : r.error });
      if (r.models.length && !model.trim()) setModel(r.models[0]);
    });
  const test = (id: string) =>
    run(`test-${id}`, async () => {
      const r = await testProvider(id);
      setTests((t) => ({ ...t, [id]: { ok: r.ok, text: r.ok ? tr("Connexion réussie ({0})", [r.model ?? ""]) : r.error ?? tr("Échec") } }));
    });

  const field = "w-full rounded-lg border px-3 py-2 text-sm bg-transparent outline-none focus:ring-2";
  const fstyle = { borderColor: "var(--border-strong)", color: "var(--text-heading)" } as React.CSSProperties;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5" style={{ backgroundColor: "rgba(27, 22, 20, 0.55)" }}>
      <div className="relative w-full max-w-2xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[90vh] sanad-liquid-modal" style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-strong)" }} role="dialog" aria-label={tr("Clés API et modèles")}>
        <div className="p-5 border-b flex items-center justify-between" style={{ borderColor: "var(--border-subtle)" }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ backgroundColor: "var(--bg-card)", color: "var(--accent-primary)" }}>
              <KeyRound className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-lg font-editorial font-medium" style={{ color: "var(--text-heading)" }}>{tr("Clés API et modèles")}</h2>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{tr("Enregistrez plusieurs fournisseurs et choisissez celui qui rédige les réponses.")}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:opacity-75 cursor-pointer" style={{ color: "var(--text-muted)" }} aria-label={tr("Fermer")}><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 overflow-y-auto space-y-5 flex-1">
          {state?.mode === "offline" && (
            <div className="flex items-start gap-2 rounded-xl border p-3 text-xs" style={{ borderColor: "var(--border-strong)", backgroundColor: "var(--bg-card)", color: "var(--text-heading)" }}>
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-warm)" }} />
              {state.offline
                ? tr("Mode Hors-Ligne : les réponses sont rédigées par votre modèle local ({0}). Rien ne quitte l'ordinateur.", [state.providers.find((p) => p.id === state.offline)?.model ?? ""])
                : tr("Le mode Hors-Ligne est actif : aucun fournisseur en ligne n'est appelé. Ajoutez un modèle local (Ollama, LM Studio) pour obtenir des réponses rédigées sans connexion.")}
            </div>
          )}
          {err && <div className="rounded-xl border p-3 text-xs" style={{ borderColor: "#c0392b", color: "#c0392b" }}>{err}</div>}

          {/* saved providers */}
          <div className="space-y-2">
            {state && state.providers.length === 0 && (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {tr("Aucun fournisseur enregistré.")}
                {state.environment_provider ? " " + tr("(Le serveur utilise actuellement {0} / {1} défini dans son environnement.)", [state.environment_provider.provider, state.environment_provider.model ?? "?"]) : ""}
              </p>
            )}
            {state?.providers.map((p) => {
              const unused = !!off && p.kind !== "local";       // an online provider while the app is in Offline mode
              const isActive = off ? state.offline === p.id : state.active === p.id;
              const t = tests[p.id];
              return (
                <div key={p.id} className="rounded-xl border p-3 space-y-2" style={{ borderColor: isActive ? "var(--accent-primary)" : "var(--border-subtle)", backgroundColor: isActive ? "var(--bg-card)" : "var(--bg-canvas)", opacity: unused ? 0.55 : 1 }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: "var(--text-heading)" }}>
                        {p.label} <span className="font-code text-xs opacity-70">· {p.model}</span>
                      </div>
                      <div className="text-xs flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                        <ShieldCheck className="w-3 h-3" />
                        {p.kind === "local" ? tr("Sur cet ordinateur · sans clé") : p.has_key ? tr("Clé enregistrée (jamais réaffichée)") : p.kind === "openai_compat" ? tr("Sans clé") : tr("Clé manquante")}
                        {p.base_url ? <span className="font-code truncate">· {p.base_url}</span> : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button type="button" onClick={() => edit(p)} disabled={unused} className="px-2.5 py-1 rounded-lg border text-xs cursor-pointer hover:opacity-85 disabled:cursor-not-allowed" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>{tr("Modifier")}</button>
                      <button type="button" onClick={() => test(p.id)} disabled={unused || busy === `test-${p.id}`} className="px-2.5 py-1 rounded-lg border text-xs cursor-pointer hover:opacity-85 inline-flex items-center gap-1 disabled:cursor-not-allowed" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>
                        {busy === `test-${p.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : null}{tr("Tester")}
                      </button>
                      <button type="button" aria-label={tr("Supprimer")} onClick={() => run(`del-${p.id}`, () => deleteProvider(p.id))} className="p-1.5 rounded-lg hover:opacity-75 cursor-pointer" style={{ color: "var(--text-muted)" }}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--text-heading)" }}>
                    {unused && <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border" style={{ borderColor: "var(--border-subtle)", color: "var(--text-muted)" }}>{tr("Désactivé en mode Hors-Ligne")}</span>}
                    {!off && (<>
                    <button type="button" onClick={() => run("active", () => setActiveProvider(isActive ? null : p.id))} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border cursor-pointer" style={{ borderColor: isActive ? "var(--accent-primary)" : "var(--border-strong)", backgroundColor: isActive ? "var(--accent-primary)" : "transparent", color: isActive ? "var(--accent-primary-fg)" : "var(--text-heading)" }}>
                      {isActive ? <Check className="w-3 h-3" /> : null}{isActive ? tr("Utilisé pour répondre") : tr("Utiliser pour répondre")}
                    </button>
                    <button type="button" onClick={() => run("checker", () => setCheckerProvider(state.checker === p.id ? null : p.id))} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border cursor-pointer" style={{ borderColor: state.checker === p.id ? "var(--accent-primary)" : "var(--border-strong)" }} title={tr("Un second modèle relit chaque affirmation face à sa source. Choisissez un modèle différent de celui qui rédige.")}>
                      {state.checker === p.id ? <Check className="w-3 h-3" /> : null}{tr("Vérificateur")}
                    </button>
                    </>)}
                    {p.kind === "local" && (
                      <button type="button" onClick={() => run("offline", () => setOfflineProvider(state.offline === p.id ? null : p.id))} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border cursor-pointer" style={{ borderColor: state.offline === p.id ? "var(--accent-primary)" : "var(--border-strong)" }} title={tr("En mode Hors-Ligne, ce modèle rédige les réponses. Rien ne quitte l'ordinateur.")}>
                        {state.offline === p.id ? <Check className="w-3 h-3" /> : null}{state.offline === p.id ? tr("Utilisé en mode Hors-Ligne") : tr("Utiliser en mode Hors-Ligne")}
                      </button>
                    )}
                    {t && <span style={{ color: t.ok ? "var(--accent-primary)" : "#c0392b" }}>{t.text}</span>}
                  </div>
                </div>
              );
            })}
          </div>

          {/* add / edit */}
          <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: "var(--border-subtle)" }}>
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-heading)" }}>
              <Plus className="w-4 h-4" />{editingId ? tr("Modifier le fournisseur") : tr("Ajouter un fournisseur")}
              {editingId && <button type="button" onClick={() => pickKind(off ? "local" : "openai")} className="ml-auto text-xs underline cursor-pointer" style={{ color: "var(--text-muted)" }}>{tr("Annuler")}</button>}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(state?.presets ?? []).map((p) => (
                <button key={p.kind} type="button" disabled={!!editingId || (!!off && p.kind !== "local")} title={off && p.kind !== "local" ? tr("Désactivé en mode Hors-Ligne") : undefined} onClick={() => pickKind(p.kind)} className="px-3 py-1.5 rounded-lg border text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" style={{ borderColor: kind === p.kind ? "var(--accent-primary)" : "var(--border-strong)", backgroundColor: kind === p.kind ? "var(--bg-card)" : "transparent", color: "var(--text-heading)" }}>
                  {p.kind === "openai_compat" ? tr("Autre (compatible OpenAI)") : p.kind === "local" ? tr("Modèle local (Ollama, LM Studio)") : p.label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-xs space-y-1" style={{ color: "var(--text-muted)" }}>
                {tr("Nom affiché")}
                <input className={field} style={fstyle} value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} />
              </label>
              <label className="text-xs space-y-1" style={{ color: "var(--text-muted)" }}>
                {tr("Modèle")}
                <input className={field} style={fstyle} value={model} onChange={(e) => setModel(e.target.value)} list="provider-models" placeholder={kind === "openai" ? "gpt-4o" : ""} spellCheck={false} />
                <datalist id="provider-models">{(preset?.models ?? []).map((m) => (<option key={m} value={m} />))}</datalist>
              </label>
            </div>
            {kind === "local" && (
              <div className="space-y-2">
                <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  {tr("Le modèle tourne sur votre ordinateur : rien ne quitte l'ordinateur, et il fonctionne en mode Hors-Ligne. Installez Ollama (ollama.com) puis, par exemple, « ollama pull qwen2.5:7b », ou chargez un modèle dans LM Studio et démarrez son serveur local.")}
                </p>
                <div className="flex flex-wrap items-end gap-2">
                  <label className="text-xs space-y-1 flex-1 min-w-[220px]" style={{ color: "var(--text-muted)" }}>
                    {tr("Adresse du serveur local")}
                    <input className={field + " font-code"} style={fstyle} value={baseUrl} onChange={(e) => { setBaseUrl(e.target.value); setFound(null); }} spellCheck={false} />
                  </label>
                  <button type="button" onClick={() => { setBaseUrl("http://127.0.0.1:11434/v1"); setFound(null); }} className="px-2.5 py-2 rounded-lg border text-xs cursor-pointer" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>Ollama</button>
                  <button type="button" onClick={() => { setBaseUrl("http://127.0.0.1:1234/v1"); setFound(null); }} className="px-2.5 py-2 rounded-lg border text-xs cursor-pointer" style={{ borderColor: "var(--border-strong)", color: "var(--text-heading)" }}>LM Studio</button>
                  <button type="button" onClick={findModels} disabled={busy === "find"} className="inline-flex items-center gap-1.5 px-2.5 py-2 rounded-lg border text-xs cursor-pointer" style={{ borderColor: "var(--accent-primary)", color: "var(--accent-primary)" }}>
                    {busy === "find" ? <Loader2 className="w-3 h-3 animate-spin" /> : null}{tr("Trouver les modèles installés")}
                  </button>
                </div>
                {found && found.error && <p className="text-[11px]" style={{ color: "#c0392b" }}>{found.error}</p>}
                {found && !found.error && (
                  <div className="flex flex-wrap gap-1.5">
                    {found.models.length === 0 && <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Le serveur répond mais aucun modèle n'est installé.")}</span>}
                    {found.models.map((m) => (
                      <button key={m} type="button" onClick={() => setModel(m)} className="px-2 py-1 rounded-lg border text-[11px] font-code cursor-pointer" style={{ borderColor: model === m ? "var(--accent-primary)" : "var(--border-strong)", backgroundColor: model === m ? "var(--bg-card)" : "transparent", color: "var(--text-heading)" }}>{m}</button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {kind === "openai_compat" && (
              <label className="text-xs space-y-1 block" style={{ color: "var(--text-muted)" }}>
                {tr("Adresse de l'API (base URL)")}
                <input className={field + " font-code"} style={fstyle} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://openrouter.ai/api/v1" spellCheck={false} />
              </label>
            )}
            {kind !== "local" && (<>
            <label className="text-xs space-y-1 block" style={{ color: "var(--text-muted)" }}>
              {tr("Clé API")}{editingId ? " " + tr("(laisser vide pour garder la clé actuelle)") : kind === "openai_compat" ? " " + tr("(facultative)") : ""}
              <div className="relative">
                <input className={field + " font-code pr-10"} style={fstyle} type={showKey ? "text" : "password"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={kind === "openai" ? "sk-…" : ""} autoComplete="off" spellCheck={false} />
                <button type="button" onClick={() => setShowKey((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 cursor-pointer opacity-70" aria-label={showKey ? tr("Masquer") : tr("Afficher")}>
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </label>
            <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {tr("La clé est envoyée une seule fois au serveur local et rangée dans le trousseau de votre système ({0}). Elle n'est jamais renvoyée à l'écran ni incluse dans l'application.", [state?.key_storage ?? "…"])}
            </p>
            </>)}
            <div className="flex justify-end">
              <button type="button" onClick={save} disabled={!canSave || busy === "save"} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed" style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" }}>
                {busy === "save" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                {editingId ? tr("Enregistrer les changements") : tr("Enregistrer")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
