import React, { useEffect, useMemo, useState } from "react";
import { tr } from "../i18n";
import { getStatus } from "../api/legalrag";
import { entriesToMappings, rulesToTerms, useServerMasking } from "../api/useServerMasking";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronRight,
  Copy,
  Eye,
  EyeOff,
  FileText,
  KeyRound,
  Lock,
  RotateCcw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  X,
} from "lucide-react";
import { AttachmentItem, PseudonymMapping } from "../types/agent";
import { estimateTokenCount, scanAndDetectEntities } from "../utils/pseudonymiser";

interface SendPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmSend: (finalText: string) => void;
  rawText: string;
  attachments: AttachmentItem[];
  mappings: PseudonymMapping[];
  autoPseudonymise: boolean;
  onToggleAutoPseudonymise: (val: boolean) => void;
  alwaysPreview: boolean;
  onToggleAlwaysPreview: (val: boolean) => void;
  onOpenPseudonymiser: () => void;
  onAddMappings: (rules: PseudonymMapping[]) => void;
  modelName?: string;
  thinkingBudget?: number;
}

export const SendPreviewModal: React.FC<SendPreviewModalProps> = ({
  isOpen,
  onClose,
  onConfirmSend,
  rawText,
  attachments,
  mappings,
  autoPseudonymise,
  onToggleAutoPseudonymise,
  alwaysPreview,
  onToggleAlwaysPreview,
  onOpenPseudonymiser,
  onAddMappings,
  modelName = "gemini-3.8-flash",
  thinkingBudget = 8000,
}) => {
  const [viewTab, setViewTab] = useState<"pseudonymised" | "raw" | "attachments">(
    "pseudonymised"
  );
  const [copied, setCopied] = useState(false);

  // ONE masking engine: the local backend (same detectors as the real send). Your saved rules are forwarded to it.
  const server = useServerMasking(rawText, autoPseudonymise ? rulesToTerms(mappings) : [], isOpen);
  const [cloudLabel, setCloudLabel] = useState<string>(tr("the local backend"));
  useEffect(() => {
    if (!isOpen) return;
    getStatus()
      .then((st) => {
        const llm = (st as unknown as { providers?: { llm?: { provider: string; model: string } | null } }).providers?.llm;
        setCloudLabel(llm ? `${llm.provider}/${llm.model} (mode ${st.mode})` : tr("no cloud model configured (mode {0}): nothing leaves the device", [st.mode]));
      })
      .catch(() => setCloudLabel(tr("the local backend (unreachable)")));
  }, [isOpen]);

  const serverError = server.error;
  const serverPreview = server.masked !== null ? { warnings: server.warnings } : null;
  const serverCount = server.entries.length;
  const replacedCount = serverCount;
  const shownReplaced = serverCount;
  const shownPayload = autoPseudonymise ? (server.masked ?? rawText) : rawText;
  const activePayloadText = rawText; // what is submitted: the backend masks it again, identically
  const appliedMappings: PseudonymMapping[] = server.entries.map((e, i) => ({
    id: `srv-${i}`, original: e.original, replacement: e.placeholder, category: e.category, active: true,
  }));
  const unsavedEntries = server.entries.filter(
    (e) => !mappings.some((m) => m.original.trim().toLowerCase() === e.original.trim().toLowerCase())
  );
  // Leftovers: things the local heuristic scanner sees that are still visible in the masked payload.
  const unmaskedFindings = useMemo(
    () => scanAndDetectEntities(rawText, mappings).filter((f) => (server.masked ?? rawText).toLowerCase().includes(f.original.toLowerCase())),
    [rawText, mappings, server.masked]
  );
  const estimatedTokens = useMemo(() => {
    const textTokens = estimateTokenCount(activePayloadText);
    const attTokens = attachments.reduce((sum, att) => {
      if (att.textContent) return sum + estimateTokenCount(att.textContent);
      if (att.dataUrl) return sum + 258; // standard image token estimate
      return sum + 50;
    }, 0);
    return textTokens + attTokens;
  }, [activePayloadText, attachments]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(activePayloadText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore clipboard error
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Modal Card */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="send-preview-title"
        className="relative w-full max-w-2xl rounded-2xl sm:rounded-3xl border shadow-2xl overflow-hidden flex flex-col max-h-[92vh] z-10 sanad-liquid-modal"
        style={{
          backgroundColor: "var(--bg-surface)",
          borderColor: "var(--border-strong)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-3.5 border-b shrink-0"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
              style={{
                backgroundColor: "var(--bg-muted)",
                color: "var(--accent-warm)",
              }}
            >
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2
                id="send-preview-title"
                className="font-editorial text-sm sm:text-base font-semibold leading-tight"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Send Payload & Privacy Inspection")}
              </h2>
              <div
                className="text-[11px] font-code"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Review exact content dispatched to")} {cloudLabel}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label={tr("Close send preview")}
            className="p-1.5 rounded-lg opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Security & Token Banner */}
        <div
          className="px-5 py-3 border-b flex flex-wrap items-center justify-between gap-3 text-xs"
          style={{
            backgroundColor: "var(--bg-canvas)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-code text-[11px] font-semibold tracking-wide"
              style={{
                backgroundColor: autoPseudonymise
                  ? "rgba(16, 185, 129, 0.12)"
                  : "rgba(239, 68, 68, 0.12)",
                color: autoPseudonymise ? "#10B981" : "#EF4444",
              }}
            >
              {autoPseudonymise ? (
                <>
                  <ShieldCheck className="w-3.5 h-3.5" />
                  {tr("Shield Active (")}{shownReplaced} {tr("Replaced)")}
                </>
              ) : (
                <>
                  <ShieldAlert className="w-3.5 h-3.5" />
                  {tr("Raw Text (Pseudonymiser Off)")}
                </>
              )}
            </span>

            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-code text-[11px]"
              style={{
                backgroundColor: "var(--bg-muted)",
                color: "var(--text-muted)",
              }}
            >
              ~{estimatedTokens.toLocaleString()} {tr("tokens")}
            </span>


          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onToggleAutoPseudonymise(!autoPseudonymise)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border cursor-pointer hover:opacity-85 transition-opacity"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              {autoPseudonymise ? (
                <>
                  <EyeOff className="w-3 h-3" />
                  <span>{tr("Disable Masking")}</span>
                </>
              ) : (
                <>
                  <Eye className="w-3 h-3" />
                  <span>{tr("Enable Masking")}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* View Tabs */}
        <div
          className="flex items-center justify-between px-5 pt-3 border-b"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setViewTab("pseudonymised")}
              className={`pb-2.5 text-xs font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-1.5 ${
                viewTab === "pseudonymised"
                  ? "border-[var(--accent-primary)] text-[var(--text-heading)] font-semibold"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              <Shield className="w-3.5 h-3.5" />
              <span>{tr("Model Payload View")}</span>
              {autoPseudonymise && replacedCount > 0 && (
                <span
                  className="px-1.5 py-0.2 rounded-full text-[10px] font-code"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {replacedCount}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setViewTab("raw")}
              className={`pb-2.5 text-xs font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-1.5 ${
                viewTab === "raw"
                  ? "border-[var(--accent-primary)] text-[var(--text-heading)] font-semibold"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span>{tr("Original Input")}</span>
            </button>

            {attachments.length > 0 && (
              <button
                type="button"
                onClick={() => setViewTab("attachments")}
                className={`pb-2.5 text-xs font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-1.5 ${
                  viewTab === "attachments"
                    ? "border-[var(--accent-primary)] text-[var(--text-heading)] font-semibold"
                    : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span>{tr("Attachments (")}{attachments.length})</span>
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1 text-[11px] pb-2 cursor-pointer hover:opacity-80"
            style={{ color: "var(--text-muted)" }}
          >
            {copied ? (
              <>
                <Check className="w-3 h-3 text-emerald-500" />
                <span className="text-emerald-500 font-medium">{tr("Copied")}</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3" />
                <span>{tr("Copy Payload")}</span>
              </>
            )}
          </button>
        </div>

        {/* Payload Content Area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {viewTab === "pseudonymised" && (
            <div className="space-y-3">
              <div
                className="p-4 rounded-xl font-code text-xs leading-relaxed whitespace-pre-wrap border select-text max-h-72 overflow-y-auto"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              >
                {shownPayload || (
                  <span className="italic opacity-50">{tr("Empty prompt body")}</span>
                )}
              </div>

              {/* Applied Pseudonym Mapping Badges */}
              {appliedMappings.length > 0 ? (
                <div className="space-y-1.5">
                  <div
                    className="text-[11px] font-semibold uppercase tracking-wider flex items-center justify-between"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <span>{tr("Masked Identity Tokens in This Request")}</span>
                    <span className="flex items-center gap-3">
                      {unsavedEntries.length > 0 && (
                        <button
                          type="button"
                          onClick={() => onAddMappings(entriesToMappings(unsavedEntries, mappings))}
                          className="text-[11px] normal-case tracking-normal font-medium underline cursor-pointer hover:opacity-80"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          {tr("Save")} {unsavedEntries.length} {tr("to rules")}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={onOpenPseudonymiser}
                        className="inline-flex items-center gap-1 text-[11px] lowercase tracking-normal font-normal hover:underline cursor-pointer"
                        style={{ color: "var(--accent-primary)" }}
                      >
                        <span>{tr("Manage rules in panel")}</span>
                        <ArrowRight className="w-3 h-3" />
                      </button>
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {appliedMappings.map((m) => (
                      <div
                        key={m.id}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs"
                        style={{
                          backgroundColor: "var(--bg-surface)",
                          borderColor: "var(--border-subtle)",
                        }}
                      >
                        <span
                          className="line-through opacity-60 font-medium"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {m.original}
                        </span>
                        <ChevronRight
                          className="w-3 h-3 opacity-40 shrink-0"
                          style={{ color: "var(--text-muted)" }}
                        />
                        <span
                          className="font-code font-bold"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          {m.replacement}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div
                  className="p-3 rounded-xl border text-xs flex items-center gap-2.5"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-muted)",
                  }}
                >
                  <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
                  <span>
                    {serverError
                      ? tr("Local backend unreachable ({0}): only your own rules were checked.", [serverError])
                      : serverCount > 0
                      ? tr("The local backend masked {0} item(s) (names, phone numbers, IDs). Review the payload above.", [serverCount])
                      : tr("No names or identifiers were detected by your rules or the local backend. Check the text once more before sending.")}
                  </span>
                  {serverPreview?.warnings.map((w, i) => (
                    <span key={i} style={{ color: "var(--accent-warm)" }}> ⚠ {w}</span>
                  ))}
                </div>
              )}

              {/* Unmasked PII Warnings if any */}
              {unmaskedFindings.length > 0 && (
                <div
                  className="p-3.5 rounded-xl border space-y-2"
                  style={{
                    backgroundColor: "rgba(245, 158, 11, 0.08)",
                    borderColor: "rgba(245, 158, 11, 0.3)",
                  }}
                >
                  <div className="flex items-center justify-between text-xs font-semibold text-amber-700 dark:text-amber-300">
                    <span className="flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      {tr("Potential Unmasked Entities Detected (")}{unmaskedFindings.length})
                    </span>
                    <button
                      type="button"
                      onClick={() => onAddMappings(unmaskedFindings)}
                      className="text-[11px] underline cursor-pointer hover:opacity-80"
                    >
                      {tr("Add to Rules")}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {unmaskedFindings.map((f) => (
                      <span
                        key={f.id}
                        className="px-2 py-0.5 rounded text-[11px] font-code bg-amber-500/15 text-amber-800 dark:text-amber-200 border border-amber-500/25"
                      >
                        {f.original} ({f.category})
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {viewTab === "raw" && (
            <div
              className="p-4 rounded-xl font-code text-xs leading-relaxed whitespace-pre-wrap border select-text max-h-72 overflow-y-auto"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              {rawText || (
                <span className="italic opacity-50">{tr("Empty prompt body")}</span>
              )}
            </div>
          )}

          {viewTab === "attachments" && (
            <div className="space-y-2.5">
              {attachments.map((att) => (
                <div
                  key={att.id}
                  className="flex items-center justify-between p-3 rounded-xl border text-xs"
                  style={{
                    backgroundColor: "var(--bg-canvas)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {att.dataUrl ? (
                      <img
                        src={att.dataUrl}
                        alt={att.name}
                        className="w-8 h-8 rounded-lg object-cover border shrink-0"
                        style={{ borderColor: "var(--border-subtle)" }}
                      />
                    ) : (
                      <div
                        className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--accent-primary)",
                        }}
                      >
                        <FileText className="w-4 h-4" />
                      </div>
                    )}
                    <div className="min-w-0">
                      <div
                        className="font-medium truncate"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {att.name}
                      </div>
                      <div
                        className="font-code text-[11px]"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {(att.sizeBytes / 1024).toFixed(1)} {tr("KB ·")} {att.mimeType}
                      </div>
                    </div>
                  </div>
                  <span
                    className="font-code text-[11px] px-2 py-0.5 rounded"
                    style={{
                      backgroundColor: "var(--bg-surface)",
                      color: "var(--text-muted)",
                    }}
                  >
                    {tr("Included")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div
          className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 border-t shrink-0"
          style={{
            backgroundColor: "var(--bg-canvas)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
            <input
              type="checkbox"
              checked={alwaysPreview}
              onChange={(e) => onToggleAlwaysPreview(e.target.checked)}
              className="rounded accent-[var(--accent-primary)] cursor-pointer"
            />
            <span style={{ color: "var(--text-muted)" }}>
              {tr("Always show preview before sending")}
            </span>
          </label>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-2 rounded-xl text-xs font-medium border hover:opacity-80 transition-opacity cursor-pointer"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              {tr("Edit Prompt")}
            </button>

            <button
              type="button"
              onClick={() => {
                onConfirmSend(activePayloadText);
                onClose();
              }}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold hover:opacity-95 transition-all shadow-xs cursor-pointer"
              style={{
                backgroundColor: "var(--accent-primary)",
                color: "var(--accent-primary-fg)",
              }}
            >
              <span>{tr("Send Payload Now")}</span>
              <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
