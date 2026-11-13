import React, { useState } from "react";
import { tr } from "../i18n";
import {
  Calendar,
  CheckCircle2,
  Sparkles,
  BookOpen,
  Search,
  X,
  Scale,
} from "lucide-react";
import { FinderPanel, HistoryPanel, ContractPanel } from "./LawToolsPanels";
import { CONCORDANCE_RULES } from "../data/moroccanLawData";
import { useConcordance, useTransitionalRules } from "../api/useLawGuides";

interface ConcordanceWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyDate?: (dateStr: string) => void;
}

export function ConcordanceWizardModal({
  isOpen,
  onClose,
  onApplyDate,
}: ConcordanceWizardModalProps) {
  const [activeTab, setActiveTab] = useState<"wizard" | "finder" | "history" | "contract" | "table">("finder");
  const [searchTerm, setSearchTerm] = useState("");

  // Wizard State
  const [caseType, setCaseType] = useState<"civil" | "criminal" | "realestate" | "labor">("civil");
  const [filingDate, setFilingDate] = useState<string>("2026-06-15");
  const [claimAmount, setClaimAmount] = useState<number>(8500);

  const packRules = useConcordance(isOpen);
  const transitional = useTransitionalRules(filingDate, isOpen);

  if (!isOpen) return null;

  const filteredRules = [...CONCORDANCE_RULES, ...packRules].filter((r) => {
    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase();
    return (
      r.topic.toLowerCase().includes(q) ||
      r.oldArticle.toLowerCase().includes(q) ||
      r.newArticle.toLowerCase().includes(q) ||
      r.keyChange.toLowerCase().includes(q)
    );
  });

  // Wizard calculation
  const determineRegime = () => {
    const filingObj = new Date(filingDate);
    const aug24_2026 = new Date("2026-08-24");
    const dec08_2025 = new Date("2025-12-08");
    const jul01_2026 = new Date("2026-07-01");

    if (caseType === "civil") {
      const isPostAug2026 = filingObj >= aug24_2026;
      const appealableUnderOld = claimAmount > 5000;
      const appealableUnderNew = claimAmount > 10000;

      return {
        applicableLaw: isPostAug2026
          ? "Loi 58.25 (Nouveau Code de Procédure Civile)"
          : "Dahir 1-74-447 du 28 septembre 1974 (Ancien CPC)",
        effectiveDate: isPostAug2026 ? tr("24 Août 2026") : "En vigueur jusqu'au 23 Août 2026",
        status: isPostAug2026 ? tr("Nouveau Régime (Loi 58.25)") : tr("Ancien Régime (CPC 1974)"),
        isNew: isPostAug2026,
        summary: isPostAug2026
          ? tr("L'action ayant été initiée le {0} (après le 24 août 2026), la procédure est régie par la Loi 58.25. La notification électronique est légalement admise et le seuil de compétence en dernier ressort s'établit à 10.000 DH.", [filingDate])
          : tr("L'action ayant été introduite le {0} (avant le 24 août 2026), l'instance et ses voies de recours restent régies par le Dahir de 1974 en application du principe de non-rétroactivité des lois de procédure pour les instances en cours.", [filingDate]),
        appealStatus: isPostAug2026
          ? appealableUnderNew
            ? tr("Appel RECEVABLE (Montant de {0} DH > Seuil de 10.000 DH selon Art. 30 Loi 58.25)", [claimAmount.toLocaleString()])
            : tr("Jugement en DERNIER RESSORT (Montant de {0} DH ≤ 10.000 DH : Appel irrecevable)", [claimAmount.toLocaleString()])
          : appealableUnderOld
          ? tr("Appel RECEVABLE sous le régime de 1974 (Montant de {0} DH > Ancien seuil de 5.000 DH selon Art. 19)", [claimAmount.toLocaleString()])
          : tr("Jugement en DERNIER RESSORT (Montant de {0} DH ≤ 5.000 DH)", [claimAmount.toLocaleString()]),
        keyCitations: isPostAug2026
          ? ["Loi 58.25 Art. 30", "Loi 58.25 Art. 42 (Notification dématérialisée)", "BO n° 7485"]
          : ["Dahir 1.74.447 Art. 19", "Dahir 1.74.447 Art. 37-39", "BO n° 3230 bis"],
      };
    } else if (caseType === "criminal") {
      const isPostDec2025 = filingObj >= dec08_2025;
      return {
        applicableLaw: isPostDec2025
          ? "Loi 03.23 amendant le Code de Procédure Pénale"
          : "Loi 22.01 (Ancien CPP)",
        effectiveDate: "8 Décembre 2025",
        status: isPostDec2025 ? tr("Garde à vue réformée") : tr("Ancien régime"),
        isNew: isPostDec2025,
        summary: isPostDec2025
          ? tr("Droit à l'avocat dès la première heure de garde à vue et obligation légale d'enregistrement audiovisuel des auditions (Art. 66 & 66 bis).")
          : tr("Ancien régime : avocat autorisé après prolongation par le Parquet."),
        appealStatus: tr("Voies de recours pénales standards"),
        keyCitations: ["Loi 03.23 Art. 66", "Dahir 1-25-54", "BO n° 7437"],
      };
    } else if (caseType === "realestate") {
      const isPostJul2026 = filingObj >= jul01_2026;
      return {
        applicableLaw: "Code Général des Impôts (Art. 133 modifié par Loi de Finances 50-25)",
        effectiveDate: tr("1er Juillet 2026"),
        status: isPostJul2026 ? tr("Surtaxe 2% Espèces Applicable") : tr("Exempté de la surtaxe 2%"),
        isNew: isPostJul2026,
        summary: isPostJul2026
          ? tr("Tout acte de vente immobilière ou de fonds de commerce payé en espèces hors circuit bancaire subit un droit d'enregistrement supplémentaire de 2% sur la quote-part en liquide.")
          : tr("Les actes conclus avant le 1er juillet 2026 échappent au droit additionnel de 2%."),
        appealStatus: tr("Contentieux fiscal devant la Commission Locale de Taxation"),
        keyCitations: ["Loi 50-25 Art. 133", "CGI 2026", "BO n° 7465 bis"],
      };
    } else {
      return {
        applicableLaw: "Code du Travail (Loi 65-99) & Décret 2.25.983 (SMIG 2026)",
        effectiveDate: "1er Janvier 2026",
        status: "SMIG 17,92 MAD/h en vigueur",
        isNew: true,
        summary:
          tr("Le salaire horaire minimum légal dans le secteur non agricole est de 17,92 MAD/h. Toute rupture abusive ouvre droit au calcul d'indemnité selon l'Art. 53."),
        appealStatus: tr("Appel recevable selon le droit commun social"),
        keyCitations: ["Loi 65-99 Art. 53", "Décret 2.25.983", "BO n° 7470"],
      };
    }
  };

  const analysis = determineRegime();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5"
      style={{ backgroundColor: "rgba(27, 22, 20, 0.55)" }}
    >
      <div
        className="relative w-full max-w-4xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[90vh] sanad-liquid-modal"
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
                  {tr("Concordance & Règles Transitoires")}
                </h2>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-md font-medium"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {tr("Loi 58.25 vs CPC 1974")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Pivots légaux au Maroc : Date d'entrée en vigueur du 24 Août 2026 et non-rétroactivité des lois.")}
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

        {/* Navigation Tabs */}
        <div
          className="px-6 border-b flex items-center gap-4 overflow-x-auto"
          style={{
            borderColor: "var(--border-subtle)",
            backgroundColor: "var(--bg-canvas)",
          }}
        >
          {([
            ["finder", "Ancien → nouvel article"],
            ["history", "Historique d'un article"],
            ["contract", "Vérifier un contrat"],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className="py-3 text-xs font-medium flex items-center gap-2 border-b-2 transition-all cursor-pointer"
              style={{
                borderColor: activeTab === id ? "var(--accent-primary)" : "transparent",
                color: activeTab === id ? "var(--text-heading)" : "var(--text-muted)",
              }}
            >
              <span>{tr(label)}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => setActiveTab("wizard")}
            className="py-3 text-xs font-medium flex items-center gap-2 border-b-2 transition-all cursor-pointer"
            style={{
              borderColor: activeTab === "wizard" ? "var(--accent-primary)" : "transparent",
              color: activeTab === "wizard" ? "var(--text-heading)" : "var(--text-muted)",
            }}
          >
            <Sparkles className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
            <span>{tr("Assistant \"Quel régime s'applique à mon litige ?\"")}</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("table")}
            className="py-3 text-xs font-medium flex items-center gap-2 border-b-2 transition-all cursor-pointer"
            style={{
              borderColor: activeTab === "table" ? "var(--accent-primary)" : "transparent",
              color: activeTab === "table" ? "var(--text-heading)" : "var(--text-muted)",
            }}
          >
            <BookOpen className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
            <span>{tr("Repères fixes (1974 ↔ 2026)")}</span>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {activeTab === "finder" ? (
            <FinderPanel asOf={filingDate} />
          ) : activeTab === "history" ? (
            <HistoryPanel asOf={new Date().toISOString().slice(0, 10)} />
          ) : activeTab === "contract" ? (
            <ContractPanel asOf={new Date().toISOString().slice(0, 10)} />
          ) : activeTab === "wizard" ? (
            <div className="space-y-6">
              {/* Wizard Inputs */}
              <div
                className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <div>
                  <label
                    className="block text-xs font-semibold mb-1"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {tr("Nature du litige / Matière")}
                  </label>
                  <select
                    value={caseType}
                    onChange={(e) => setCaseType(e.target.value as any)}
                    className="w-full text-xs p-2 rounded-lg border outline-none"
                    style={{
                      backgroundColor: "var(--bg-surface)",
                      borderColor: "var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  >
                    <option value="civil">{tr("Procédure Civile & Commerciale")}</option>
                    <option value="criminal">{tr("Procédure Pénale (Garde à vue)")}</option>
                    <option value="realestate">{tr("Vente Immobilière & Droit 2% Espèces")}</option>
                    <option value="labor">{tr("Droit du Travail (Licenciement/SMIG)")}</option>
                  </select>
                </div>

                <div>
                  <label
                    className="block text-xs font-semibold mb-1"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {tr("Date de dépôt ou de l'acte")}
                  </label>
                  <input
                    type="date"
                    value={filingDate}
                    onChange={(e) => setFilingDate(e.target.value)}
                    className="w-full text-xs p-2 rounded-lg border outline-none"
                    style={{
                      backgroundColor: "var(--bg-surface)",
                      borderColor: "var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  />
                  <div className="flex gap-2 mt-1">
                    <button
                      type="button"
                      onClick={() => setFilingDate("2026-05-10")}
                      className="text-[10px] hover:underline cursor-pointer"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Avant 24 Août")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setFilingDate("2026-09-01")}
                      className="text-[10px] hover:underline cursor-pointer"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Après 24 Août")}
                    </button>
                  </div>
                </div>

                {caseType === "civil" && (
                  <div>
                    <label
                      className="block text-xs font-semibold mb-1"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {tr("Montant du litige (Dirhams)")}
                    </label>
                    <input
                      type="number"
                      value={claimAmount}
                      onChange={(e) => setClaimAmount(Number(e.target.value))}
                      className="w-full text-xs p-2 rounded-lg border outline-none"
                      style={{
                        backgroundColor: "var(--bg-surface)",
                        borderColor: "var(--border-subtle)",
                        color: "var(--text-primary)",
                      }}
                    />
                    <span
                      className="text-[10px] mt-1 block"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Seuils légaux : 5.000 DH (1974) vs 10.000 DH (2026)")}
                    </span>
                  </div>
                )}
              </div>

              {/* Result Card */}
              <div
                className="p-5 rounded-xl border transition-all space-y-3"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--accent-warm)",
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CheckCircle2
                      className="w-4 h-4"
                      style={{ color: "var(--accent-warm)" }}
                    />
                    <span
                      className="font-editorial font-semibold text-base"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {analysis.status}
                    </span>
                  </div>
                  <span
                    className="text-xs px-2.5 py-1 rounded-md font-medium border"
                    style={{
                      backgroundColor: "var(--bg-surface)",
                      borderColor: "var(--border-subtle)",
                      color: "var(--text-muted)",
                    }}
                  >
                    {tr("Pivot :")} {analysis.effectiveDate}
                  </span>
                </div>

                <div
                  className="text-xs space-y-2.5"
                  style={{ color: "var(--text-primary)" }}
                >
                  <p className="leading-relaxed">
                    <strong style={{ color: "var(--text-heading)" }}>{tr("Texte applicable :")}</strong>{" "}
                    {analysis.applicableLaw}
                  </p>
                  <p
                    className="leading-relaxed p-3 rounded-lg border"
                    style={{
                      backgroundColor: "var(--bg-surface)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    {analysis.summary}
                  </p>
                  {caseType === "civil" && (
                    <div
                      className="p-3 rounded-lg border font-medium"
                      style={{
                        backgroundColor: "var(--bg-surface)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <span
                        className="text-[10px] block uppercase"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {tr("Recevabilité de l'appel :")}
                      </span>
                      <span
                        className="font-semibold block mt-0.5"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {analysis.appealStatus}
                      </span>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span
                      className="text-[10px] uppercase font-semibold mr-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Citations officielles :")}
                    </span>
                    {analysis.keyCitations.map((cite, i) => (
                      <span
                        key={i}
                        className="text-[11px] px-2 py-0.5 rounded border"
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          borderColor: "var(--border-subtle)",
                          color: "var(--text-heading)",
                        }}
                      >
                        {cite}
                      </span>
                    ))}
                  </div>
                </div>

                {transitional && transitional.length > 0 && (
                  <div className="mt-4 pt-3 border-t space-y-2 text-[11px]" style={{ borderColor: "var(--border-subtle)" }}>
                    <div className="text-[10px] uppercase font-semibold" style={{ color: "var(--text-muted)" }}>
                      {tr("Règles transitoires du pack de lois (texte officiel, sans décision)")}
                    </div>
                    {transitional.map((h) => (
                      <div key={h.instrument_id}>
                        <div className="font-medium" style={{ color: "var(--text-heading)" }}>{h.title}</div>
                        {h.rules.map((r, k) => (
                          <div key={k} style={{ color: "var(--text-primary)" }}>
                            • {r.note}
                            {r.date_comparison ? <em style={{ color: "var(--text-muted)" }}> ({r.date_comparison})</em> : null}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {onApplyDate && (
                  <div
                    className="mt-4 pt-3 border-t flex justify-end"
                    style={{ borderColor: "var(--border-subtle)" }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        onApplyDate(filingDate);
                        onClose();
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:opacity-90 transition-opacity"
                      style={{
                        backgroundColor: "var(--accent-primary)",
                        color: "var(--accent-primary-fg)",
                      }}
                    >
                      <Calendar className="w-3.5 h-3.5" />
                      <span>{tr("Définir comme date de référence de l'espace (")}{filingDate})</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* Table of Concordance */
            <div className="space-y-4">
              <div className="relative">
                <Search
                  className="w-3.5 h-3.5 absolute left-3 top-2.5 opacity-60"
                  style={{ color: "var(--text-muted)" }}
                />
                <input
                  type="text"
                  placeholder={tr("Rechercher par article (ex: Article 19, 30, notification, appel)...")}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border outline-none"
                  style={{
                    backgroundColor: "var(--bg-canvas)",
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-primary)",
                  }}
                />
              </div>

              <div className="space-y-3">
                {filteredRules.map((rule) => (
                  <div
                    key={rule.id}
                    className="p-4 rounded-xl border space-y-3"
                    style={{
                      backgroundColor: "var(--bg-card)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span
                        className="font-editorial font-semibold text-sm"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {rule.topic}
                      </span>
                      <span
                        className="text-[10px] font-medium px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--accent-primary)",
                        }}
                      >
                        {tr("Vigueur :")} {rule.effectiveDate}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                      <div
                        className="p-2.5 rounded-lg border"
                        style={{
                          backgroundColor: "var(--bg-surface)",
                          borderColor: "var(--border-subtle)",
                        }}
                      >
                        <span
                          className="text-[10px] uppercase font-semibold block mb-0.5"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {tr("Ancien texte (")}{rule.oldLaw})
                        </span>
                        <span
                          className="font-semibold block mb-1"
                          style={{ color: "var(--text-heading)" }}
                        >
                          {rule.oldArticle}
                        </span>
                        <p
                          className="text-[11px] leading-relaxed"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {rule.oldSummary}
                        </p>
                      </div>

                      <div
                        className="p-2.5 rounded-lg border"
                        style={{
                          backgroundColor: "var(--bg-surface)",
                          borderColor: "var(--accent-warm)",
                        }}
                      >
                        <span
                          className="text-[10px] uppercase font-semibold block mb-0.5"
                          style={{ color: "var(--accent-warm)" }}
                        >
                          {tr("Nouveau texte (")}{rule.newLaw})
                        </span>
                        <span
                          className="font-semibold block mb-1"
                          style={{ color: "var(--text-heading)" }}
                        >
                          {rule.newArticle}
                        </span>
                        <p
                          className="text-[11px] leading-relaxed"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {rule.newSummary}
                        </p>
                      </div>
                    </div>

                    <div
                      className="p-2.5 rounded-lg text-[11px] border-l-2"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderLeftColor: "var(--accent-primary)",
                        color: "var(--text-primary)",
                      }}
                    >
                      <strong style={{ color: "var(--text-heading)" }}>{tr("Règle de transition :")}</strong>{" "}
                      {rule.transitionalRuleText}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="p-4 border-t flex items-center justify-between"
          style={{
            borderColor: "var(--border-subtle)",
            backgroundColor: "var(--bg-canvas)",
          }}
        >
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            {tr("Source officielle : Bulletin Officiel du Royaume du Maroc n° 7485 & Dahir n° 1-74-447.")}
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
