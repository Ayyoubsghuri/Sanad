import React, { useRef, useState } from "react";
import { tr, useI18n } from "../i18n";
import { AlertTriangle, CheckCircle2, FileSearch, History, Loader2, Search, ShieldAlert } from "lucide-react";
import {
  articleHistory, checkContract, findNewArticle, toolError,
  type ContractResult, type DiffSeg, type FinderResult, type HistoryResult,
} from "../api/useTools";

const card = { backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)" } as const;
const inputStyle = { backgroundColor: "var(--bg-surface)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" } as const;

function Diff({ segs }: { segs: DiffSeg[] }) {
  return (
    <p className="text-xs leading-relaxed" dir="rtl" style={{ color: "var(--text-primary)" }}>
      {segs.map((s, i) =>
        s.op === "equal" ? <span key={i}>{s.text} </span> :
        s.op === "insert" ? <mark key={i} className="rounded px-0.5" style={{ backgroundColor: "rgba(34,160,90,0.22)", color: "inherit" }}>{s.text} </mark> :
        <del key={i} className="rounded px-0.5" style={{ backgroundColor: "rgba(220,60,60,0.2)", color: "inherit" }}>{s.text} </del>
      )}
    </p>
  );
}

function Err({ msg }: { msg: string }) {
  return <div className="p-3 rounded-xl border text-xs flex gap-2" style={{ ...card, color: "var(--text-primary)" }}><AlertTriangle className="w-4 h-4 shrink-0" />{msg}</div>;
}

const CONF: Record<string, string> = { high: "Correspondance forte", medium: "Correspondance probable", low: "Correspondance faible : la règle a peut-être été scindée, fusionnée ou supprimée" };

// ------------------------------------------------------------------------------------------------ old -> new
export function FinderPanel({ asOf }: { asOf: string }) {
  const [ref, setRef] = useState("");
  const [res, setRes] = useState<FinderResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (target?: string) => {
    if (!ref.trim()) return;
    setBusy(true); setErr("");
    try { setRes(await findNewArticle({ ref, asOf, target })); } catch (e) { setRes(null); setErr(toolError(e)); }
    setBusy(false);
  };
  return (
    <div className="space-y-4">
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>{tr("Tapez un ancien article (ex. : « الفصل 440 من قانون المسطرة المدنية ») : l'outil cherche l'article qui l'a remplacé dans le nouveau texte.")}</p>
      <div className="flex gap-2">
        <input value={ref} onChange={(e) => setRef(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} dir="auto" placeholder="الفصل 440 من قانون المسطرة المدنية"
          className="flex-1 text-xs p-2 rounded-lg border outline-none" style={inputStyle} />
        <button type="button" onClick={() => run()} disabled={busy} className="px-3 rounded-lg text-xs font-medium cursor-pointer inline-flex items-center gap-1.5"
          style={{ backgroundColor: "var(--accent-primary)", color: "var(--text-on-accent, #fff)" }}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}{tr("Chercher")}
        </button>
      </div>
      {err && <Err msg={err} />}
      {res && (
        <div className="space-y-3">
          <div className="p-3 rounded-xl border text-xs space-y-1" style={card}>
            <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{tr("Ancien texte")} — {res.old.label} ({res.old.law})</div>
            <p dir="rtl" style={{ color: "var(--text-primary)" }}>{res.old.text}</p>
          </div>
          <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            {tr("Cherché dans :")} {res.target.title_ar || res.target.title_fr || res.target.instrument_id} · {tr(CONF[res.confidence])} · <b>{tr("dérivé")}</b>
          </div>
          {res.matches.map((m, i) => (
            <div key={m.provision_id} className="p-3 rounded-xl border text-xs space-y-1" style={{ ...card, outline: i === 0 ? "2px solid var(--accent-primary)" : "none" }}>
              <div className="flex justify-between gap-2 font-semibold" style={{ color: "var(--text-heading)" }}>
                <span>{i === 0 ? tr("Meilleure correspondance") : tr("Autre piste")} — {tr("Art.")} {m.number}</span>
                <span style={{ color: "var(--text-muted)" }}>{Math.round(m.score * 100)}%</span>
              </div>
              {i === 0 ? <Diff segs={res.diff_with_best} /> : <p dir="rtl" style={{ color: "var(--text-primary)" }}>{m.text}</p>}
            </div>
          ))}
          <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Comparaison automatique des textes, pas une table officielle : lisez les deux articles. Vert = ajouté, rouge = supprimé.")}</p>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ history
export function HistoryPanel({ asOf }: { asOf: string }) {
  const [ref, setRef] = useState("");
  const [res, setRes] = useState<HistoryResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!ref.trim()) return;
    setBusy(true); setErr("");
    try { setRes(await articleHistory({ ref, asOf })); } catch (e) { setRes(null); setErr(toolError(e)); }
    setBusy(false);
  };
  return (
    <div className="space-y-4">
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>{tr("Tous les textes qu'un article a eus, avec les dates et ce qui a changé d'une version à l'autre.")}</p>
      <div className="flex gap-2">
        <input value={ref} onChange={(e) => setRef(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} dir="auto" placeholder="المادة 78-2 من مدونة التجارة"
          className="flex-1 text-xs p-2 rounded-lg border outline-none" style={inputStyle} />
        <button type="button" onClick={run} disabled={busy} className="px-3 rounded-lg text-xs font-medium cursor-pointer inline-flex items-center gap-1.5"
          style={{ backgroundColor: "var(--accent-primary)", color: "var(--text-on-accent, #fff)" }}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <History className="w-3.5 h-3.5" />}{tr("Historique")}
        </button>
      </div>
      {err && <Err msg={err} />}
      {res && (
        <div className="space-y-3">
          <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            {tr("Article")} {res.article.label} · {res.periods.length} {tr("version(s)")} · {res.changes} {tr("changement(s)")} · {tr("Au")} {res.as_of}
          </div>
          {res.ended_on && <Err msg={tr("Cet article a pris fin le {0}.", [res.ended_on])} />}
          {res.periods.map((p, i) => (
            <div key={i} className="p-3 rounded-xl border text-xs space-y-1.5" style={{ ...card, outline: p.in_force_on_date ? "2px solid var(--accent-primary)" : "none" }}>
              <div className="flex flex-wrap justify-between gap-2 font-semibold" style={{ color: "var(--text-heading)" }}>
                <span>{p.valid_from} → {p.valid_to || tr("aujourd'hui")}{p.in_force_on_date ? ` · ${tr("en vigueur à cette date")}` : ""}</span>
                <span style={{ color: "var(--text-muted)" }}>{p.sources.map((s) => s.edition).join(" / ")}</span>
              </div>
              {p.amended_by && <div style={{ color: "var(--text-muted)" }}>{tr("Modifié par")} {p.amended_by.number || p.amended_by.instrument_id}{p.amended_by.bo_number ? ` (BO ${p.amended_by.bo_number})` : ""}</div>}
              {p.diff_from_previous ? (
                <>
                  <div style={{ color: "var(--text-muted)" }}>+{p.change_summary?.words_added} / −{p.change_summary?.words_removed} {tr("mots par rapport à la version précédente")}</div>
                  <Diff segs={p.diff_from_previous} />
                </>
              ) : <p dir="rtl" style={{ color: "var(--text-primary)" }}>{p.text}</p>}
            </div>
          ))}
          {res.continued_in && (
            <div className="p-3 rounded-xl border text-xs space-y-1" style={card}>
              <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{tr("Repris dans le texte qui l'a remplacé (dérivé)")} — {tr("Art.")} {res.continued_in.matches[0]?.number}</div>
              <p dir="rtl">{res.continued_in.matches[0]?.text}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ contract checker
const VERDICT: Record<string, { label: string; color: string }> = {
  conflicts: { label: "En contradiction", color: "rgba(220,60,60,0.9)" },
  check: { label: "À vérifier", color: "rgba(214,150,30,0.95)" },
  consistent: { label: "Conforme", color: "rgba(34,160,90,0.9)" },
};

export function ContractPanel({ asOf }: { asOf: string }) {
  const { lang } = useI18n();
  const [text, setText] = useState("");
  const [res, setRes] = useState<ContractResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const run = async () => {
    if (text.trim().length < 60) { setErr(tr("Collez le texte du contrat (au moins quelques clauses).")); return; }
    setBusy(true); setErr("");
    try { setRes(await checkContract({ text, asOf, lang })); } catch (e) { setRes(null); setErr(toolError(e)); }
    setBusy(false);
  };
  const load = async (f: File | undefined) => {
    if (!f) return;
    if (/\.(txt|md)$/i.test(f.name)) setText(await f.text());
    else setErr(tr("Pour un PDF ou un Word, ajoutez-le comme pièce jointe dans le chat, ou collez son texte ici."));
  };
  return (
    <div className="space-y-4">
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        {tr("Collez un contrat : les noms sont masqués sur votre appareil, puis chaque clause est comparée aux articles du pack. L'outil signale les clauses à lire ; ce n'est pas un avis juridique.")}
      </p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} dir="auto" rows={9} placeholder={tr("Texte du contrat…")}
        className="w-full text-xs p-2.5 rounded-lg border outline-none" style={inputStyle} />
      <div className="flex gap-2 items-center">
        <button type="button" onClick={run} disabled={busy} className="px-3 py-2 rounded-lg text-xs font-medium cursor-pointer inline-flex items-center gap-1.5"
          style={{ backgroundColor: "var(--accent-primary)", color: "var(--text-on-accent, #fff)" }}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileSearch className="w-3.5 h-3.5" />}{tr("Vérifier le contrat")}
        </button>
        <button type="button" onClick={() => file.current?.click()} className="px-3 py-2 rounded-lg text-xs border cursor-pointer" style={{ ...card, color: "var(--text-primary)" }}>{tr("Charger un .txt")}</button>
        <input ref={file} type="file" accept=".txt,.md" hidden onChange={(e) => load(e.target.files?.[0])} />
        {res && <button type="button" onClick={() => { setRes(null); setText(""); }} className="text-xs underline cursor-pointer" style={{ color: "var(--text-muted)" }}>{tr("Effacer")}</button>}
      </div>
      {err && <Err msg={err} />}
      {res && (
        <div className="space-y-3">
          {res.note && <Err msg={res.note} />}
          {res.summary && (
            <div className="flex gap-2 text-[11px]">
              {Object.entries(VERDICT).map(([k, v]) => <span key={k} className="px-2 py-1 rounded-md" style={{ border: `1px solid ${v.color}`, color: "var(--text-primary)" }}>{tr(v.label)} : {res.summary?.[k] ?? 0}</span>)}
            </div>
          )}
          {res.findings.map((f, i) => {
            const cl = res.clauses.find((c) => c.n === f.clause);
            return (
              <div key={i} className="p-3 rounded-xl border text-xs space-y-1.5" style={{ ...card, borderLeft: `4px solid ${VERDICT[f.verdict].color}` }}>
                <div className="flex items-center gap-1.5 font-semibold" style={{ color: "var(--text-heading)" }}>
                  {f.verdict === "conflicts" ? <ShieldAlert className="w-3.5 h-3.5" /> : f.verdict === "consistent" ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                  {tr(VERDICT[f.verdict].label)} — {tr("clause")} {f.clause}
                </div>
                {cl && <p dir="auto" className="line-clamp-3" style={{ color: "var(--text-muted)" }}>{cl.text}</p>}
                <p dir="auto" style={{ color: "var(--text-primary)" }}>{f.why}</p>
                <blockquote dir="rtl" className="border-s-2 ps-2" style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}>« {f.quote} »</blockquote>
                <div style={{ color: "var(--text-muted)" }}>{f.law}, {f.article} · {f.trust}</div>
              </div>
            );
          })}
          {res.status === "retrieved_only" && res.clauses.map((c) => (
            <div key={c.n} className="p-3 rounded-xl border text-xs space-y-1" style={card}>
              <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{tr("Clause")} {c.n}</div>
              <p dir="auto" style={{ color: "var(--text-muted)" }}>{c.text}</p>
              {c.passages.map((p) => res.passages[p] && <div key={p} dir="rtl" className="pt-1" style={{ color: "var(--text-primary)" }}><b>{res.passages[p].law}, {res.passages[p].article}</b> — {res.passages[p].text.slice(0, 260)}…</div>)}
            </div>
          ))}
          {res.cited_in_document.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer font-semibold" style={{ color: "var(--text-heading)" }}>{tr("Articles cités dans le contrat")} ({res.cited_in_document.length})</summary>
              {res.cited_in_document.map((c, i) => (
                <div key={i} className="mt-1.5 p-2 rounded-lg border" style={card}>
                  <b>{c.reference}</b> {c.note ? `— ${c.note}` : ""}
                  {c.text && <p dir="rtl" className="mt-1">{c.text}</p>}
                </div>
              ))}
            </details>
          )}
          {res.findings_dropped_unverified ? <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("{0} remarque(s) écartée(s) : leur citation n'a pas été retrouvée dans l'article.", [res.findings_dropped_unverified])}</p> : null}
          <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{res.notice}</p>
        </div>
      )}
    </div>
  );
}
