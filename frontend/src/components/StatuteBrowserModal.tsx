import React, { useEffect, useState } from "react";
import { tr } from "../i18n";
import { useBackendArticles } from "../api/useBackendArticles";
import {
  BookOpen,
  Search,
  Copy,
  Check,
  ShieldCheck,
  AlertTriangle,
  X,
  MessageSquarePlus,
} from "lucide-react";
import {
  SAMPLE_BILINGUAL_ARTICLES,
} from "../data/moroccanLawData";
import { BilingualArticle } from "../types/agent";

interface StatuteBrowserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onInsertToPrompt?: (text: string) => void;
  asOfDate?: string;
}

export function StatuteBrowserModal({
  isOpen,
  onClose,
  onInsertToPrompt,
  asOfDate,
}: StatuteBrowserModalProps) {
  const [selectedLawFilter, setSelectedLawFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedArticleId, setSelectedArticleId] = useState<string>(
    SAMPLE_BILINGUAL_ARTICLES[0]?.id || ""
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const asOf = asOfDate || new Date().toISOString().slice(0, 10);
  const backend = useBackendArticles(isOpen, asOf, SAMPLE_BILINGUAL_ARTICLES);
  const ARTICLES = backend.articles;
  const [searchHits, setSearchHits] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!isOpen || !backend.live || searchQuery.trim().length < 2) {
      setSearchHits(new Set());
      return;
    }
    const ctl = new AbortController();
    const t = setTimeout(() => {
      backend.search(searchQuery.trim(), ctl.signal).then(setSearchHits).catch(() => {});
    }, 350);
    return () => { clearTimeout(t); ctl.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, isOpen, backend.live, backend.search]);

  const flat = (x: string) => x.toLowerCase().replace(/[\s.\-/_]/g, "");
  // open a law -> load its articles; typing a number or a title -> load the laws that match it
  useEffect(() => {
    if (!isOpen || !backend.live || !backend.laws) return;
    if (selectedLawFilter !== "all") { backend.loadLaw(selectedLawFilter); return; }
    const q = flat(searchQuery);
    if (q.length >= 2) {
      backend.laws.filter((l) => flat(l.label).includes(q) || flat(l.id).includes(q)).slice(0, 6).forEach((l) => backend.loadLaw(l.id));
    } else if (backend.laws[0]) {
      backend.loadLaw(backend.laws[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, backend.live, backend.laws, selectedLawFilter, searchQuery]);

  // pick the first real article once the backend list arrives, and load text of the selection
  useEffect(() => {
    if (backend.live && !ARTICLES.some((a) => a.id === selectedArticleId) && ARTICLES[0]) {
      setSelectedArticleId(ARTICLES[0].id);
    }
  }, [backend.live, ARTICLES, selectedArticleId]);
  useEffect(() => {
    if (isOpen && selectedArticleId) backend.loadArticle(selectedArticleId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, selectedArticleId, backend.live, asOf]);

  if (!isOpen) return null;

  const lawsList = backend.live && backend.laws ? [{ id: "all", label: tr("Tous les textes") }, ...backend.laws] : [
    { id: "all", label: tr("Tous les textes") },
    { id: "58.25", label: tr("Loi 58.25 (Procédure Civile)") },
    { id: "03.23", label: tr("Loi 03.23 (Procédure Pénale)") },
    { id: "DOC 1913", label: tr("DOC 1913 (Obligations & Contrats)") },
    { id: "65-99", label: tr("Loi 65-99 (Code du Travail)") },
    { id: "Loi 70.03", label: tr("Loi 70.03 (Code de la Famille)") },
    { id: "66.23", label: tr("Loi 66.23 (Profession d'Avocat ⚠️)") },
    { id: "50-25", label: tr("Loi 50-25 (CGI - 2% Espèces)") },
  ];

  const filteredArticles = ARTICLES.filter((art) => {
    const matchesLaw =
      selectedLawFilter === "all" ||
      (backend.live ? art.instrumentId === selectedLawFilter : art.lawNumber.includes(selectedLawFilter));
    if (!matchesLaw) return false;

    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    if (searchHits.has(art.id)) return true;
    if (backend.live && flat(searchQuery).length >= 2 && flat(`${art.lawNumber} ${art.lawTitle} ${art.titleAr || ""} ${art.dahirNumber}`).includes(flat(searchQuery))) return true;
    return (
      art.articleNumber.toLowerCase().includes(q) ||
      art.textFr.toLowerCase().includes(q) ||
      art.textAr.includes(searchQuery) ||
      art.lawTitle.toLowerCase().includes(q) ||
      art.boNumber.toLowerCase().includes(q)
    );
  });

  const activeArticle =
    ARTICLES.find((a) => a.id === selectedArticleId) ||
    filteredArticles[0] ||
    ARTICLES[0];

  const handleCopyCitation = (art: BilingualArticle) => {
    const citation = `${art.lawTitle} (${art.lawNumber}), ${art.articleNumber} — Dahir: ${art.dahirNumber}, ${art.boNumber} du ${art.boDate}`;
    navigator.clipboard.writeText(citation);
    setCopiedId(art.id);
    setTimeout(() => setCopiedId(null), 2000);
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
              <BookOpen className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2
                  className="text-lg font-editorial font-medium"
                  style={{ color: "var(--text-heading)" }}
                >
                  {tr("Explorateur des Textes & Lois du Maroc")}
                </h2>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-md font-medium"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-primary)",
                  }}
                >
                  {tr("Base Locale Source-Vérifiée (BO)")}
                </span>
              </div>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Textes légaux officiels bilingues avec mention du Dahir, Bulletin Officiel et date d'application.")}
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

        {/* Filter bar */}
        <div
          className="px-6 py-2.5 border-b flex flex-wrap items-center gap-2"
          style={{
            borderColor: "var(--border-subtle)",
            backgroundColor: "var(--bg-canvas)",
          }}
        >
          <div className="relative flex-1 min-w-[200px]">
            <Search
              className="w-3.5 h-3.5 absolute left-3 top-2.5 opacity-60"
              style={{ color: "var(--text-muted)" }}
            />
            <input
              type="text"
              placeholder={tr("Rechercher article, terme en arabe ou français...")}
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
          <div className="flex items-center gap-1.5 overflow-x-auto py-0.5">
            {lawsList.map((law) => (
              <button
                key={law.id}
                type="button"
                onClick={() => setSelectedLawFilter(law.id)}
                className="text-[11px] px-2.5 py-1 rounded-lg font-medium whitespace-nowrap transition-colors cursor-pointer border"
                style={{
                  backgroundColor:
                    selectedLawFilter === law.id
                      ? "var(--accent-primary)"
                      : "var(--bg-surface)",
                  borderColor:
                    selectedLawFilter === law.id
                      ? "var(--accent-primary)"
                      : "var(--border-subtle)",
                  color:
                    selectedLawFilter === law.id
                      ? "var(--accent-primary-fg)"
                      : "var(--text-heading)",
                }}
              >
                {law.label}
              </button>
            ))}
          </div>
        </div>

        {/* Split view */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left: Article list */}
          <div
            className="w-full md:w-80 border-r overflow-y-auto p-2 space-y-1"
            style={{
              borderColor: "var(--border-subtle)",
              backgroundColor: "var(--bg-canvas)",
            }}
          >
            {backend.error && (
              <div className="p-2 text-[10px]" style={{ color: "var(--accent-warm)" }}>{backend.error}</div>
            )}
            {filteredArticles.length === 0 ? (
              <div
                className="p-4 text-center text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Aucun article trouvé.")}
              </div>
            ) : (
              filteredArticles.map((art) => {
                const isSelected = art.id === activeArticle?.id;
                return (
                  <button
                    key={art.id}
                    type="button"
                    onClick={() => setSelectedArticleId(art.id)}
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
                        className="font-medium text-xs truncate"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {art.articleNumber}
                      </span>
                      {art.contestedStatus === "active_contested" ? (
                        <span
                          className="text-[10px] font-semibold px-1.5 py-0.2 rounded"
                          style={{
                            backgroundColor: "var(--bg-muted)",
                            color: "var(--accent-warm)",
                          }}
                        >
                          {tr("CONTESTÉ")}
                        </span>
                      ) : (
                        <span
                          className="text-[10px] font-medium px-1.5 py-0.2 rounded"
                          style={{
                            backgroundColor: "var(--bg-muted)",
                            color: "var(--text-muted)",
                          }}
                        >
                          {art.boNumber}
                        </span>
                      )}
                    </div>
                    <div
                      className="text-[11px] truncate mb-0.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {art.lawTitle}
                    </div>
                    <div
                      className="text-[10px] font-arabic truncate dir-rtl text-right"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {art.titleAr}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Right: Dual-column bilingual viewer */}
          <div
            className="flex-1 overflow-y-auto p-6 space-y-5"
            style={{ backgroundColor: "var(--bg-surface)" }}
          >
            {activeArticle && (
              <>
                {/* Article Header & Citation Info */}
                <div
                  className="pb-4 border-b flex flex-col sm:flex-row sm:items-start justify-between gap-4"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="text-xs font-semibold px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--accent-primary)",
                        }}
                      >
                        {activeArticle.lawNumber}
                      </span>
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {activeArticle.path}
                      </span>
                    </div>
                    <h3
                      className="text-lg font-editorial font-semibold"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {activeArticle.articleNumber} — {activeArticle.lawTitle}
                    </h3>
                    <p
                      className="text-xs font-arabic dir-rtl text-right mt-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {activeArticle.titleAr}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleCopyCitation(activeArticle)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-1.5 cursor-pointer hover:opacity-85 transition-opacity"
                      style={{
                        backgroundColor: "var(--bg-canvas)",
                        borderColor: "var(--border-subtle)",
                        color: "var(--text-heading)",
                      }}
                    >
                      {copiedId === activeArticle.id ? (
                        <>
                          <Check className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                          <span>{tr("Copié !")}</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>{tr("Copier citation")}</span>
                        </>
                      )}
                    </button>
                    {onInsertToPrompt && (
                      <button
                        type="button"
                        onClick={() => {
                          const quote = `Selon l'article ${activeArticle.articleNumber} de la ${activeArticle.lawTitle} (${activeArticle.boNumber}) :\n"${activeArticle.textFr}"\nPouvez-vous m'éclairer sur son application ?`;
                          onInsertToPrompt(quote);
                          onClose();
                        }}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:opacity-90 transition-opacity"
                        style={{
                          backgroundColor: "var(--accent-primary)",
                          color: "var(--accent-primary-fg)",
                        }}
                      >
                        <MessageSquarePlus className="w-3.5 h-3.5" />
                        <span>{tr("Insérer dans la saisie")}</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Law Status & Provenance Card */}
                <div
                  className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3.5 rounded-xl border text-xs"
                  style={{
                    backgroundColor: "var(--bg-card)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <div>
                    <span
                      className="block text-[10px] uppercase font-semibold mb-0.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Dahir Royal")}
                    </span>
                    <span
                      className="font-medium truncate block"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {activeArticle.dahirNumber}
                    </span>
                  </div>
                  <div>
                    <span
                      className="block text-[10px] uppercase font-semibold mb-0.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Bulletin Officiel (BO)")}
                    </span>
                    <span
                      className="font-medium block"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {activeArticle.boNumber} ({activeArticle.boDate})
                    </span>
                  </div>
                  <div>
                    <span
                      className="block text-[10px] uppercase font-semibold mb-0.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Entrée en Vigueur")}
                    </span>
                    <span
                      className="font-semibold block"
                      style={{ color: "var(--accent-warm)" }}
                    >
                      {activeArticle.validFrom}
                    </span>
                  </div>
                  <div>
                    <span
                      className="block text-[10px] uppercase font-semibold mb-0.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Statut Juridique")}
                    </span>
                    {activeArticle.contestedStatus === "active_contested" ? (
                      <span
                        className="font-semibold flex items-center gap-1"
                        style={{ color: "var(--accent-warm)" }}
                      >
                        <AlertTriangle className="w-3.5 h-3.5" /> {tr("Contestation Barreau")}
                      </span>
                    ) : (
                      <span
                        className="font-semibold flex items-center gap-1"
                        style={{ color: "var(--accent-primary)" }}
                      >
                        <ShieldCheck className="w-3.5 h-3.5" /> {tr("Promulgué au BO")}
                      </span>
                    )}
                  </div>
                </div>

                {/* Transitional Rule banner if present */}
                {activeArticle.transitionalRule && (
                  <div
                    className="p-3 border-l-2 rounded-r-lg text-xs space-y-0.5"
                    style={{
                      backgroundColor: "var(--bg-card)",
                      borderLeftColor: "var(--accent-warm)",
                      color: "var(--text-primary)",
                    }}
                  >
                    <strong
                      className="block font-semibold"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {tr("Règle transitoire d'application :")}
                    </strong>
                    <p style={{ color: "var(--text-muted)" }}>
                      {activeArticle.transitionalRule}
                    </p>
                  </div>
                )}

                {/* Dual Column Bilingual Viewer (French on Left / Arabic on Right) */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* French Column */}
                  <div
                    className="p-4 rounded-xl border space-y-2"
                    style={{
                      backgroundColor: "var(--bg-canvas)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    <div
                      className="flex items-center justify-between pb-2 border-b"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <span
                        className="text-xs font-semibold"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {tr("Version Française Officielle")}
                      </span>
                      <span
                        className="text-[10px] px-2 py-0.5 rounded font-medium"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--text-muted)",
                        }}
                      >
                        {tr("Traduction SGG")}
                      </span>
                    </div>
                    <div
                      className="text-xs leading-relaxed whitespace-pre-line font-sans"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {activeArticle.textFr}
                    </div>
                  </div>

                  {/* Arabic Column (CONTROLLING VERSION) */}
                  <div
                    className="p-4 rounded-xl border space-y-2"
                    style={{
                      backgroundColor: "var(--bg-card)",
                      borderColor: "var(--accent-warm)",
                    }}
                  >
                    <div
                      className="flex items-center justify-between pb-2 border-b"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <span
                        className="text-[10px] px-2 py-0.5 rounded font-semibold"
                        style={{
                          backgroundColor: "var(--accent-primary)",
                          color: "var(--accent-primary-fg)",
                        }}
                      >
                        النص الرسمي المعتمد (الملزم)
                      </span>
                      <span
                        className="text-xs font-semibold font-arabic"
                        style={{ color: "var(--text-heading)" }}
                      >
                        الصيغة العربية الرسمية
                      </span>
                    </div>
                    <div
                      dir="rtl"
                      className="text-sm leading-loose whitespace-pre-line font-arabic text-right"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {activeArticle.textAr}
                    </div>
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
