import React, { useState } from "react";
import { tr } from "../i18n";
import { AlertTriangle, ShieldCheck, X } from "lucide-react";
import { reviewDocument, type IngestResult } from "../api/documents";

interface Props {
  docs: IngestResult[];
  onResolve: (confirmed: IngestResult[] | null) => void; // null = cancelled
}

/**
 * Shown before an attachment is used. The user sees the MASKED text (what the backend may send as excerpts), can add names the
 * detector missed, and must confirm. Nothing from the attachment is used until then.
 */
export const DocumentReviewModal: React.FC<Props> = ({ docs, onResolve }) => {
  const [state, setState] = useState<Record<string, { preview: string; confidence: number; warnings: string[]; terms: string; busy: boolean; error: string }>>(
    () =>
      Object.fromEntries(
        docs.map((d) => [d.doc_id, { preview: d.pseudonymised_preview, confidence: d.confidence, warnings: d.warnings, terms: "", busy: false, error: "" }])
      )
  );
  const [confirming, setConfirming] = useState(false);

  const patch = (id: string, p: Partial<(typeof state)[string]>) => setState((s) => ({ ...s, [id]: { ...s[id], ...p } }));
  const termsOf = (id: string) => state[id].terms.split(/[,\n;]+/).map((t) => t.trim()).filter((t) => t.length >= 2);

  const recheck = async (d: IngestResult) => {
    patch(d.doc_id, { busy: true, error: "" });
    try {
      const r = await reviewDocument(d.doc_id, termsOf(d.doc_id), false);
      patch(d.doc_id, { preview: r.pseudonymised_preview, confidence: r.confidence, warnings: r.warnings, busy: false });
    } catch (e) {
      patch(d.doc_id, { busy: false, error: (e as Error).message });
    }
  };

  const confirmAll = async () => {
    setConfirming(true);
    try {
      for (const d of docs) await reviewDocument(d.doc_id, termsOf(d.doc_id), true);
      onResolve(docs);
    } catch (e) {
      setConfirming(false);
      patch(docs[0].doc_id, { error: (e as Error).message });
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-3 sm:p-5">
      <div className="fixed inset-0 bg-black/65" />
      <div
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-2xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[92vh] z-10"
        style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-strong)" }}
      >
        <div className="flex items-center justify-between px-5 py-3.5 border-b" style={{ borderColor: "var(--border-subtle)" }}>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4" style={{ color: "var(--accent-warm)" }} />
            <h2 className="font-editorial text-base font-semibold" style={{ color: "var(--text-heading)" }}>{tr("Review attachments before use")}</h2>
          </div>
          <button type="button" onClick={() => onResolve(null)} aria-label={tr("Cancel")} className="p-1.5 rounded-lg opacity-60 hover:opacity-100 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            {tr("Only the masked text below can ever leave your device, and only short excerpts relevant to your question. Add any names or details the detector missed (comma-separated), re-check, then confirm.")}
          </p>
          {docs.map((d) => {
            const st = state[d.doc_id];
            return (
              <div key={d.doc_id} className="rounded-xl border p-3.5 space-y-2.5" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-canvas)" }}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold" style={{ color: "var(--text-heading)" }}>{d.filename}{d.sensitive ? tr(" (from vault)") : ""}</span>
                  <span className="font-code" style={{ color: "var(--text-muted)" }}>{tr("detection confidence")} {(st.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="p-3 rounded-lg border font-code text-xs leading-relaxed whitespace-pre-wrap max-h-56 overflow-y-auto select-text" style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}>
                  {st.preview}
                </div>
                {st.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-[11px]" style={{ color: "var(--accent-warm)" }}>
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>{w}</span>
                  </div>
                ))}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={st.terms}
                    onChange={(e) => patch(d.doc_id, { terms: e.target.value })}
                    placeholder={tr("Names or details to mask, e.g. Atlas, Hay Salam")}
                    className="flex-1 px-3 py-1.5 rounded-lg border bg-transparent text-xs"
                    style={{ borderColor: "var(--border-subtle)" }}
                  />
                  <button type="button" disabled={st.busy || termsOf(d.doc_id).length === 0} onClick={() => recheck(d)} className="px-3 py-1.5 rounded-lg border text-xs cursor-pointer hover:opacity-85 disabled:opacity-40" style={{ borderColor: "var(--border-strong)" }}>
                    {st.busy ? tr("Checking…") : tr("Mask and re-check")}
                  </button>
                </div>
                {st.error && <div className="text-xs text-red-500">{st.error}</div>}
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t" style={{ borderColor: "var(--border-subtle)" }}>
          <button type="button" onClick={() => onResolve(null)} className="px-4 py-2 rounded-xl border text-xs cursor-pointer hover:opacity-85" style={{ borderColor: "var(--border-subtle)" }}>
            {tr("Cancel (send nothing)")}
          </button>
          <button
            type="button"
            disabled={confirming}
            onClick={confirmAll}
            className="px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer hover:opacity-90"
            style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" }}
          >
            {confirming ? tr("Confirming…") : tr("Confirm masked text and continue")}
          </button>
        </div>
      </div>
    </div>
  );
};
