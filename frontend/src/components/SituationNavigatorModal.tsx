import React, { useState } from "react";
import { tr } from "../i18n";
import {
  FileText,
  Briefcase,
  Home,
  Users,
  CreditCard,
  Building,
  Car,
  ShoppingBag,
  CheckCircle2,
  ChevronRight,
  Printer,
  MessageSquarePlus,
  X,
  Search,
  BookOpen,
  Compass,
} from "lucide-react";
import { CITIZEN_SITUATIONS } from "../data/moroccanLawData";
import { CitizenSituation } from "../types/agent";
import { useNavigatorArticles, SITUATION_TO_BACKEND } from "../api/useLawGuides";
import { makeGuide, toolError, type GuideResult } from "../api/useTools";
import { useI18n } from "../i18n";

interface SituationNavigatorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectPrompt: (promptText: string) => void;
  onOpenConsultationPrep?: (situation: CitizenSituation) => void;
  asOfDate?: string;
}

export function SituationNavigatorModal({
  isOpen,
  onClose,
  onSelectPrompt,
  onOpenConsultationPrep,
  asOfDate,
}: SituationNavigatorModalProps) {
  const [selectedId, setSelectedId] = useState<string>(
    CITIZEN_SITUATIONS[0]?.id || "sit-unpaid-wages"
  );
  const [searchQuery, setSearchQuery] = useState<string>("");
  const { lang } = useI18n();
  const [guide, setGuide] = useState<GuideResult | null>(null);
  const [guideBusy, setGuideBusy] = useState(false);
  const [guideErr, setGuideErr] = useState("");

  const live = useNavigatorArticles(
    selectedId,
    asOfDate || new Date().toISOString().slice(0, 10),
    isOpen
  );

  React.useEffect(() => { setGuide(null); setGuideErr(""); }, [selectedId]);
  if (!isOpen) return null;

  const filteredSituations = CITIZEN_SITUATIONS.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.title.toLowerCase().includes(q) ||
      s.titleAr.includes(searchQuery) ||
      s.description.toLowerCase().includes(q)
    );
  });

  const activeSituation =
    CITIZEN_SITUATIONS.find((s) => s.id === selectedId) || CITIZEN_SITUATIONS[0];

  const getCategoryIcon = (cat: CitizenSituation["category"]) => {
    switch (cat) {
      case "employment":
        return Briefcase;
      case "housing":
        return Home;
      case "family":
        return Users;
      case "commercial":
        return CreditCard;
      case "inheritance":
        return Building;
      case "traffic":
        return Car;
      default:
        return ShoppingBag;
    }
  };

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
              <Compass className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2
                  className="text-lg font-editorial font-medium"
                  style={{ color: "var(--text-heading)" }}
                >
                  {tr("Guide des Situations Juridiques Citoyen")}
                </h2>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-md font-medium"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {tr("Dossier Prêt-à-Consulter")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Parcours simplifié pour connaître vos droits, les articles du Bulletin Officiel et les pièces à réunir pour votre avocat.")}
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

        {/* Search bar & Body split */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left: Situations list */}
          <div
            className="w-full md:w-80 border-r flex flex-col"
            style={{
              borderColor: "var(--border-subtle)",
              backgroundColor: "var(--bg-canvas)",
            }}
          >
            <div
              className="p-3 border-b"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <div className="relative">
                <Search
                  className="w-3.5 h-3.5 absolute left-3 top-2.5 opacity-60"
                  style={{ color: "var(--text-muted)" }}
                />
                <input
                  type="text"
                  placeholder={tr("Rechercher une situation...")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border outline-none"
                  style={{
                    backgroundColor: "var(--bg-surface)",
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-primary)",
                  }}
                />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {filteredSituations.map((sit) => {
                const Icon = getCategoryIcon(sit.category);
                const isSelected = sit.id === activeSituation.id;
                return (
                  <button
                    key={sit.id}
                    onClick={() => setSelectedId(sit.id)}
                    className="w-full text-left p-3 rounded-xl transition-all flex items-start gap-2.5 cursor-pointer border"
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
                    <div
                      className="p-2 rounded-lg shrink-0 mt-0.5"
                      style={{
                        backgroundColor: isSelected
                          ? "var(--accent-primary)"
                          : "var(--bg-muted)",
                        color: isSelected
                          ? "var(--accent-primary-fg)"
                          : "var(--accent-warm)",
                      }}
                    >
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h4
                        className="font-medium text-xs truncate"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {sit.title}
                      </h4>
                      <p
                        className="text-[11px] font-arabic truncate dir-rtl text-right mt-0.5"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {sit.titleAr}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: Situation Details */}
          <div
            className="flex-1 overflow-y-auto p-6 space-y-6"
            style={{ backgroundColor: "var(--bg-surface)" }}
          >
            {activeSituation && (
              <>
                <div
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <div>
                    <span
                      className="text-[10px] uppercase tracking-wider font-semibold block"
                      style={{ color: "var(--accent-warm)" }}
                    >
                      {tr("Situation Pratique Citoyenne")}
                    </span>
                    <h3
                      className="text-lg font-editorial font-semibold mt-0.5"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {activeSituation.title}
                    </h3>
                    <p
                      className="text-xs font-arabic dir-rtl text-right mt-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {activeSituation.titleAr}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {onOpenConsultationPrep && (
                      <button
                        type="button"
                        onClick={() => onOpenConsultationPrep(activeSituation)}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-1.5 cursor-pointer hover:opacity-85 transition-opacity"
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          borderColor: "var(--border-subtle)",
                          color: "var(--text-heading)",
                        }}
                      >
                        <Printer className="w-3.5 h-3.5" />
                        <span>{tr("Imprimer Dossier")}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        const defaultPrompt = tr("Je rencontre la situation suivante : \"{0}\". Pouvez-vous analyser mes droits selon la loi marocaine en vigueur, m'indiquer les textes du BO applicables et vérifier les pièces dont j'ai besoin ?", [activeSituation.title]);
                        onSelectPrompt(defaultPrompt);
                        onClose();
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:opacity-90 transition-opacity"
                      style={{
                        backgroundColor: "var(--accent-primary)",
                        color: "var(--accent-primary-fg)",
                      }}
                    >
                      <MessageSquarePlus className="w-3.5 h-3.5" />
                      <span>{tr("Poser cette question")}</span>
                    </button>
                  </div>
                </div>

                <p
                  className="text-xs leading-relaxed p-3.5 rounded-xl border"
                  style={{
                    backgroundColor: "var(--bg-canvas)",
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-primary)",
                  }}
                >
                  {activeSituation.description}
                </p>

                {/* Guide generated from the law pack */}
                <div>
                  <button
                    type="button"
                    disabled={guideBusy}
                    onClick={async () => {
                      setGuideBusy(true); setGuideErr("");
                      try {
                        const sit = SITUATION_TO_BACKEND[selectedId];
                        setGuide(await makeGuide({ situation: sit, topic: sit ? undefined : (activeSituation.titleAr || activeSituation.title), asOf: asOfDate, lang }));
                      } catch (e) { setGuide(null); setGuideErr(toolError(e)); }
                      setGuideBusy(false);
                    }}
                    className="px-3 py-2 rounded-lg text-xs font-medium cursor-pointer"
                    style={{ backgroundColor: "var(--accent-primary)", color: "var(--text-on-accent, #fff)" }}
                  >
                    {guideBusy ? tr("Préparation du guide…") : tr("Générer le guide à partir des lois installées")}
                  </button>
                  {guideErr && <p className="text-[11px] mt-2" style={{ color: "var(--text-muted)" }}>{guideErr}</p>}
                  {guide && (
                    <div className="mt-3 space-y-2">
                      {guide.steps.map((st, i) => (
                        <div key={i} className="p-3 rounded-xl border text-xs space-y-1" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)" }}>
                          <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{i + 1}. {st.title}</div>
                          <div style={{ color: "var(--text-primary)" }}>{st.text}</div>
                          <div style={{ color: "var(--text-muted)" }}>{st.articles.map((a) => `${a.law}, ${a.article}`).join(" · ")}</div>
                        </div>
                      ))}
                      {guide.status === "articles_only" && <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{tr("Pas de modèle de langage dans ce mode : les articles trouvés sont listés ci-dessous sans étapes rédigées.")}</p>}
                      {guide.status === "articles_only" && guide.articles.slice(0, 6).map((a) => (
                        <div key={a.id} className="p-3 rounded-xl border text-[11px]" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)" }}>
                          <div className="font-medium" style={{ color: "var(--text-heading)" }}>{a.law}, {a.article}</div>
                          <div style={{ color: "var(--text-muted)" }}>{a.text}</div>
                        </div>
                      ))}
                      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{guide.notice}</p>
                    </div>
                  )}
                </div>

                {/* Live articles from the local law pack */}
                {live.supported && (live.articles || live.error) && (
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider mb-2.5" style={{ color: "var(--text-heading)" }}>
                      {tr("Articles du pack de lois (source vérifiée, au")} {asOfDate})
                    </h4>
                    {live.error && <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{live.error}</p>}
                    <div className="space-y-2">
                      {(live.articles || []).slice(0, 6).map((a) => (
                        <div key={a.id} className="p-3 rounded-xl border text-[11px] space-y-1" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)" }}>
                          <div className="font-medium" style={{ color: "var(--text-heading)" }}>
                            {a.law}, {a.article}
                            {a.bo?.number ? tr(" (BO {0})", [a.bo.number]) : ""}
                            {a.in_force_on_as_of === false ? tr(" ⚠ non en vigueur à cette date") : ""}
                          </div>
                          <div style={{ color: "var(--text-muted)" }}>{a.text}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Key Legal Articles */}
                <div>
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider mb-2.5 flex items-center gap-1.5"
                    style={{ color: "var(--text-heading)" }}
                  >
                    <BookOpen className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                    {tr("Textes & Articles de Loi Applicables")}
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {activeSituation.keyArticles.map((art, idx) => (
                      <div
                        key={idx}
                        className="p-3.5 rounded-xl border space-y-1"
                        style={{
                          backgroundColor: "var(--bg-card)",
                          borderColor: "var(--border-subtle)",
                        }}
                      >
                        <div className="flex items-center justify-between">
                          <span
                            className="font-medium text-xs"
                            style={{ color: "var(--text-heading)" }}
                          >
                            {art.article}
                          </span>
                          <span
                            className="text-[10px] font-medium px-2 py-0.5 rounded"
                            style={{
                              backgroundColor: "var(--bg-muted)",
                              color: "var(--accent-primary)",
                            }}
                          >
                            {art.law}
                          </span>
                        </div>
                        <p
                          className="text-[11px] leading-relaxed"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {art.summary}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* What to bring to a lawyer */}
                <div
                  className="border rounded-xl p-4 space-y-2"
                  style={{
                    backgroundColor: "var(--bg-canvas)",
                    borderColor: "var(--accent-warm)",
                  }}
                >
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5"
                    style={{ color: "var(--text-heading)" }}
                  >
                    <FileText className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                    {tr("Dossier à constituer pour votre Avocat (Pièces exigées)")}
                  </h4>
                  <p
                    className="text-[11px]"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {tr("Conformément à la déontologie légale, cette assistance prépare vos démarches sans remplacer la représentation par un avocat inscrit au Barreau marocain.")}
                  </p>
                  <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                    {activeSituation.documentsToBring.map((doc, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-xs p-2 rounded-lg border"
                        style={{
                          backgroundColor: "var(--bg-surface)",
                          borderColor: "var(--border-subtle)",
                          color: "var(--text-primary)",
                        }}
                      >
                        <CheckCircle2
                          className="w-3.5 h-3.5 shrink-0 mt-0.5"
                          style={{ color: "var(--accent-warm)" }}
                        />
                        <span>{doc}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Practical Next Steps */}
                <div>
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider mb-2"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {tr("Étapes Pratiques Recommandées")}
                  </h4>
                  <div className="space-y-2">
                    {activeSituation.practicalNextSteps.map((step, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 rounded-lg border text-xs flex items-start gap-2"
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          borderColor: "var(--border-subtle)",
                          color: "var(--text-primary)",
                        }}
                      >
                        <ChevronRight
                          className="w-3.5 h-3.5 shrink-0 mt-0.5"
                          style={{ color: "var(--accent-warm)" }}
                        />
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Typical Citizen Questions */}
                <div>
                  <h4
                    className="text-xs font-semibold uppercase tracking-wider mb-2"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {tr("Questions Fréquemment Posées")}
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {activeSituation.typicalQuestions.map((q, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => {
                          onSelectPrompt(q);
                          onClose();
                        }}
                        className="text-left text-xs px-3 py-2 rounded-lg border transition-opacity cursor-pointer hover:opacity-85"
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          borderColor: "var(--border-subtle)",
                          color: "var(--text-heading)",
                        }}
                      >
                        "{q}"
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
