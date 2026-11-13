import React, { useState } from "react";
import { tr } from "../i18n";
import {
  Printer,
  X,
  FileText,
  Scale,
  CheckCircle2,
} from "lucide-react";
import { MOROCCAN_BAR_ASSOCIATIONS } from "../data/moroccanLawData";
import { CitizenSituation } from "../types/agent";

interface ConsultationPrepModalProps {
  isOpen: boolean;
  onClose: () => void;
  situation?: CitizenSituation | null;
  asOfDate: string;
}

export function ConsultationPrepModal({
  isOpen,
  onClose,
  situation,
  asOfDate,
}: ConsultationPrepModalProps) {
  const [clientName, setClientName] = useState("Salarié / Demandeur");
  const [selectedBarCity, setSelectedBarCity] = useState("Casablanca");
  const [factsSummary, setFactsSummary] = useState(
    situation?.description ||
      "Rupture abusive du contrat de travail intervenue sans préavis ni notification écrite des motifs légaux de licenciement."
  );

  if (!isOpen) return null;

  const activeBar =
    MOROCCAN_BAR_ASSOCIATIONS.find((b) => b.city === selectedBarCity) ||
    MOROCCAN_BAR_ASSOCIATIONS[0];

  const handlePrint = () => {
    window.print();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 print:p-0 print:static"
      style={{ backgroundColor: "rgba(27, 22, 20, 0.55)" }}
    >
      <div
        className="relative w-full max-w-4xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[90vh] print:max-h-none print:shadow-none print:border-none sanad-liquid-modal"
        style={{
          backgroundColor: "var(--bg-surface)",
          borderColor: "var(--border-strong)",
        }}
      >
        {/* Header - Screen only */}
        <div
          className="print:hidden px-5 py-4 sm:px-6 sm:py-5 border-b flex items-center justify-between gap-3 min-w-0"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{
                backgroundColor: "var(--bg-card)",
                color: "var(--accent-primary)",
              }}
            >
              <FileText className="w-4 h-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h2
                  className="text-base sm:text-lg font-editorial font-medium truncate"
                  style={{ color: "var(--text-heading)" }}
                >
                  {tr("Dossier de Préparation Avocat")}
                </h2>
                <span
                  className="text-[10px] sm:text-[11px] px-2 py-0.5 rounded-md font-medium whitespace-nowrap shrink-0 inline-flex items-center"
                  style={{
                    backgroundColor: "var(--bg-card)",
                    color: "var(--accent-primary)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  {tr("Fiche de Synthèse")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5 truncate hidden sm:block"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Générez une fiche structurée reprenant chronologie, articles applicables, calculs et pièces justificatives.")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handlePrint}
              className="px-3.5 py-1.5 sm:py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 cursor-pointer hover:opacity-90 transition-opacity whitespace-nowrap shrink-0 shadow-xs"
              style={{
                backgroundColor: "var(--accent-primary)",
                color: "var(--accent-primary-fg)",
              }}
            >
              <Printer className="w-3.5 h-3.5 shrink-0" />
              <span>{tr("Imprimer / PDF")}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              title={tr("Fermer")}
              className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer shrink-0"
              style={{ color: "var(--text-muted)" }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Configuration toolbar - Screen only */}
        <div
          className="print:hidden px-6 py-3 border-b flex flex-wrap items-center justify-between gap-3 text-xs"
          style={{
            borderColor: "var(--border-subtle)",
            backgroundColor: "var(--bg-canvas)",
          }}
        >
          <div className="flex items-center gap-2">
            <span style={{ color: "var(--text-muted)" }}>{tr("Barreau compétent :")}</span>
            <select
              value={selectedBarCity}
              onChange={(e) => setSelectedBarCity(e.target.value)}
              className="p-1.5 rounded-lg border text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              {MOROCCAN_BAR_ASSOCIATIONS.map((b) => (
                <option key={b.city} value={b.city}>
                  {tr("Ordre des Avocats de")} {b.city}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span style={{ color: "var(--text-muted)" }}>{tr("Demandeur :")}</span>
            <input
              type="text"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder={tr("Nom ou pseudonyme")}
              className="p-1.5 rounded-lg border text-xs outline-none w-48"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            />
          </div>
        </div>

        {/* Printable 1-Page Content Container */}
        <div
          className="flex-1 overflow-y-auto p-8 space-y-6 print:p-0 print:m-0 print:bg-white print:text-black"
          style={{ backgroundColor: "var(--bg-surface)" }}
        >
          {/* Printable Official Header */}
          <div
            className="border-b-2 pb-4 flex items-start justify-between"
            style={{ borderColor: "var(--border-strong)" }}
          >
            <div>
              <span
                className="text-[10px] uppercase font-bold tracking-widest block"
                style={{ color: "var(--accent-warm)" }}
              >
                {tr("Royaume du Maroc — Ordre des Avocats de")} {activeBar.city}
              </span>
              <h1
                className="text-xl font-editorial font-bold mt-1"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("FICHE PRÉPARATOIRE À LA CONSULTATION JURIDIQUE")}
              </h1>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                {tr("Dossier technique établi conformément aux textes en vigueur au")} {asOfDate}
              </p>
            </div>
            <div className="text-right text-xs">
              <span
                className="font-code font-bold block"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("DATE :")} {new Date().toLocaleDateString("fr-MA")}
              </span>
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                {activeBar.court}
              </span>
            </div>
          </div>

          {/* Section 1: Identification & Chronology */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div
              className="p-3.5 rounded-xl border"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
              }}
            >
              <span
                className="font-semibold uppercase text-[10px] tracking-wider block mb-1"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Demandeur / Client")}
              </span>
              <div
                className="font-medium text-sm"
                style={{ color: "var(--text-heading)" }}
              >
                {clientName}
              </div>
              <div
                className="text-[11px] mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Résidence / Juridiction :")} {activeBar.court}
              </div>
            </div>

            <div
              className="p-3.5 rounded-xl border"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
              }}
            >
              <span
                className="font-semibold uppercase text-[10px] tracking-wider block mb-1"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Date de Référence Légale (As-Of Date)")}
              </span>
              <div
                className="font-code font-semibold text-sm"
                style={{ color: "var(--accent-warm)" }}
              >
                {asOfDate}
              </div>
              <div
                className="text-[11px] mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Régime procédural :")}{" "}
                {new Date(asOfDate) >= new Date("2026-08-24")
                  ? tr("Loi 58.25 (Nouveau CPC)")
                  : tr("Dahir 1-74-447 (1974)")}
              </div>
            </div>
          </div>

          {/* Section 2: Summary of Facts */}
          <div>
            <h2
              className="text-xs font-semibold uppercase tracking-wider mb-2 border-b pb-1"
              style={{
                borderColor: "var(--border-subtle)",
                color: "var(--text-heading)",
              }}
            >
              {tr("1. Exposé Sommaire des Faits")}
            </h2>
            <textarea
              rows={3}
              value={factsSummary}
              onChange={(e) => setFactsSummary(e.target.value)}
              className="w-full text-xs p-3 rounded-xl border outline-none leading-relaxed print:border-none print:p-0 print:resize-none"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          {/* Section 3: Governing Moroccan Statutes */}
          <div>
            <h2
              className="text-xs font-semibold uppercase tracking-wider mb-2 border-b pb-1"
              style={{
                borderColor: "var(--border-subtle)",
                color: "var(--text-heading)",
              }}
            >
              {tr("2. Textes & Fondements Juridiques Invoqués (Bulletin Officiel)")}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div
                className="p-3 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <span
                  className="font-medium block"
                  style={{ color: "var(--text-heading)" }}
                >
                  Code du Travail — Loi n° 65-99 (Art. 41, 51, 53)
                </span>
                <span
                  className="text-[11px] block mt-0.5"
                  style={{ color: "var(--text-muted)" }}
                >
                  {tr("Dahir n° 1-03-194 (BO n° 5167) — Indemnité légale de licenciement et forclusion de 90 jours (Art. 65).")}
                </span>
              </div>
              <div
                className="p-3 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <span
                  className="font-medium block"
                  style={{ color: "var(--text-heading)" }}
                >
                  Décret n° 2.25.983 — SMIG Légal 2026
                </span>
                <span
                  className="text-[11px] block mt-0.5"
                  style={{ color: "var(--text-muted)" }}
                >
                  {tr("Taux horaire légal fixé à 17,92 MAD/heure (base 3.422,72 MAD pour 191h de travail mensuel).")}
                </span>
              </div>
              <div
                className="p-3 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <span
                  className="font-medium block"
                  style={{ color: "var(--text-heading)" }}
                >
                  Code de Procédure Civile — Loi 58.25 / Dahir 1.74.447
                </span>
                <span
                  className="text-[11px] block mt-0.5"
                  style={{ color: "var(--text-muted)" }}
                >
                  {tr("Compétence territoriale du tribunal de première instance du lieu d'exécution du contrat de travail.")}
                </span>
              </div>
              <div
                className="p-3 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <span
                  className="font-medium block"
                  style={{ color: "var(--text-heading)" }}
                >
                  Dahir des Obligations et Contrats (DOC 1913)
                </span>
                <span
                  className="text-[11px] block mt-0.5"
                  style={{ color: "var(--text-muted)" }}
                >
                  {tr("Art. 230 & 264 — Force obligatoire des conventions et dommages-intérêts réparateurs.")}
                </span>
              </div>
            </div>
          </div>

          {/* Section 4: Document Checklist for the Lawyer */}
          <div>
            <h2
              className="text-xs font-semibold uppercase tracking-wider mb-2 border-b pb-1"
              style={{
                borderColor: "var(--border-subtle)",
                color: "var(--text-heading)",
              }}
            >
              {tr("3. Bordereau des Pièces Justificatives à Remettre à l'Avocat")}
            </h2>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
              {(situation?.documentsToBring || [
                tr("Contrat de travail initial signé et légalisé"),
                tr("12 derniers bulletins de paie certifiés"),
                tr("Relevé de carrière et déclaration d'affiliation CNSS"),
                tr("Copie de la lettre de licenciement ou mise en demeure"),
                tr("Relevés de compte bancaire attestant du versement des salaires"),
                tr("Copie intégrale de la Carte d'Identité Nationale (CIN)"),
              ]).map((doc, idx) => (
                <li
                  key={idx}
                  className="flex items-center gap-2 p-2 rounded-lg border"
                  style={{
                    backgroundColor: "var(--bg-canvas)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <CheckCircle2
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <span style={{ color: "var(--text-primary)" }}>{doc}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Section 5: Bar Association Contact Details */}
          <div
            className="p-4 rounded-xl border text-xs space-y-1.5"
            style={{
              backgroundColor: "var(--bg-canvas)",
              borderColor: "var(--border-subtle)",
            }}
          >
            <span
              className="font-semibold uppercase text-[10px] tracking-wider block"
              style={{ color: "var(--text-muted)" }}
            >
              {tr("4. Coordonnées de l'Ordre des Avocats Compétent")}
            </span>
            <div
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-1"
              style={{ color: "var(--text-heading)" }}
            >
              <div className="font-medium">
                {tr("Barreau de")} {activeBar.city} — {activeBar.court}
              </div>
              <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                {activeBar.address}
              </div>
            </div>
            <p className="text-[10px] italic pt-1" style={{ color: "var(--text-muted)" }}>
              {tr("Avertissement déontologique : Ce dossier est un instrument préparatoire de synthèse. La représentation en justice devant les tribunaux marocains requiert le mandat exprès d'un avocat inscrit au Barreau.")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
