import React, { useState } from "react";
import { tr } from "../i18n";
import {
  CheckCircle2,
  Send,
  X,
  Scale,
} from "lucide-react";

interface ReportErrorModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultArticle?: string;
  onSubmitReport: (report: {
    articleRef: string;
    boNumber: string;
    errorType: string;
    details: string;
    suggestedFix: string;
  }) => void;
}

export function ReportErrorModal({
  isOpen,
  onClose,
  defaultArticle = "",
  onSubmitReport,
}: ReportErrorModalProps) {
  const [articleRef, setArticleRef] = useState(defaultArticle || "Loi 58.25 - Art. 30");
  const [boNumber, setBoNumber] = useState("BO 7485 (23 Février 2026)");
  const [errorType, setErrorType] = useState<
    "outdated" | "translation" | "transitional_date" | "amending_dahir" | "other"
  >("transitional_date");
  const [details, setDetails] = useState("");
  const [suggestedFix, setSuggestedFix] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmitReport({
      articleRef,
      boNumber,
      errorType,
      details,
      suggestedFix,
    });
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      onClose();
    }, 1800);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5"
      style={{ backgroundColor: "rgba(27, 22, 20, 0.55)" }}
    >
      <div
        className="relative w-full max-w-lg rounded-2xl border shadow-2xl overflow-hidden flex flex-col sanad-liquid-modal"
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
                  className="text-base font-editorial font-semibold"
                  style={{ color: "var(--text-heading)" }}
                >
                  {tr("Signaler une Divergence / Citer BO")}
                </h2>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-md font-medium"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {tr("Règle 2 : Citation BO")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Aidez à maintenir la conformité absolue avec le Bulletin Officiel du Royaume du Maroc.")}
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

        {submitted ? (
          <div className="p-10 flex flex-col items-center justify-center text-center space-y-3">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{
                backgroundColor: "var(--bg-card)",
                color: "var(--accent-primary)",
              }}
            >
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3
              className="font-editorial font-semibold text-base"
              style={{ color: "var(--text-heading)" }}
            >
              {tr("Signalement Enregistré avec Succès")}
            </h3>
            <p
              className="text-xs max-w-xs leading-relaxed"
              style={{ color: "var(--text-muted)" }}
            >
              {tr("Votre observation a été versée au journal de concordance local et sera vérifiée contre la version officielle du Bulletin Officiel.")}
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            <div>
              <label
                className="block text-xs font-semibold mb-1"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Référence de l'Article ou du Texte")}
              </label>
              <input
                type="text"
                required
                value={articleRef}
                onChange={(e) => setArticleRef(e.target.value)}
                placeholder={tr("Ex: Loi 58.25 Art. 30 ou Dahir 1.74.447 Art. 19")}
                className="w-full text-xs p-2.5 rounded-xl border outline-none"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-1"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Source Officielle SGG (N° Bulletin Officiel)")}
              </label>
              <input
                type="text"
                required
                value={boNumber}
                onChange={(e) => setBoNumber(e.target.value)}
                placeholder={tr("Ex: BO n° 7485 du 23 février 2026")}
                className="w-full text-xs p-2.5 rounded-xl border outline-none"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-1"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Nature du problème constaté")}
              </label>
              <select
                value={errorType}
                onChange={(e) => setErrorType(e.target.value as any)}
                className="w-full text-xs p-2.5 rounded-xl border outline-none"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              >
                <option value="transitional_date">{tr("Date d'entrée en vigueur ou règle transitoire imprécise")}</option>
                <option value="translation">{tr("Écart entre version arabe officielle et traduction française")}</option>
                <option value="outdated">{tr("Texte abrogé ou modifié par un Dahir postérieur")}</option>
                <option value="amending_dahir">{tr("Dahir d'application non encore publié")}</option>
                <option value="other">{tr("Autre précision doctrinale / jurisprudentielle")}</option>
              </select>
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-1"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Description de la divergence")}
              </label>
              <textarea
                rows={3}
                required
                value={details}
                onChange={(e) => setDetails(e.target.value)}
                placeholder={tr("Décrivez avec exactitude la divergence constatée par rapport au texte officiel...")}
                className="w-full text-xs p-2.5 rounded-xl border outline-none leading-relaxed"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            <div
              className="pt-2 flex items-center justify-end gap-2 border-t"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <button
                type="button"
                onClick={onClose}
                className="px-3.5 py-2 rounded-lg text-xs font-medium border cursor-pointer hover:opacity-85 transition-opacity"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-heading)",
                }}
              >
                {tr("Annuler")}
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:opacity-90 transition-opacity"
                style={{
                  backgroundColor: "var(--accent-primary)",
                  color: "var(--accent-primary-fg)",
                }}
              >
                <Send className="w-3.5 h-3.5" />
                <span>{tr("Transmettre la citation BO")}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
