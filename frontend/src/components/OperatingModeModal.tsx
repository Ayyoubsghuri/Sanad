import React, { useEffect, useState } from "react";
import { tr } from "../i18n";
import { getStatus } from "../api/legalrag";
import {
  Shield,
  WifiOff,
  Check,
  Lock,
  X,
  Scale,
} from "lucide-react";
import { OperatingMode } from "../types/agent";

interface OperatingModeModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentMode: OperatingMode;
  onSelectMode: (mode: OperatingMode) => void;
}

export function OperatingModeModal({
  isOpen,
  onClose,
  currentMode,
  onSelectMode,
}: OperatingModeModalProps) {
  const [backend, setBackend] = useState<string>(tr("Vérification du serveur local…"));
  useEffect(() => {
    if (!isOpen) return;
    let off = false;
    getStatus()
      .then((st) => {
        if (off) return;
        const llm = (st as unknown as { providers?: { llm?: { provider: string; model: string } | null } }).providers?.llm;
        setBackend(
          tr("Serveur local connecté · mode {0} · pack {1}{2} · génération : {3}", [st.mode, st.pack.loaded ? st.pack.version : "absent", st.pack.stale ? tr(" (ancien)") : "", llm ? `${llm.provider}/${llm.model}` : tr("aucun modèle (articles cités seulement)")])
        );
      })
      .catch(() => !off && setBackend(tr("Serveur local injoignable (vérifiez l'URL et le jeton).")));
    return () => { off = true; };
  }, [isOpen, currentMode]);

  if (!isOpen) return null;

  const modes: {
    id: OperatingMode;
    title: string;
    badge: string;
    tagline: string;
    icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
    privacyLevel: string;
    latency: string;
    cloudCalls: string;
    description: string;
    features: string[];
  }[] = [
    {
      id: "offline",
      title: tr("Mode Hors-Ligne (Strict)"),
      badge: tr("0 Appel Réseau"),
      tagline: tr("Texte de loi officiel brut + calculateurs déterministes locaux"),
      icon: WifiOff,
      privacyLevel: tr("100% Souverain (Navigateur local)"),
      latency: tr("< 50 ms (Instantané)"),
      cloudCalls: tr("0 requête sortante"),
      description:
        tr("Aucune donnée ne quitte votre machine. L'assistance juridique s'appuie exclusivement sur les textes du Bulletin Officiel pré-indexés et les calculateurs certifiés en code pur."),
      features: [
        tr("Confidentialité absolue du secret professionnel (Art. 12 Barreau)"),
        tr("Calculs de SMIG, indemnités et droits de mutation 100% locaux"),
        tr("Consultation bilingue exacte des lois 58.25, 03.23, DOC et 65-99"),
        tr("Fonctionne sans connexion Internet"),
        tr("Réponses rédigées par un modèle local (Ollama, LM Studio) si vous en ajoutez un dans Clés API"),
      ],
    },
    {
      id: "hybrid",
      title: tr("Mode Hybride (Recommandé)"),
      badge: tr("Recommandé Sanad"),
      tagline: tr("Pseudonymisation locale d'abord, puis synthèse cloud vérifiée"),
      icon: Shield,
      privacyLevel: tr("Chiffrement + Pseudonymisation active"),
      latency: tr("~1.2 s (Haute fidélité)"),
      cloudCalls: tr("Requêtes anonymisées"),
      description:
        tr("Le bouclier de pseudonymisation remplace noms, montants et adresses par des jetons cryptographiques avant toute analyse par Gemini 3.8 Flash. Contrôle NLI anti-hallucination local."),
      features: [
        tr("Protection PII automatique : entités remplacées avant envoi"),
        tr("Raisonnement juridique approfondi avec budget de réflexion étendu"),
        tr("Contrôle de conformité NLI : rejet automatique en cas de contradiction"),
        tr("Restauration automatique des vrais noms dans la réponse locale"),
      ],
    },
  ];

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
                  {tr("Modes Opératoires & Souveraineté")}
                </h2>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-md font-medium"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {tr("Règle 7 : Zéro fuite de données")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Garantie de souveraineté et conformité CNDP selon le niveau de sensibilité du dossier.")}
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
        <div className="p-5 sm:p-6 overflow-y-auto space-y-6 flex-1">
          {/* The two modes (cloud-assisted mode is disabled) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {modes.map((m) => {
              const Icon = m.icon;
              const isSelected = currentMode === m.id;
              return (
                <div
                  key={m.id}
                  onClick={() => onSelectMode(m.id)}
                  className={`cursor-pointer rounded-xl border p-4 transition-all flex flex-col justify-between relative ${
                    isSelected ? "ring-2" : "hover:opacity-95"
                  }`}
                  style={{
                    backgroundColor: isSelected
                      ? "var(--bg-card)"
                      : "var(--bg-canvas)",
                    borderColor: isSelected
                      ? "var(--accent-primary)"
                      : "var(--border-subtle)",
                    boxShadow: isSelected ? "0 4px 12px rgba(0,0,0,0.05)" : "none",
                  }}
                >
                  {isSelected && (
                    <div
                      className="absolute top-3 right-3 w-5 h-5 rounded-full flex items-center justify-center shadow-xs"
                      style={{
                        backgroundColor: "var(--accent-primary)",
                        color: "var(--accent-primary-fg)",
                      }}
                    >
                      <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                    </div>
                  )}

                  <div>
                    <div className="flex items-center gap-2 mb-2.5">
                      <div
                        className="p-2 rounded-lg"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--accent-warm)",
                        }}
                      >
                        <Icon className="w-4 h-4" />
                      </div>
                      <span
                        className="text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--text-muted)",
                        }}
                      >
                        {m.badge}
                      </span>
                    </div>

                    <h3
                      className="font-editorial text-sm font-semibold mb-1"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {m.title}
                    </h3>
                    <p
                      className="text-xs mb-3 leading-relaxed"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {m.description}
                    </p>

                    <div
                      className="space-y-1.5 pt-2 border-t text-[11px]"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <div className="flex justify-between">
                        <span style={{ color: "var(--text-muted)" }}>{tr("Confidentialité :")}</span>
                        <span
                          className="font-medium text-right"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {m.privacyLevel}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span style={{ color: "var(--text-muted)" }}>{tr("Temps réponse :")}</span>
                        <span
                          className="font-medium"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {m.latency}
                        </span>
                      </div>
                    </div>

                    <div
                      className="mt-3 pt-3 border-t space-y-1"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <span
                        className="text-[10px] font-semibold uppercase tracking-wider block"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {tr("Garanties clés :")}
                      </span>
                      {m.features.slice(0, 3).map((f, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-1.5 text-[11px]"
                          style={{ color: "var(--text-primary)" }}
                        >
                          <Check
                            className="w-3.5 h-3.5 shrink-0 mt-0.5"
                            style={{ color: "var(--accent-warm)" }}
                          />
                          <span>{f}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="mt-4 pt-3">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectMode(m.id);
                      }}
                      className="w-full py-1.5 px-3 rounded-lg text-xs font-medium transition-opacity cursor-pointer"
                      style={{
                        backgroundColor: isSelected
                          ? "var(--accent-primary)"
                          : "var(--bg-muted)",
                        color: isSelected
                          ? "var(--accent-primary-fg)"
                          : "var(--text-heading)",
                      }}
                    >
                      {isSelected ? tr("Mode Actif") : tr("Activer ce mode")}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Benchmark comparison matrix table */}
          <div
            className="border rounded-xl overflow-hidden"
            style={{
              borderColor: "var(--border-subtle)",
              backgroundColor: "var(--bg-canvas)",
            }}
          >
            <div
              className="px-4 py-2.5 border-b flex items-center justify-between"
              style={{
                backgroundColor: "var(--bg-muted)",
                borderColor: "var(--border-subtle)",
              }}
            >
              <span
                className="text-xs font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Matrice d'Évaluation & Garanties de Conformité")}
              </span>
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                {tr("Législation marocaine (Loi 09-08 CNDP & Secret professionnel)")}
              </span>
            </div>
            <div className="overflow-x-auto text-xs">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr
                    className="border-b"
                    style={{
                      borderColor: "var(--border-subtle)",
                      color: "var(--text-muted)",
                    }}
                  >
                    <th className="p-3 font-medium">{tr("Critère")}</th>
                    <th className="p-3 font-medium">{tr("Hors-Ligne")}</th>
                    <th className="p-3 font-medium">{tr("Hybride (Sanad)")}</th>
                  </tr>
                </thead>
                <tbody
                  className="divide-y"
                  style={{
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-primary)",
                  }}
                >
                  <tr>
                    <td className="p-3 font-medium" style={{ color: "var(--text-heading)" }}>
                      {tr("Règle 4 : Calculs déterministes certifiés")}
                    </td>
                    <td className="p-3 font-semibold" style={{ color: "var(--accent-warm)" }}>
                      {tr("100% Local (Code pur)")}
                    </td>
                    <td className="p-3 font-semibold" style={{ color: "var(--accent-warm)" }}>
                      {tr("100% Local (Code pur)")}
                    </td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium" style={{ color: "var(--text-heading)" }}>
                      {tr("Règle 7 : Secret professionnel (Art. 12 Barreau)")}
                    </td>
                    <td className="p-3 font-semibold" style={{ color: "var(--accent-warm)" }}>
                      {tr("Zéro transit réseau")}
                    </td>
                    <td className="p-3 font-medium">{tr("Chiffré + Pseudonymisé")}</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium" style={{ color: "var(--text-heading)" }}>
                      {tr("Règle 2 : Citations strictes avec BO")}
                    </td>
                    <td className="p-3">{tr("Exactes (Base locale)")}</td>
                    <td className="p-3">{tr("Exactes + Vérification NLI")}</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium" style={{ color: "var(--text-heading)" }}>
                      {tr("Transitoire : Loi 58.25 vs CPC 1974")}
                    </td>
                    <td className="p-3">{tr("Concordance locale")}</td>
                    <td className="p-3">{tr("Concordance + Raisonnement temporel")}</td>
                  </tr>
                </tbody>
              </table>
            </div>
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
            <span>
              {tr("Mode sélectionné :")} <strong style={{ color: "var(--text-heading)" }} className="uppercase">{currentMode}</strong>
              <span className="block text-[10px] mt-0.5">{backend}</span>
            </span>
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
            {tr("Appliquer et fermer")}
          </button>
        </div>
      </div>
    </div>
  );
}
