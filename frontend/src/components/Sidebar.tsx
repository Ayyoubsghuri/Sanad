import React, { useMemo, useState, useRef, useEffect } from "react";
import { tr } from "../i18n";
import { useI18n } from "../i18n";
import { Gavel,
  BookOpen,
  Calendar,
  Calculator,
  ChevronDown,
  Compass,
  FileCode2,
  FileText,
  Lock,
  PanelLeftClose,
  Plus,
  Scale,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Star,
  Trash2,
  UserCheck,
  Users,
  DownloadCloud,
  KeyRound,
} from "lucide-react";
import { ArtifactItem, ChatThread, OperatingMode } from "../types/agent";
import { SanadAvatar } from "./SanadAvatar";

interface SidebarProps {
  threads: ChatThread[];
  activeThreadId: string | null;
  showRecent: boolean;
  projectDocCount: number;
  vaultItemCount?: number;
  pseudonymRuleCount?: number;
  onSelectThread: (threadId: string) => void;
  onNewChat: () => void;
  onToggleStar: (threadId: string) => void;
  onDeleteThread: (threadId: string) => void;
  onSelectArtifactFromLibrary: (threadId: string, artifact: ArtifactItem) => void;
  onOpenProjectKnowledge: () => void;
  onOpenAppearance: () => void;
  onOpenPseudonymiser: () => void;
  onOpenVault: () => void;
  onCollapse: () => void;
  // Moroccan Legal RAG Blueprint Controls
  operatingMode?: OperatingMode;
  audienceMode?: "citizen" | "professional";
  asOfDate?: string;
  onOpenOperatingMode?: () => void;
  onToggleAudienceMode?: () => void;
  onOpenCalculators?: () => void;
  onOpenSituations?: () => void;
  onOpenStatutes?: () => void;
  onOpenAuditTrace?: () => void;
  onOpenConcordance?: () => void;
  onOpenConsultation?: () => void;
  onOpenProToolkit?: () => void;
  onOpenBoUpdate?: () => void;
  onOpenApiKeys?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  threads,
  activeThreadId,
  showRecent,
  projectDocCount,
  vaultItemCount = 4,
  pseudonymRuleCount = 5,
  onSelectThread,
  onNewChat,
  onToggleStar,
  onDeleteThread,
  onSelectArtifactFromLibrary,
  onOpenProjectKnowledge,
  onOpenAppearance,
  onOpenPseudonymiser,
  onOpenVault,
  onCollapse,
  operatingMode = "hybrid",
  audienceMode = "citizen",
  asOfDate = new Date().toISOString().slice(0, 10),
  onOpenOperatingMode,
  onToggleAudienceMode,
  onOpenCalculators,
  onOpenSituations,
  onOpenStatutes,
  onOpenAuditTrace,
  onOpenConcordance,
  onOpenConsultation,
  onOpenProToolkit,
  onOpenBoUpdate,
  onOpenApiKeys,
}) => {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"all" | "starred" | "artifacts">("all");
  const [legalToolsOpen, setLegalToolsOpen] = useState(false);
  const toolsMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!legalToolsOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        toolsMenuRef.current &&
        !toolsMenuRef.current.contains(e.target as Node)
      ) {
        setLegalToolsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [legalToolsOpen]);

  const filteredThreads = useMemo(() => {
    const q = query.trim().toLowerCase();
    return threads.filter((t) => {
      if (tab === "starred" && !t.starred) return false;
      if (!q) return true;
      return (
        t.title.toLowerCase().includes(q) ||
        t.messages.some((m) => m.content.toLowerCase().includes(q))
      );
    });
  }, [threads, query, tab]);

  const allArtifactsWithThread = useMemo(() => {
    const list: Array<{ threadId: string; threadTitle: string; artifact: ArtifactItem }> = [];
    for (const t of threads) {
      for (const m of t.messages) {
        if (m.artifacts) {
          for (const art of m.artifacts) {
            if (
              !query.trim() ||
              art.title.toLowerCase().includes(query.trim().toLowerCase())
            ) {
              list.push({
                threadId: t.id,
                threadTitle: t.title,
                artifact: art,
              });
            }
          }
        }
      }
    }
    return list;
  }, [threads, query]);

  return (
    <aside
      className="w-[268px] h-full shrink-0 border-r flex flex-col select-none"
      style={{
        backgroundColor: "var(--bg-muted)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {/* Brand + Collapse */}
      <div className="pywebview-drag-region flex items-center justify-between px-4 pt-4 pb-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex items-center gap-2.5 font-editorial text-xl font-medium tracking-tight cursor-pointer whitespace-nowrap shrink-0"
          style={{ color: "var(--text-heading)" }}
        >
          <SanadAvatar size={28} glow={false} />
          Sanad
        </button>

        <button
          type="button"
          onClick={onCollapse}
          title={t("sidebar.collapse")}
          className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer"
          style={{ color: "var(--text-muted)" }}
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Primary New Session CTA */}
      <div className="px-3.5 pb-2">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-xl text-xs font-semibold transition-opacity hover:opacity-90 cursor-pointer whitespace-nowrap"
          style={{
            backgroundColor: "var(--accent-primary)",
            color: "var(--accent-primary-fg)",
          }}
        >
          <Plus className="w-4 h-4" />
          <span>{t("sidebar.new")}</span>
        </button>
      </div>

      {/* Moroccan Legal RAG Controls (Hybride, Citoyen & Outils Juridiques) */}
      <div className="px-3.5 pb-3 space-y-1.5">
        <div className="grid grid-cols-2 gap-1.5">
          {/* Operating Mode (Hybride / Hors-Ligne / Cloud) */}
          {onOpenOperatingMode && (
            <button
              type="button"
              onClick={onOpenOperatingMode}
              title={tr("Mode Opératoire: {0} · Cliquer pour configurer", [operatingMode])}
              className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-xl border text-xs font-medium transition-colors hover:opacity-85 cursor-pointer whitespace-nowrap min-w-0"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-heading)",
              }}
            >
              <ShieldCheck
                className="w-3.5 h-3.5 opacity-80 shrink-0"
                style={{ color: "var(--accent-warm)" }}
              />
              <span className="truncate">
                {operatingMode === "offline"
                  ? t("mode.offline")
                  : operatingMode === "hybrid"
                  ? t("mode.hybrid")
                  : t("mode.cloud")}
              </span>
            </button>
          )}

          {/* Audience Mode Switcher (Citoyen / Avocat Pro) */}
          {onToggleAudienceMode && (
            <button
              type="button"
              onClick={onToggleAudienceMode}
              title={tr("Mode d'audience: {0} · Cliquer pour basculer", [audienceMode === "citizen"
                  ? tr("Grand Public / Citoyen")
                  : tr("Avocat / Juriste Pro")])}
              className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-xl border text-xs font-medium transition-colors hover:opacity-85 cursor-pointer whitespace-nowrap min-w-0"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-heading)",
              }}
            >
              <Users className="w-3.5 h-3.5 opacity-70 shrink-0" />
              <span className="truncate">
                {audienceMode === "citizen" ? t("aud.citizen") : t("aud.pro")}
              </span>
            </button>
          )}
        </div>


        {/* Professional toolkit: shown in Pro Lawyer mode */}
        {audienceMode === "professional" && onOpenProToolkit && (
          <button
            type="button"
            onClick={onOpenProToolkit}
            className="mt-2 w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-start cursor-pointer transition-all hover:opacity-90 pro-fade-in"
            style={{ backgroundColor: "var(--accent-primary)", color: "var(--bg-surface)" }}
          >
            <Gavel className="w-4 h-4 shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-semibold truncate">{tr("Professional Toolkit")}</span>
              <span className="block text-[10px] opacity-80 truncate">{tr("AI Courtroom · Case Analyzer · Jurisprudence")}</span>
            </span>
          </button>
        )}

        {/* Bulletin Officiel auto-update + API keys */}
        {(onOpenBoUpdate || onOpenApiKeys) && (
          <div className="grid grid-cols-2 gap-1.5">
            {onOpenBoUpdate && (
              <button
                type="button"
                onClick={onOpenBoUpdate}
                title={tr("Chercher les nouveaux numéros du Bulletin Officiel et les ajouter à la base")}
                className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-xl border text-xs font-medium transition-colors hover:opacity-85 cursor-pointer whitespace-nowrap min-w-0"
                style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-subtle)", color: "var(--text-heading)" }}
              >
                <DownloadCloud className="w-3.5 h-3.5 opacity-80 shrink-0" style={{ color: "var(--accent-warm)" }} />
                <span className="truncate">{tr("Mettre à jour BO")}</span>
              </button>
            )}
            {onOpenApiKeys && (
              <button
                type="button"
                onClick={onOpenApiKeys}
                title={tr("Clés API et modèles (OpenAI, Anthropic, autre)")}
                className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-xl border text-xs font-medium transition-colors hover:opacity-85 cursor-pointer whitespace-nowrap min-w-0"
                style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-subtle)", color: "var(--text-heading)" }}
              >
                <KeyRound className="w-3.5 h-3.5 opacity-80 shrink-0" style={{ color: "var(--accent-warm)" }} />
                <span className="truncate">{tr("Clés API")}</span>
              </button>
            )}
          </div>
        )}

        {/* Outils Juridiques Dropdown (Shown Over / Floating Popover) */}
        <div className="relative" ref={toolsMenuRef}>
          <button
            type="button"
            onClick={() => setLegalToolsOpen((prev) => !prev)}
            title={t("tools.title")}
            className="w-full flex items-center justify-between py-1.5 px-2.5 rounded-xl border text-xs font-medium transition-colors hover:opacity-85 cursor-pointer whitespace-nowrap"
            style={{
              backgroundColor: legalToolsOpen
                ? "var(--bg-card)"
                : "var(--bg-surface)",
              borderColor: legalToolsOpen
                ? "var(--border-strong)"
                : "var(--border-subtle)",
              color: "var(--text-heading)",
            }}
          >
            <span className="inline-flex items-center gap-2 min-w-0">
              <Scale
                className="w-3.5 h-3.5 opacity-80 shrink-0"
                style={{ color: "var(--accent-warm)" }}
              />
              <span className="truncate">{t("tools.title")}</span>
            </span>
            <ChevronDown
              className={`w-3.5 h-3.5 opacity-70 shrink-0 transition-transform duration-150 ${
                legalToolsOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {/* Floating Dropdown Menu (Shown Over) */}
          {legalToolsOpen && (
            <div
              className="sanad-liquid-pop sanad-liquid-stagger absolute left-0 right-0 top-full mt-1.5 z-50 p-1.5 rounded-xl border text-xs space-y-0.5 shadow-2xl"
              style={{
                transformOrigin: "50% 0%",
                ["--liquid-radius" as string]: "0.75rem",
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-strong)",
                boxShadow:
                  "0 16px 36px -4px rgba(0, 0, 0, 0.24), 0 8px 16px -4px rgba(0, 0, 0, 0.12)",
              }}
            >
              {onOpenCalculators && (
                <button
                  type="button"
                  onClick={() => {
                    setLegalToolsOpen(false);
                    onOpenCalculators();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:opacity-80 cursor-pointer"
                  style={{ color: "var(--text-primary)" }}
                >
                  <Calculator
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[11px] truncate">
                      {t("tools.calc")}
                    </div>
                    <div
                      className="text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {t("tools.calc.sub")}
                    </div>
                  </div>
                </button>
              )}

              {onOpenSituations && (
                <button
                  type="button"
                  onClick={() => {
                    setLegalToolsOpen(false);
                    onOpenSituations();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:opacity-80 cursor-pointer"
                  style={{ color: "var(--text-primary)" }}
                >
                  <Compass
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[11px] truncate">
                      {t("tools.situations")}
                    </div>
                    <div
                      className="text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {t("tools.situations.sub")}
                    </div>
                  </div>
                </button>
              )}

              {onOpenStatutes && (
                <button
                  type="button"
                  onClick={() => {
                    setLegalToolsOpen(false);
                    onOpenStatutes();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:opacity-80 cursor-pointer"
                  style={{ color: "var(--text-primary)" }}
                >
                  <BookOpen
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[11px] truncate">
                      {t("tools.statutes")}
                    </div>
                    <div
                      className="text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {t("tools.statutes.sub")}
                    </div>
                  </div>
                </button>
              )}

              {onOpenConcordance && (
                <button
                  type="button"
                  onClick={() => {
                    setLegalToolsOpen(false);
                    onOpenConcordance();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:opacity-80 cursor-pointer"
                  style={{ color: "var(--text-primary)" }}
                >
                  <Calendar
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[11px] truncate">
                      {t("tools.concordance")}
                    </div>
                    <div
                      className="text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("Loi en vigueur au")} {asOfDate || new Date().toISOString().slice(0, 10)}
                    </div>
                  </div>
                </button>
              )}

              {onOpenAuditTrace && (
                <button
                  type="button"
                  onClick={() => {
                    setLegalToolsOpen(false);
                    onOpenAuditTrace();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:opacity-80 cursor-pointer"
                  style={{ color: "var(--text-primary)" }}
                >
                  <ShieldCheck
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[11px] truncate">
                      {t("tools.audit")}
                    </div>
                    <div
                      className="text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {t("tools.audit.sub")}
                    </div>
                  </div>
                </button>
              )}

              {onOpenConsultation && (
                <button
                  type="button"
                  onClick={() => {
                    setLegalToolsOpen(false);
                    onOpenConsultation();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:opacity-80 cursor-pointer"
                  style={{ color: "var(--text-primary)" }}
                >
                  <FileText
                    className="w-3.5 h-3.5 shrink-0"
                    style={{ color: "var(--accent-warm)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[11px] truncate">
                      {t("tools.consult")}
                    </div>
                    <div
                      className="text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {t("tools.consult.sub")}
                    </div>
                  </div>
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Search Filter */}
      <div className="px-3.5 pb-2.5">
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border"
          style={{
            backgroundColor: "var(--bg-surface)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <Search
            className="w-3.5 h-3.5 shrink-0"
            style={{ color: "var(--text-muted)" }}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("sidebar.filter")}
            className="w-full bg-transparent border-0 outline-none text-xs"
            style={{ color: "var(--text-primary)" }}
          />
        </div>
      </div>

      {/* Functional Segmented Filter */}
      <div className="px-3.5 pb-2">
        <div
          className="grid grid-cols-3 p-0.5 rounded-lg border"
          style={{
            backgroundColor: "var(--bg-canvas)",
            borderColor: "var(--border-subtle)",
          }}
        >
          {(
            [
              { id: "all", label: t("sidebar.tab.all") },
              { id: "starred", label: t("sidebar.tab.starred") },
              { id: "artifacts", label: t("sidebar.tab.artifacts") },
            ] as const
          ).map((item) => {
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className="py-1 text-[11px] font-medium rounded-md transition-colors cursor-pointer whitespace-nowrap"
                style={{
                  backgroundColor: active ? "var(--bg-surface)" : "transparent",
                  color: active ? "var(--text-heading)" : "var(--text-muted)",
                }}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Scrollable List */}
      <div className="flex-1 overflow-y-auto px-2.5 py-1.5 space-y-0.5">
        {tab === "artifacts" ? (
          allArtifactsWithThread.length === 0 ? (
            <div
              className="px-3 py-8 text-center text-xs leading-relaxed"
              style={{ color: "var(--text-muted)" }}
            >
              {t("sidebar.noArtifacts")}
            </div>
          ) : (
            allArtifactsWithThread.map(({ threadId, threadTitle, artifact }) => (
              <button
                key={artifact.id}
                type="button"
                onClick={() => onSelectArtifactFromLibrary(threadId, artifact)}
                className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-xl text-left transition-colors hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: "transparent" }}
              >
                <FileCode2
                  className="w-4 h-4 mt-0.5 shrink-0"
                  style={{ color: "var(--accent-primary)" }}
                />
                <div className="min-w-0 flex-1">
                  <div
                    className="text-xs font-medium truncate"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {artifact.title}
                  </div>
                  <div
                    className="text-[11px] truncate"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {artifact.language} · {threadTitle}
                  </div>
                </div>
              </button>
            ))
          )
        ) : !showRecent && tab === "all" ? (
          <div
            className="px-3 py-8 text-center text-xs leading-relaxed"
            style={{ color: "var(--text-muted)" }}
          >
            {t("sidebar.historyHidden")}
          </div>
        ) : filteredThreads.length === 0 ? (
          <div
            className="px-3 py-8 text-center text-xs leading-relaxed"
            style={{ color: "var(--text-muted)" }}
          >
            {tab === "starred"
              ? t("sidebar.noStarred")
              : t("sidebar.noConv")}
          </div>
        ) : (
          filteredThreads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            return (
              <div
                key={thread.id}
                className="group flex items-center justify-between gap-1 px-2.5 py-2 rounded-xl transition-colors"
                style={{
                  backgroundColor: isActive ? "var(--bg-card)" : "transparent",
                }}
              >
                <button
                  type="button"
                  onClick={() => onSelectThread(thread.id)}
                  className="min-w-0 flex-1 text-left cursor-pointer"
                >
                  <div
                    className={`text-xs truncate ${
                      isActive ? "font-semibold" : "font-medium"
                    }`}
                    style={{
                      color: isActive
                        ? "var(--text-heading)"
                        : "var(--text-primary)",
                    }}
                  >
                    {thread.title}
                  </div>
                </button>

                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity shrink-0">
                  <button
                    type="button"
                    onClick={() => onToggleStar(thread.id)}
                    title={thread.starred ? tr("Unstar session") : tr("Star session")}
                    className="p-1 rounded-md hover:opacity-75 cursor-pointer"
                    style={{
                      color: thread.starred
                        ? "var(--accent-warm)"
                        : "var(--text-muted)",
                    }}
                  >
                    <Star
                      className="w-3.5 h-3.5"
                      fill={thread.starred ? "currentColor" : "none"}
                    />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteThread(thread.id)}
                    title={t("sidebar.delete")}
                    className="p-1 rounded-md hover:opacity-75 cursor-pointer"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Bottom Workspace Utilities */}
      <div
        className="p-3 border-t space-y-1"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <button
          type="button"
          onClick={onOpenPseudonymiser}
          className="w-full flex items-center justify-between px-2.5 py-2 rounded-xl text-xs font-medium transition-colors hover:opacity-85 cursor-pointer"
          style={{ color: "var(--text-primary)" }}
        >
          <span className="inline-flex items-center gap-2 whitespace-nowrap">
            <UserCheck className="w-4 h-4 opacity-75" />
            <span>{t("sidebar.pseudonymiser")}</span>
          </span>
          <span
            className="font-code text-[11px] px-1.5 py-0.2 rounded"
            style={{
              backgroundColor: "var(--bg-canvas)",
              color: "var(--accent-primary)",
            }}
          >
            {pseudonymRuleCount} {t("sidebar.rules")}
          </span>
        </button>

        <button
          type="button"
          onClick={onOpenVault}
          className="w-full flex items-center justify-between px-2.5 py-2 rounded-xl text-xs font-medium transition-colors hover:opacity-85 cursor-pointer"
          style={{ color: "var(--text-primary)" }}
        >
          <span className="inline-flex items-center gap-2 whitespace-nowrap">
            <Lock className="w-4 h-4 opacity-75" />
            <span>{t("sidebar.vault")}</span>
          </span>
          <span
            className="font-code text-[10px] font-semibold px-1.5 py-0.2 rounded"
            style={{
              backgroundColor: "var(--bg-canvas)",
              color: "var(--accent-warm)",
            }}
          >
            AES-256
          </span>
        </button>

        <button
          type="button"
          onClick={onOpenProjectKnowledge}
          className="w-full flex items-center justify-between px-2.5 py-2 rounded-xl text-xs font-medium transition-colors hover:opacity-85 cursor-pointer"
          style={{ color: "var(--text-primary)" }}
        >
          <span className="inline-flex items-center gap-2 whitespace-nowrap">
            <BookOpen className="w-4 h-4 opacity-75" />
            <span>{t("sidebar.knowledge")}</span>
          </span>
          <span
            className="font-code text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {projectDocCount}
          </span>
        </button>

        <button
          type="button"
          onClick={onOpenAppearance}
          className="w-full flex items-center justify-between px-2.5 py-2 rounded-xl text-xs font-medium transition-colors hover:opacity-85 cursor-pointer"
          style={{ color: "var(--text-primary)" }}
        >
          <span className="inline-flex items-center gap-2 whitespace-nowrap">
            <SlidersHorizontal className="w-4 h-4 opacity-75" />
            <span>{t("sidebar.appearance")}</span>
          </span>
        </button>
      </div>
    </aside>
  );
};
