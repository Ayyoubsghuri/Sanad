import React, { useState } from "react";
import { tr } from "../i18n";
import {
  ShieldCheck,
  Trash2,
  Lock,
  CheckCircle2,
  X,
  Scale,
} from "lucide-react";
import { AuditTraceRecord } from "../types/agent";

interface AuditTraceModalProps {
  isOpen: boolean;
  onClose: () => void;
  auditLogs: AuditTraceRecord[];
  onWipeAuditLogs: () => void;
}

export function AuditTraceModal({
  isOpen,
  onClose,
  auditLogs,
  onWipeAuditLogs,
}: AuditTraceModalProps) {
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(
    auditLogs[0]?.id || null
  );

  if (!isOpen) return null;

  const activeRecord =
    auditLogs.find((l) => l.id === selectedRecordId) || auditLogs[0] || null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5"
      style={{ backgroundColor: "rgba(27, 22, 20, 0.55)" }}
    >
      <div
        className="relative w-full max-w-5xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[90vh] sanad-liquid-modal"
        style={{
          backgroundColor: "var(--bg-surface)",
          borderColor: "var(--border-strong)",
        }}
      >
        {/* Header */}
        <div
          className="p-5 sm:p-6 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{
                backgroundColor: "var(--bg-card)",
                color: "var(--accent-primary)",
              }}
            >
              <Scale className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2
                  className="text-lg font-editorial font-medium"
                  style={{ color: "var(--text-heading)" }}
                >
                  {tr("Journal d'Audit Local & Contrôle NLI")}
                </h2>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-md font-medium"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {tr("Zéro Télémétrie Externe")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Traçabilité souveraine des requêtes, vérifications d'inférence (NLI Premise-Hypothesis) et destruction en 1 clic.")}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left: Log Entries */}
          <div
            className="w-full md:w-80 border-r overflow-y-auto p-3 space-y-2"
            style={{
              borderColor: "var(--border-subtle)",
              backgroundColor: "var(--bg-canvas)",
            }}
          >
            <div
              className="flex items-center justify-between pb-2 border-b"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <span
                className="text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Historique (")}{auditLogs.length})
              </span>
              <button
                type="button"
                onClick={onWipeAuditLogs}
                className="text-[11px] font-medium flex items-center gap-1 cursor-pointer hover:opacity-80 transition-opacity"
                style={{ color: "var(--accent-primary)" }}
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{tr("Effacer tout")}</span>
              </button>
            </div>

            {auditLogs.length === 0 ? (
              <div
                className="p-6 text-center text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Aucun journal enregistré. Les requêtes sont conservées uniquement en mémoire locale.")}
              </div>
            ) : (
              auditLogs.map((log) => {
                const isSelected = log.id === activeRecord?.id;
                return (
                  <button
                    key={log.id}
                    type="button"
                    onClick={() => setSelectedRecordId(log.id)}
                    className="w-full text-left p-3 rounded-xl transition-all border cursor-pointer"
                    style={{
                      backgroundColor: isSelected
                        ? "var(--bg-card)"
                        : "transparent",
                      borderColor: isSelected
                        ? "var(--accent-warm)"
                        : "transparent",
                      color: "var(--text-primary)",
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span
                        className="text-[10px] font-code"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {log.timestamp}
                      </span>
                      <span
                        className="text-[10px] font-semibold px-1.5 py-0.2 rounded"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--accent-primary)",
                        }}
                      >
                        {tr("NLI :")} {log.verification.overallStatus.toUpperCase()}
                      </span>
                    </div>
                    <div
                      className="text-xs font-medium truncate mb-1"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {log.pseudonymisedQuery}
                    </div>
                    <div
                      className="flex items-center justify-between text-[10px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span>{tr("Mode:")} {log.operatingMode}</span>
                      <span>{tr("Support:")} {log.verification.claimSupportRate}%</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Right: Record details & NLI breakdown */}
          <div
            className="flex-1 overflow-y-auto p-6 space-y-6"
            style={{ backgroundColor: "var(--bg-surface)" }}
          >
            {activeRecord ? (
              <>
                <div
                  className="pb-4 border-b flex items-center justify-between"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <div>
                    <span
                      className="text-[10px] font-code block"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("ID TRACE :")} {activeRecord.id}
                    </span>
                    <h3
                      className="text-base font-editorial font-semibold mt-0.5"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {tr("Contrôle de Véracité NLI & Audit des Données Sortantes")}
                    </h3>
                  </div>
                  <div className="text-right">
                    <span
                      className="text-xs block"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Date de référence légale")}
                    </span>
                    <strong
                      className="text-xs font-code font-semibold"
                      style={{ color: "var(--accent-warm)" }}
                    >
                      {activeRecord.asOfDate}
                    </strong>
                  </div>
                </div>

                {/* 5-Point Verification Grid */}
                <div>
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-1.5"
                    style={{ color: "var(--text-heading)" }}
                  >
                    <ShieldCheck className="w-4 h-4" style={{ color: "var(--accent-warm)" }} />
                    {tr("Rapport de Vérification Anti-Hallucination (5 Points Clés)")}
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <div
                      className="p-3 rounded-lg border space-y-1"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Citation Valide")}</span>
                        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                      </div>
                      <span className="text-xs font-semibold block" style={{ color: "var(--text-heading)" }}>
                        {activeRecord.verification.citationExists ? tr("Conforme BO") : tr("Non trouvé")}
                      </span>
                    </div>

                    <div
                      className="p-3 rounded-lg border space-y-1"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Citation Exacte")}</span>
                        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                      </div>
                      <span className="text-xs font-semibold block" style={{ color: "var(--text-heading)" }}>
                        {activeRecord.verification.quoteMatches ? tr("100% Fidèle") : "Divergence"}
                      </span>
                    </div>

                    <div
                      className="p-3 rounded-lg border space-y-1"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Pseudonymes Intacts")}</span>
                        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                      </div>
                      <span className="text-xs font-semibold block" style={{ color: "var(--text-heading)" }}>
                        {activeRecord.verification.placeholdersIntact ? tr("Zéro fuite PII") : "Alerte"}
                      </span>
                    </div>

                    <div
                      className="p-3 rounded-lg border space-y-1"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Version Temporelle")}</span>
                        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                      </div>
                      <span className="text-xs font-semibold block" style={{ color: "var(--text-heading)" }}>
                        {activeRecord.verification.versionValid ? "Applicable" : tr("Périmée")}
                      </span>
                    </div>

                    <div
                      className="p-3 rounded-lg border space-y-1"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Chiffres Déterministes")}</span>
                        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                      </div>
                      <span className="text-xs font-semibold block" style={{ color: "var(--text-heading)" }}>
                        {activeRecord.verification.noStrayNumbers ? tr("Calculateur Pur") : tr("Nombre libre")}
                      </span>
                    </div>

                    <div
                      className="p-3 rounded-lg border space-y-1"
                      style={{
                        backgroundColor: "var(--bg-card)",
                        borderColor: "var(--accent-warm)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Taux Support NLI")}</span>
                        <span className="font-bold text-xs" style={{ color: "var(--accent-warm)" }}>
                          {activeRecord.verification.claimSupportRate}%
                        </span>
                      </div>
                      <span className="text-xs font-semibold block" style={{ color: "var(--text-heading)" }}>
                        {tr("Implication Formelle")}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sanitized outbound payload */}
                <div>
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider mb-2 flex items-center justify-between"
                    style={{ color: "var(--text-heading)" }}
                  >
                    <span>{tr("Charge Utile Sortante Réseau (Inspectée)")}</span>
                    <span className="text-[10px] font-code" style={{ color: "var(--text-muted)" }}>
                      {activeRecord.rawQuestionLength} {tr("car. anonymisés")}
                    </span>
                  </h4>
                  <pre
                    className="p-3 rounded-xl text-[11px] font-code overflow-x-auto max-h-40 border"
                    style={{
                      backgroundColor: "var(--bg-canvas)",
                      borderColor: "var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {activeRecord.outboundPayloadJson}
                  </pre>
                </div>

                {/* Retrieved legal chunks provenance */}
                <div>
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider mb-2"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {tr("Extraits de Textes Officiels Mobilisés (")}{activeRecord.retrievedChunkIds.length})
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {activeRecord.retrievedChunkIds.map((chunkId, idx) => (
                      <span
                        key={idx}
                        className="text-xs px-2.5 py-1 rounded border font-code"
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          borderColor: "var(--border-subtle)",
                          color: "var(--text-heading)",
                        }}
                      >
                        {chunkId}
                      </span>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div
                className="text-center py-12 text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Sélectionnez une entrée dans le journal à gauche pour inspecter le détail.")}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          className="p-4 border-t flex items-center justify-between"
          style={{
            borderColor: "var(--border-subtle)",
            backgroundColor: "var(--bg-canvas)",
          }}
        >
          <div
            className="text-xs flex items-center gap-1.5"
            style={{ color: "var(--text-muted)" }}
          >
            <Lock className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
            <span>{tr("Chiffrement client AES-GCM 256 bits — Zéro traçage publicitaire ou analytique")}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-semibold shadow-xs cursor-pointer hover:opacity-90 transition-opacity"
            style={{
              backgroundColor: "var(--accent-primary)",
              color: "var(--accent-primary-fg)",
            }}
          >
            {tr("Fermer")}
          </button>
        </div>
      </div>
    </div>
  );
}
