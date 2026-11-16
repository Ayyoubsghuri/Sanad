import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, AlignLeft, ArrowLeft, ArrowRight, ArrowUpRight, Book, BookOpen, Briefcase, CalendarClock, CheckCircle2,
  ClipboardList, ExternalLink, FileCheck, FilePen, FileSearch, FileSignature, FileText, Gavel, GitCompare, Home, IdCard,
  Library, ListChecks, ListOrdered, Loader2, Mail, MessageSquare, Package, Scale, ShieldCheck, Split, Swords, Users, X, XCircle,
} from "lucide-react";
import { tr, useI18n } from "../i18n";
import {
  ArticleSource, Argument, CourtroomOutput, L3, ProCatalog, ProJob, ProResult, ProTool, ReportOutput, RulingCard,
  getJob, prepareJob, proCatalog, runJob,
} from "../api/pro";
import { ArtifactItem, ArtifactKind } from "../types/agent";
import { IS_ANDROID } from "../platform";

const ICONS: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  gavel: Gavel, briefcase: Briefcase, library: Library, "file-pen": FilePen, "message-square": MessageSquare, scale: Scale,
  swords: Swords, "file-search": FileSearch, "arrow-up-right": ArrowUpRight, "git-compare": GitCompare, "book-open": BookOpen,
  "align-left": AlignLeft, split: Split, home: Home, "file-signature": FileSignature, users: Users, "clipboard-list": ClipboardList,
  "list-checks": ListChecks, "id-card": IdCard, "shield-check": ShieldCheck, package: Package, "alert-triangle": AlertTriangle,
  book: Book, mail: Mail, "calendar-clock": CalendarClock, "list-ordered": ListOrdered, "file-check": FileCheck,
};

const TAG_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  strong: { bg: "rgba(34,139,84,.14)", fg: "#1f7a4d", label: "Strong" },
  won: { bg: "rgba(34,139,84,.14)", fg: "#1f7a4d", label: "Won in court" },
  medium: { bg: "rgba(196,140,32,.16)", fg: "#9a6a12", label: "Medium" },
  weak: { bg: "rgba(190,60,50,.13)", fg: "#a23a30", label: "Weak" },
  lost: { bg: "rgba(190,60,50,.13)", fg: "#a23a30", label: "Lost in court" },
  risk: { bg: "rgba(190,60,50,.13)", fg: "#a23a30", label: "Risk" },
  missing: { bg: "rgba(196,140,32,.16)", fg: "#9a6a12", label: "Missing" },
};
const CHAMBER: Record<string, string> = {
  civil: "Civil", family: "Family", commercial: "Commercial", administrative: "Administrative", social: "Social",
  criminal: "Criminal", real_estate: "Real estate",
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
  asOfDate: string;
  onOpenArtifact?: (a: ArtifactItem) => void;
}

export function ProToolkitModal({ isOpen, onClose, asOfDate, onOpenArtifact }: Props) {
  const { lang, dir } = useI18n();
  const pick = (l?: L3) => (l ? l[lang] || l.en : "");
  const [catalog, setCatalog] = useState<ProCatalog | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [tool, setTool] = useState<ProTool | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [job, setJob] = useState<ProJob | null>(null);
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [asOf, setAsOf] = useState(asOfDate);

  useEffect(() => setAsOf(asOfDate), [asOfDate]);
  useEffect(() => {
    if (!isOpen || catalog) return;
    proCatalog().then(setCatalog).catch((e) => setLoadErr(String(e?.message || e)));
  }, [isOpen, catalog]);

  // poll a running job
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const ctl = new AbortController();
    const t = setInterval(() => {
      getJob(job.job_id, ctl.signal).then(setJob).catch(() => undefined);
    }, 1200);
    return () => { clearInterval(t); ctl.abort(); };
  }, [job?.job_id, job?.status]);

  if (!isOpen) return null;

  const openTool = (t: ProTool) => {
    setTool(t); setJob(null); setErr(null); setFocus(null); setEdited({});
    const init: Record<string, string> = {};
    t.fields.forEach((f) => { if (f.kind === "choice" && f.options?.length) init[f.id] = f.options[0].id; });
    setFields(init);
  };
  const back = () => { if (job) { setJob(null); setErr(null); } else setTool(null); };
  const missing = tool?.fields.filter((f) => f.required && !(fields[f.id] || "").trim()) || [];

  const doPrepare = async () => {
    if (!tool) return;
    setBusy(true); setErr(null);
    try {
      const j = await prepareJob(tool.id, fields, asOf, lang);
      setJob(j); setEdited({});
    } catch (e: any) { setErr(String(e?.message || e)); }
    setBusy(false);
  };
  const doRun = async () => {
    if (!job) return;
    setBusy(true); setErr(null);
    try { setJob(await runJob(job.job_id, Object.keys(edited).length ? edited : undefined)); }
    catch (e: any) { setErr(String(e?.message || e)); }
    setBusy(false);
  };
  const showSource = (id: string) => {
    setFocus(id);
    setTimeout(() => document.getElementById(`pro-src-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 30);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-stretch sm:items-center justify-center sm:p-4" style={{ backgroundColor: "rgba(27,22,20,.55)" }} dir={dir}>
      <div className="relative w-full sm:max-w-6xl sm:rounded-2xl border shadow-2xl overflow-hidden flex flex-col h-full sm:h-[92vh] sanad-liquid-modal"
        style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-strong)" }}>
        {/* header */}
        <div className="px-4 sm:px-6 py-3.5 border-b flex items-center gap-3 shrink-0" style={{ borderColor: "var(--border-subtle)" }}>
          {tool && (
            <button type="button" onClick={back} className="p-1.5 rounded-lg hover:opacity-75 cursor-pointer" style={{ color: "var(--text-muted)" }} title={tr("Back")}>
              {dir === "rtl" ? <ArrowRight className="w-4 h-4" /> : <ArrowLeft className="w-4 h-4" />}
            </button>
          )}
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ backgroundColor: "var(--bg-card)", color: "var(--accent-primary)" }}>
            <Briefcase className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-base sm:text-lg font-editorial font-medium truncate" style={{ color: "var(--text-heading)" }}>
              {tool ? pick(tool.label) : tr("Professional Toolkit")}
            </h2>
            <div className="text-[11px] truncate" style={{ color: "var(--text-muted)" }}>
              {tool ? pick(tool.description) : tr("Moroccan legal intelligence for lawyers, judges, notaries, companies and judicial officers")}
            </div>
          </div>
          {catalog && (
            <span className="hidden sm:inline-flex text-[10px] px-2 py-1 rounded-md font-medium whitespace-nowrap"
              style={{ backgroundColor: catalog.rulings_available ? "rgba(34,139,84,.12)" : "rgba(196,140,32,.14)", color: catalog.rulings_available ? "#1f7a4d" : "#9a6a12" }}>
              {catalog.rulings_available ? tr("Court of Cassation rulings: installed") : tr("Rulings database not installed yet")}
            </span>
          )}
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg hover:opacity-75 cursor-pointer" style={{ color: "var(--text-muted)" }} title={tr("Close")}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-5">
          {loadErr && <ErrorBox text={loadErr} />}
          {!catalog && !loadErr && <Spinner text={tr("Loading…")} />}
          {catalog && !tool && <ToolHome catalog={catalog} pick={pick} onOpen={openTool} />}

          {catalog && tool && !job && (
            <div className="max-w-3xl mx-auto space-y-4">
              {tool.fields.map((f) => (
                <label key={f.id} className="block">
                  <span className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-heading)" }}>
                    {pick(f.label)}{f.required ? " *" : ""}
                  </span>
                  {f.kind === "choice" ? (
                    <div className="flex flex-wrap gap-2">
                      {f.options!.map((o) => (
                        <button key={o.id} type="button" onClick={() => setFields({ ...fields, [f.id]: o.id })}
                          className="px-3 py-1.5 rounded-lg border text-xs cursor-pointer transition-colors"
                          style={{
                            borderColor: fields[f.id] === o.id ? "var(--accent-primary)" : "var(--border-subtle)",
                            backgroundColor: fields[f.id] === o.id ? "var(--bg-card)" : "transparent",
                            color: fields[f.id] === o.id ? "var(--accent-primary)" : "var(--text-primary)",
                          }}>{pick(o.label)}</button>
                      ))}
                    </div>
                  ) : f.kind === "textarea" ? (
                    <textarea value={fields[f.id] || ""} onChange={(e) => setFields({ ...fields, [f.id]: e.target.value })}
                      placeholder={pick(f.placeholder)} rows={f.id.startsWith("document") ? 10 : 7} dir="auto"
                      className="w-full rounded-xl border px-3 py-2.5 text-sm outline-none resize-y"
                      style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }} />
                  ) : (
                    <input value={fields[f.id] || ""} onChange={(e) => setFields({ ...fields, [f.id]: e.target.value })}
                      placeholder={pick(f.placeholder)} dir="auto"
                      className="w-full rounded-xl border px-3 py-2 text-sm outline-none"
                      style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }} />
                  )}
                </label>
              ))}
              <div className="flex flex-wrap items-center gap-3 pt-1">
                <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  {tr("Law in force on")}
                  <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value || asOfDate)}
                    className="rounded-lg border px-2 py-1 text-xs" style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }} />
                </label>
                <div className="flex-1" />
                <button type="button" disabled={busy || missing.length > 0} onClick={doPrepare}
                  className="px-4 py-2 rounded-xl text-sm font-medium cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
                  style={{ backgroundColor: "var(--accent-primary)", color: "var(--bg-surface)" }}>
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  {tr("Continue")}
                </button>
              </div>
              <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {IS_ANDROID
                  ? tr("You will see exactly what is sent before anything leaves the phone.")
                  : tr("Names, ID numbers, phones and addresses are replaced by placeholders on this computer. You will see exactly what is sent before anything leaves it.")}
              </p>
              {err && <ErrorBox text={err} />}
            </div>
          )}

          {job && job.status === "preview" && (
            <div className="max-w-3xl mx-auto space-y-4">
              <div className="rounded-xl border p-3.5 text-xs leading-relaxed" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-card)", color: "var(--text-primary)" }}>
                {job.planned_calls > 0 && job.phone_unmasked
                  ? tr("On the phone, names are not masked: this text is sent as written to {0} in {1} steps. Replace names by initials before sending.", [job.model || tr("the model"), job.planned_calls])
                  : job.planned_calls > 0
                  ? tr("This text (names masked) and public law passages will be sent to {0} in {1} steps. You can still edit it.", [job.model || tr("the model"), job.planned_calls])
                  : tr("No language model is used (Offline mode or no API key): Sanad will list the articles and rulings it finds, without analysis.")}
              </div>
              {job.preview.map((p) => (
                <label key={p.field} className="block">
                  <span className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-heading)" }}>{pick(p.label)}</span>
                  <textarea value={edited[p.field] ?? p.text} onChange={(e) => setEdited({ ...edited, [p.field]: e.target.value })} rows={7} dir="auto"
                    className="w-full rounded-xl border px-3 py-2.5 text-sm outline-none resize-y font-code"
                    style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }} />
                </label>
              ))}
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setJob(null)} className="px-4 py-2 rounded-xl text-sm border cursor-pointer"
                  style={{ borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}>{tr("Edit")}</button>
                <button type="button" disabled={busy} onClick={doRun}
                  className="px-4 py-2 rounded-xl text-sm font-medium cursor-pointer disabled:opacity-50 inline-flex items-center gap-2"
                  style={{ backgroundColor: "var(--accent-primary)", color: "var(--bg-surface)" }}>
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  {job.planned_calls > 0 ? tr("Send and analyse") : tr("Search")}
                </button>
              </div>
              {err && <ErrorBox text={err} />}
            </div>
          )}

          {job && job.status === "running" && <Progress job={job} pick={pick} tool={tool!} />}
          {job && job.status === "error" && (
            <div className="max-w-3xl mx-auto space-y-3">
              <ErrorBox text={job.error?.message || tr("The analysis failed.")} />
              <button type="button" onClick={() => setJob(null)} className="px-4 py-2 rounded-xl text-sm border cursor-pointer"
                style={{ borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}>{tr("Try again")}</button>
            </div>
          )}
          {job && job.status === "done" && job.result && tool && (
            <ResultView result={job.result} tool={tool} pick={pick} focus={focus} onCite={showSource}
              onExport={onOpenArtifact ? () => onOpenArtifact(toArtifact(job.result!, tool, pick)) : undefined} />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- home
function ToolHome({ catalog, pick, onOpen }: { catalog: ProCatalog; pick: (l?: L3) => string; onOpen: (t: ProTool) => void }) {
  const featured = catalog.tools.filter((t) => t.featured);
  return (
    <div className="space-y-7">
      <div className="grid gap-3 md:grid-cols-3">
        {featured.map((t) => {
          const Icon = ICONS[t.icon] || Briefcase;
          return (
            <button key={t.id} type="button" onClick={() => onOpen(t)}
              className="text-start rounded-2xl border p-4 cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-lg"
              style={{ borderColor: "var(--border-strong)", backgroundColor: "var(--bg-card)" }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-3" style={{ backgroundColor: "var(--accent-primary)", color: "var(--bg-surface)" }}>
                <Icon className="w-5 h-5" />
              </div>
              <div className="font-editorial text-base font-medium mb-1" style={{ color: "var(--text-heading)" }}>{pick(t.label)}</div>
              <div className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>{pick(t.description)}</div>
            </button>
          );
        })}
      </div>
      {catalog.groups.filter((g) => g.id !== "featured").map((g) => (
        <section key={g.id}>
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-2.5" style={{ color: "var(--text-muted)" }}>{pick(g.label)}</h3>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {catalog.tools.filter((t) => t.group === g.id).map((t) => {
              const Icon = ICONS[t.icon] || FileText;
              return (
                <button key={t.id} type="button" onClick={() => onOpen(t)}
                  className="text-start flex gap-3 rounded-xl border px-3 py-2.5 cursor-pointer transition-colors hover:opacity-90"
                  style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-surface)" }}>
                  <Icon className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "var(--accent-warm)" }} />
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium" style={{ color: "var(--text-heading)" }}>{pick(t.label)}</span>
                    <span className="block text-[11px] leading-snug line-clamp-2" style={{ color: "var(--text-muted)" }}>{pick(t.description)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        {tr("Every point cites the articles and rulings it relies on; citations the model invents are removed. These tools assist professionals and do not replace their judgment.")}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- progress
function Progress({ job, pick, tool }: { job: ProJob; pick: (l?: L3) => string; tool: ProTool }) {
  return (
    <div className="max-w-xl mx-auto py-6">
      <div className="flex items-center gap-3 mb-5">
        <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--accent-primary)" }} />
        <div className="text-sm font-medium" style={{ color: "var(--text-heading)" }}>
          {tool.kind === "courtroom" ? tr("The courtroom is in session…") : tr("Analysing…")}
        </div>
      </div>
      <ol className="space-y-2">
        {job.steps.map((s, i) => (
          <li key={i} className="flex items-center gap-2.5 text-sm pro-fade-in">
            {s.status === "running" ? <Loader2 className="w-4 h-4 animate-spin shrink-0" style={{ color: "var(--accent-primary)" }} />
              : s.status === "failed" ? <XCircle className="w-4 h-4 shrink-0" style={{ color: "#a23a30" }} />
              : <CheckCircle2 className="w-4 h-4 shrink-0" style={{ color: "#1f7a4d" }} />}
            <span style={{ color: s.status === "running" ? "var(--text-heading)" : "var(--text-muted)" }}>{pick(s.label)}</span>
            {s.ms != null && <span className="text-[10px] font-code" style={{ color: "var(--text-muted)" }}>{(s.ms / 1000).toFixed(1)} s</span>}
          </li>
        ))}
      </ol>
      {tool.kind === "courtroom" && (
        <p className="text-[11px] mt-6" style={{ color: "var(--text-muted)" }}>{tr("Three separate analyses run one after the other; this usually takes one to three minutes.")}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- results
function ResultView({ result, tool, pick, focus, onCite, onExport }: {
  result: ProResult; tool: ProTool; pick: (l?: L3) => string; focus: string | null; onCite: (id: string) => void; onExport?: () => void;
}) {
  const noRulingsDb = result.warnings.includes("no_rulings_db");
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-5">
        <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
          <span>{tr("Law in force on {0}", [result.as_of])}</span>
          <span>·</span>
          <span>{tr("{0} articles · {1} rulings", [result.articles.length, result.rulings.length])}</span>
          {!!result.unsupported_citations && <span>· {tr("{0} invented citations removed", [result.unsupported_citations])}</span>}
          <div className="flex-1" />
          {onExport && result.output && (
            <button type="button" onClick={onExport} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border cursor-pointer"
              style={{ borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}>
              <FileText className="w-3.5 h-3.5" />{tr("Open as document")}
            </button>
          )}
        </div>
        {noRulingsDb && tool.uses_rulings && (
          <Note text={tr("The rulings database is not installed yet, so this analysis uses the law only. Similar cases will appear once it is installed.")} />
        )}
        {result.warnings.includes("no_model") && (
          <Note text={tr("No language model was used (Offline mode or no API key). Add a key in API keys and use Hybrid mode for the full analysis.")} />
        )}
        {result.warnings.includes("nothing_found") && <Note text={tr("Nothing relevant was found in the law pack for this text.")} />}
        {result.issues?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {result.issues.map((s, i) => (
              <span key={i} className="text-[11px] px-2 py-1 rounded-lg" style={{ backgroundColor: "var(--bg-card)", color: "var(--text-primary)" }} dir="auto">{s}</span>
            ))}
          </div>
        )}
        {result.output && result.kind === "courtroom" && <Courtroom out={result.output as CourtroomOutput} onCite={onCite} />}
        {result.output && result.kind !== "courtroom" && <Report out={result.output as ReportOutput} onCite={onCite} />}
        {result.kind === "finder" && <RulingList rulings={result.rulings} focus={focus} big />}
        <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{result.notice}</p>
      </div>
      <aside className="min-w-0 space-y-4 lg:sticky lg:top-0 lg:self-start lg:max-h-[78vh] lg:overflow-y-auto">
        <h3 className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{tr("Sources")}</h3>
        {result.articles.map((a) => <ArticleCard key={a.id} a={a} open={focus === a.id} />)}
        {result.kind !== "finder" && <RulingList rulings={result.rulings} focus={focus} />}
        {!result.articles.length && !result.rulings.length && <div className="text-xs" style={{ color: "var(--text-muted)" }}>{tr("No sources.")}</div>}
      </aside>
    </div>
  );
}

function Chips({ ids, onCite, unsourced }: { ids: string[]; onCite: (id: string) => void; unsourced?: boolean }) {
  if (unsourced) return <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: "rgba(196,140,32,.16)", color: "#9a6a12" }}>{tr("no source")}</span>;
  return (
    <span className="inline-flex flex-wrap gap-1 align-middle">
      {ids.map((id) => (
        <button key={id} type="button" onClick={() => onCite(id)} className="text-[10px] font-code px-1.5 py-0.5 rounded cursor-pointer"
          style={{ backgroundColor: id.startsWith("R") ? "rgba(90,70,160,.13)" : "var(--bg-card)", color: id.startsWith("R") ? "#5a46a0" : "var(--accent-primary)" }}>{id}</button>
      ))}
    </span>
  );
}

function Tag({ t }: { t?: string }) {
  const s = t ? TAG_STYLE[t] : undefined;
  if (!s) return null;
  return <span className="text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap" style={{ backgroundColor: s.bg, color: s.fg }}>{tr(s.label)}</span>;
}

function Report({ out, onCite }: { out: ReportOutput; onCite: (id: string) => void }) {
  return (
    <div className="space-y-5" dir="auto">
      <div>
        <h3 className="font-editorial text-lg font-medium" style={{ color: "var(--text-heading)" }}>{out.title}</h3>
        {out.summary && <p className="text-sm mt-1.5 leading-relaxed" style={{ color: "var(--text-primary)" }}>{out.summary}</p>}
      </div>
      {out.sections.filter((s) => s.items?.length).map((s, i) => (
        <section key={i} className="rounded-xl border p-4" style={{ borderColor: "var(--border-subtle)" }}>
          <h4 className="text-sm font-semibold mb-2.5" style={{ color: "var(--text-heading)" }}>{s.heading}</h4>
          <ul className="space-y-2.5">
            {s.items.map((it, j) => (
              <li key={j} className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                <span className="whitespace-pre-wrap">{it.text}</span>{" "}
                <Tag t={it.tag} /> <Chips ids={it.sources} unsourced={it.unsourced} onCite={onCite} />
              </li>
            ))}
          </ul>
        </section>
      ))}
      {!!out.missing_information?.length && (
        <section className="rounded-xl border p-4" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-card)" }}>
          <h4 className="text-sm font-semibold mb-2" style={{ color: "var(--text-heading)" }}>{tr("Information that would make this more precise")}</h4>
          <ul className="list-disc ps-5 space-y-1 text-sm" style={{ color: "var(--text-primary)" }}>{out.missing_information.map((m, i) => <li key={i}>{m}</li>)}</ul>
        </section>
      )}
    </div>
  );
}

function Gauge({ value, confidence }: { value: number; confidence: string }) {
  const r = 44, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value));
  const col = v >= 60 ? "#1f7a4d" : v >= 40 ? "#b07a14" : "#a23a30";
  return (
    <div className="flex items-center gap-4">
      <svg width="112" height="112" viewBox="0 0 112 112" className="shrink-0">
        <circle cx="56" cy="56" r={r} fill="none" stroke="var(--border-subtle)" strokeWidth="10" />
        <circle cx="56" cy="56" r={r} fill="none" stroke={col} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(c * v) / 100} ${c}`} transform="rotate(-90 56 56)" style={{ transition: "stroke-dasharray .8s ease" }} />
        <text x="56" y="62" textAnchor="middle" fontSize="24" fontWeight="600" fill={col}>{v}%</text>
      </svg>
      <div>
        <div className="text-sm font-medium" style={{ color: "var(--text-heading)" }}>{tr("Estimated chance of success")}</div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{tr("Confidence: {0}", [tr(confidence)])}</div>
        <div className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>{tr("An estimate from the arguments and similar rulings, not a prediction.")}</div>
      </div>
    </div>
  );
}

function ArgCard({ a, n, onCite, accent }: { a: Argument; n: number; onCite: (id: string) => void; accent: string }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)", borderInlineStartWidth: 3, borderInlineStartColor: accent }}>
      <div className="flex items-start gap-2 mb-1">
        <span className="text-[10px] font-code mt-0.5" style={{ color: "var(--text-muted)" }}>{n}</span>
        <span className="text-sm font-medium flex-1" style={{ color: "var(--text-heading)" }}>{a.title}</span>
        <Tag t={a.strength} />
      </div>
      <p className="text-[13px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text-primary)" }}>{a.argument}</p>
      <div className="mt-1.5"><Chips ids={a.sources} unsourced={a.unsourced} onCite={onCite} /></div>
    </div>
  );
}

function Courtroom({ out, onCite }: { out: CourtroomOutput; onCite: (id: string) => void }) {
  const [tab, setTab] = useState<"a" | "b" | "j">("j");
  const j = out.judge;
  const fav = (f: string) => (f === "A" ? tr("Favours Lawyer A") : f === "B" ? tr("Favours Lawyer B") : tr("Uncertain"));
  return (
    <div className="space-y-4" dir="auto">
      <div className="rounded-2xl border p-4 sm:p-5 space-y-3" style={{ borderColor: "var(--border-strong)", backgroundColor: "var(--bg-card)" }}>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          <Gavel className="w-4 h-4" /> {tr("The judge's assessment")}
        </div>
        <Gauge value={j.chance_of_success} confidence={j.confidence} />
        <p className="text-sm leading-relaxed font-medium" style={{ color: "var(--text-heading)" }}>{j.verdict}</p>
        <p className="text-[13px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{j.chance_reasoning}</p>
      </div>
      <div className="flex gap-1 p-1 rounded-xl" style={{ backgroundColor: "var(--bg-card)" }}>
        {([["a", tr("Lawyer A · your client")], ["b", tr("Lawyer B · the other side")], ["j", tr("Judge")]] as const).map(([k, l]) => (
          <button key={k} type="button" onClick={() => setTab(k)} className="flex-1 px-2 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors"
            style={{ backgroundColor: tab === k ? "var(--bg-surface)" : "transparent", color: tab === k ? "var(--text-heading)" : "var(--text-muted)" }}>{l}</button>
        ))}
      </div>
      {tab === "a" && (
        <div className="space-y-2.5 pro-fade-in">
          <p className="text-sm" style={{ color: "var(--text-primary)" }}>{out.lawyer_a.position}</p>
          {out.lawyer_a.arguments.map((a, i) => <ArgCard key={i} a={a} n={i + 1} onCite={onCite} accent="#1f7a4d" />)}
          {!!out.lawyer_a.evidence_needed?.length && <ListBox title={tr("Evidence your client must produce")} items={out.lawyer_a.evidence_needed} />}
        </div>
      )}
      {tab === "b" && (
        <div className="space-y-2.5 pro-fade-in">
          <p className="text-sm" style={{ color: "var(--text-primary)" }}>{out.lawyer_b.position}</p>
          {out.lawyer_b.rebuttals.map((r, i) => (
            <div key={i} className="rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)", borderInlineStartWidth: 3, borderInlineStartColor: "#a23a30" }}>
              <div className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>
                {tr("Against argument {0}", [r.target])}{out.lawyer_a.arguments[r.target - 1] ? ` · ${out.lawyer_a.arguments[r.target - 1].title}` : ""}
              </div>
              <p className="text-[13px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text-primary)" }}>{r.rebuttal}</p>
              <div className="mt-1.5"><Chips ids={r.sources} unsourced={r.unsourced} onCite={onCite} /></div>
            </div>
          ))}
          {out.lawyer_b.counter_arguments.map((a, i) => <ArgCard key={i} a={a} n={i + 1} onCite={onCite} accent="#a23a30" />)}
        </div>
      )}
      {tab === "j" && (
        <div className="space-y-2.5 pro-fade-in">
          {j.issues.map((it, i) => (
            <div key={i} className="rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="flex items-start gap-2 mb-1">
                <span className="text-sm font-medium flex-1" style={{ color: "var(--text-heading)" }}>{it.issue}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap"
                  style={{ backgroundColor: it.favours === "A" ? "rgba(34,139,84,.14)" : it.favours === "B" ? "rgba(190,60,50,.13)" : "var(--bg-card)",
                    color: it.favours === "A" ? "#1f7a4d" : it.favours === "B" ? "#a23a30" : "var(--text-muted)" }}>{fav(it.favours)}</span>
              </div>
              <p className="text-[13px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{it.finding}</p>
              <div className="mt-1.5"><Chips ids={it.sources} unsourced={it.unsourced} onCite={onCite} /></div>
            </div>
          ))}
          {!!j.risks.length && (
            <div className="rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="text-sm font-medium mb-1.5" style={{ color: "var(--text-heading)" }}>{tr("Risks")}</div>
              <ul className="space-y-1.5">{j.risks.map((r, i) => (
                <li key={i} className="text-[13px]" style={{ color: "var(--text-primary)" }}><AlertTriangle className="w-3.5 h-3.5 inline me-1" style={{ color: "#a23a30" }} />{r.risk} <Chips ids={r.sources} unsourced={r.unsourced} onCite={onCite} /></li>
              ))}</ul>
            </div>
          )}
          {!!j.recommendations.length && <ListBox title={tr("What to do")} items={j.recommendations} />}
          {!!j.what_would_change?.length && <ListBox title={tr("What would change the assessment")} items={j.what_would_change} />}
        </div>
      )}
    </div>
  );
}

function ListBox({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)" }}>
      <div className="text-sm font-medium mb-1.5" style={{ color: "var(--text-heading)" }}>{title}</div>
      <ul className="list-disc ps-5 space-y-1 text-[13px]" style={{ color: "var(--text-primary)" }}>{items.map((s, i) => <li key={i}>{s}</li>)}</ul>
    </div>
  );
}

function ArticleCard({ a, open }: { a: ArticleSource; open: boolean }) {
  const [o, setO] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (open) setO(true); }, [open]);
  return (
    <div id={`pro-src-${a.id}`} ref={ref} className="rounded-xl border p-2.5 transition-shadow"
      style={{ borderColor: open ? "var(--accent-primary)" : "var(--border-subtle)", boxShadow: open ? "0 0 0 2px var(--accent-primary)" : undefined }}>
      <button type="button" onClick={() => setO(!o)} className="w-full text-start cursor-pointer">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-code px-1 rounded" style={{ backgroundColor: "var(--bg-card)", color: "var(--accent-primary)" }}>{a.id}</span>
          <span className="text-xs font-medium truncate" style={{ color: "var(--text-heading)" }} dir="auto">{a.article}</span>
        </div>
        <div className="text-[11px] truncate mt-0.5" style={{ color: "var(--text-muted)" }} dir="auto">{a.law}</div>
      </button>
      {o && (
        <div className="mt-2 text-[12px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text-primary)" }} dir="auto">
          {a.text}
          {a.valid_from && <div className="text-[10px] mt-1.5" style={{ color: "var(--text-muted)" }}>{tr("In force from {0}", [a.valid_from])}{a.valid_to ? ` → ${a.valid_to}` : ""}</div>}
        </div>
      )}
    </div>
  );
}

function RulingList({ rulings, focus, big }: { rulings: RulingCard[]; focus: string | null; big?: boolean }) {
  if (!rulings.length) return null;
  return (
    <div className={big ? "space-y-3" : "space-y-2"}>
      {big && <h3 className="text-sm font-semibold" style={{ color: "var(--text-heading)" }}>{tr("Similar rulings")}</h3>}
      {rulings.map((r) => <RulingItem key={r.id} r={r} open={focus === r.id || !!big} />)}
    </div>
  );
}

function RulingItem({ r, open }: { r: RulingCard; open: boolean }) {
  const [o, setO] = useState(open);
  useEffect(() => { if (open) setO(true); }, [open]);
  const won = r.petitioner_won;
  return (
    <div id={`pro-src-${r.id}`} className="rounded-xl border p-2.5"
      style={{ borderColor: open ? "#5a46a0" : "var(--border-subtle)" }}>
      <button type="button" onClick={() => setO(!o)} className="w-full text-start cursor-pointer">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] font-code px-1 rounded" style={{ backgroundColor: "rgba(90,70,160,.13)", color: "#5a46a0" }}>{r.id}</span>
          <span className="text-xs font-medium" style={{ color: "var(--text-heading)" }}>{tr("Ruling {0}", [r.number || r.ruling_id])}</span>
          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.date}</span>
          {r.chamber && <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>· {tr(CHAMBER[r.chamber] || r.chamber)}</span>}
          {r.outcome && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium"
              style={{ backgroundColor: won ? "rgba(34,139,84,.14)" : won === false ? "rgba(190,60,50,.13)" : "var(--bg-card)", color: won ? "#1f7a4d" : won === false ? "#a23a30" : "var(--text-muted)" }}>
              {r.outcome_ar || r.outcome}
            </span>
          )}
        </div>
        <div className="text-[12px] mt-1 leading-snug line-clamp-2" style={{ color: "var(--text-primary)" }} dir="auto">{r.keywords}</div>
      </button>
      {o && (
        <div className="mt-2 space-y-2 text-[12px] leading-relaxed" style={{ color: "var(--text-primary)" }} dir="auto">
          {r.principle && <p><b>{tr("Principle")}: </b>{r.principle}</p>}
          {r.grounds.map((g, i) => (
            <div key={i} className="rounded-lg p-2" style={{ backgroundColor: "var(--bg-card)" }}>
              <div className="flex items-center gap-1.5 mb-0.5">
                <Tag t={g.accepted === true ? "won" : g.accepted === false ? "lost" : undefined} />
                {g.accepted == null && <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{tr("Not examined")}</span>}
              </div>
              <div className="line-clamp-4">{g.ground}</div>
              {g.answer && <div className="mt-1 line-clamp-4" style={{ color: "var(--text-muted)" }}>↳ {g.answer}</div>}
            </div>
          ))}
          {r.verdict && <p style={{ color: "var(--text-muted)" }}>{r.verdict}</p>}
          {r.source_url && (
            <a href={r.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px]" style={{ color: "#5a46a0" }}>
              <ExternalLink className="w-3 h-3" />{tr("Ruling PDF")}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function Note({ text }: { text: string }) {
  return <div className="rounded-xl border px-3 py-2 text-xs" style={{ borderColor: "rgba(196,140,32,.4)", backgroundColor: "rgba(196,140,32,.08)", color: "var(--text-primary)" }}>{text}</div>;
}
function ErrorBox({ text }: { text: string }) {
  return <div className="rounded-xl border px-3 py-2 text-xs" style={{ borderColor: "rgba(190,60,50,.4)", backgroundColor: "rgba(190,60,50,.07)", color: "#a23a30" }}>{text}</div>;
}
function Spinner({ text }: { text: string }) {
  return <div className="flex items-center gap-2 text-sm py-10 justify-center" style={{ color: "var(--text-muted)" }}><Loader2 className="w-4 h-4 animate-spin" />{text}</div>;
}

// ---------------------------------------------------------------------------------------------------- export
function toArtifact(r: ProResult, tool: ProTool, pick: (l?: L3) => string): ArtifactItem {
  const cite = (ids: string[]) => (ids.length ? ` [${ids.join(", ")}]` : "");
  const lines: string[] = [`# ${pick(tool.label)}`, "", `*${tr("Law in force on {0}", [r.as_of])}*`, ""];
  if (r.kind === "courtroom" && r.output) {
    const o = r.output as CourtroomOutput;
    lines.push(`## ${tr("The judge's assessment")}`, "", `**${tr("Estimated chance of success")}: ${o.judge.chance_of_success}%** (${tr("Confidence: {0}", [tr(o.judge.confidence)])})`, "",
      o.judge.verdict, "", o.judge.chance_reasoning, "");
    o.judge.issues.forEach((i) => lines.push(`- **${i.issue}**: ${i.finding}${cite(i.sources)}`));
    lines.push("", `## ${tr("Lawyer A · your client")}`, "", o.lawyer_a.position, "");
    o.lawyer_a.arguments.forEach((a, i) => lines.push(`${i + 1}. **${a.title}** (${tr(TAG_STYLE[a.strength]?.label || a.strength)}): ${a.argument}${cite(a.sources)}`));
    lines.push("", `## ${tr("Lawyer B · the other side")}`, "", o.lawyer_b.position, "");
    o.lawyer_b.rebuttals.forEach((b) => lines.push(`- ${tr("Against argument {0}", [b.target])}: ${b.rebuttal}${cite(b.sources)}`));
    o.lawyer_b.counter_arguments.forEach((a) => lines.push(`- **${a.title}**: ${a.argument}${cite(a.sources)}`));
    lines.push("", `## ${tr("Risks")}`, "");
    o.judge.risks.forEach((x) => lines.push(`- ${x.risk}${cite(x.sources)}`));
    lines.push("", `## ${tr("What to do")}`, "");
    o.judge.recommendations.forEach((x) => lines.push(`- ${x}`));
  } else if (r.output) {
    const o = r.output as ReportOutput;
    lines.push(`## ${o.title}`, "", o.summary, "");
    o.sections.forEach((s) => { if (s.items?.length) { lines.push(`### ${s.heading}`, ""); s.items.forEach((it) => lines.push(`- ${it.text}${cite(it.sources)}`)); lines.push(""); } });
  }
  lines.push("", `## ${tr("Sources")}`, "");
  r.articles.forEach((a) => lines.push(`- **${a.id}** ${a.law}, ${a.article}`));
  r.rulings.forEach((x) => lines.push(`- **${x.id}** ${tr("Ruling {0}", [x.number || x.ruling_id])}, ${x.date}, ${x.outcome_ar || x.outcome}: ${x.keywords}`));
  lines.push("", `> ${r.notice}`);
  return {
    id: `pro-${Date.now()}`, title: pick(tool.label), kind: ArtifactKind.Markdown, language: "markdown",
    summary: tr("Law in force on {0}", [r.as_of]), content: lines.join("\n"), createdAt: new Date().toISOString(),
  };
}
