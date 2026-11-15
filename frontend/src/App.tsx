import React, { useEffect, useMemo, useRef, useState } from "react";
import { tr } from "./i18n";
import { useI18n } from "./i18n";
import {
  AlertCircle,
  ArrowRight,
  Check,
  Copy,
  ExternalLink,
  FileCode2,
  FileText,
  Lock,
  PanelLeftOpen,
  Play,
  RotateCcw,
  SlidersHorizontal,
  UserCheck,
} from "lucide-react";
import { AgentTrace } from "./components/AgentTrace";
import { toAgentSteps } from "./api/agentSteps";
import { AppearanceDrawer } from "./components/AppearanceDrawer";
import { ArtifactWorkbench } from "./components/ArtifactWorkbench";
import { Composer } from "./components/Composer";
import { EncryptedVaultModal } from "./components/EncryptedVaultModal";
import { HeaderActionsBar } from "./components/HeaderActionsBar";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import { ProjectKnowledgeModal } from "./components/ProjectKnowledgeModal";
import { PseudonymiserPanel } from "./components/PseudonymiserPanel";
import { SendPreviewModal } from "./components/SendPreviewModal";
import { Sidebar } from "./components/Sidebar";
import { SanadAvatar } from "./components/SanadAvatar";
import type { AvatarMode } from "./components/SanadAvatar";
import { LegalCalculatorsModal } from "./components/LegalCalculatorsModal";
import { OperatingModeModal } from "./components/OperatingModeModal";
import { BoUpdateModal } from "./components/BoUpdateModal";
import { ApiKeysModal } from "./components/ApiKeysModal";
import { SituationNavigatorModal } from "./components/SituationNavigatorModal";
import { ConcordanceWizardModal } from "./components/ConcordanceWizardModal";
import { StatuteBrowserModal } from "./components/StatuteBrowserModal";
import { AuditTraceModal } from "./components/AuditTraceModal";
import { ReportErrorModal } from "./components/ReportErrorModal";
import { ConsultationPrepModal } from "./components/ConsultationPrepModal";
import {
  INITIAL_PROJECT_DOCS,
  SEED_THREADS,
  REMOVED_DEMO_THREAD_IDS,
  REMOVED_DEMO_DOC_IDS,
  STARTER_PROMPTS,
} from "./data/seedThreads";
import { type HistoryTurn, prepareQuery, runQuery, getProgress, patchSettings, toBackendMode, listTraces, getTraceDetail, clearHistory, createErrorReport } from "./api/legalrag";
import { traceToAudit } from "./api/traceToAudit";
import { rulesToTerms } from "./api/useServerMasking";
import { deleteDocument, ingestAttachment, type IngestResult } from "./api/documents";
import { DocumentReviewModal } from "./components/DocumentReviewModal";
import { answerToMessage } from "./api/answerToMessage";
import { applyWorkspaceTheme } from "./themes/palettes";
import { DRAG_REGION, IS_DESKTOP_FRAMELESS, WindowControls } from "./components/WindowControls";
import { IS_ANDROID, openAndroidSetup } from "./platform";
import { usePresence } from "./usePresence";
import {
  AgentStep,
  ArtifactItem,
  ArtifactKind,
  AttachmentItem,
  AuditTraceRecord,
  ChatMessage,
  ChatThread,
  CitizenSituation,
  GroundingSource,
  LayoutDensity,
  OperatingMode,
  ProjectDoc,
  PseudonymMapping,
  StepStatus,
  ThemeId,
  VaultItem,
  WorkspaceSettings,
} from "./types/agent";
import {
  DEFAULT_INITIAL_MAPPINGS,
  restoreRealEntities,
} from "./utils/pseudonymiser";

const DEFAULT_SETTINGS: WorkspaceSettings = {
  theme: ThemeId.Mono,
  darkMode: false,
  headingScale: 100,
  bodyScale: 100,
  density: LayoutDensity.Comfy,
  showContinueCard: true,
  showExplorePrompts: true,
  showRecentSidebar: true,
  thinkingMode: true,
  thinkingBudget: 8000,
  enableWebSearch: true,
  systemInstruction: "",
  autoPseudonymise: true,
  alwaysPreviewBeforeSend: false,
  restorePseudonymsInReplies: true,
  operatingMode: "hybrid",
  audienceMode: "citizen",
  asOfDate: "", // empty = today (the backend then applies the law in force today, newest bulletin included)
  strictMode: true,
};

const INITIAL_AUDIT_LOGS: AuditTraceRecord[] = [
  {
    id: "audit-init-001",
    timestamp: "2026-10-24 14:32:05",
    rawQuestionLength: 148,
    pseudonymisedQuery: "Société [ORG_A] et Salarié [PERSON_B] - Rupture conventionnelle et indemnité légale Art. 53 Loi 65-99.",
    asOfDate: "2026-10-24",
    operatingMode: "hybrid",
    retrievedChunkIds: ["MA_LABOR_6599_ART_53", "MA_SMIG_DECREE_225983"],
    verification: {
      citationExists: true,
      quoteMatches: true,
      placeholdersIntact: true,
      versionValid: true,
      noStrayNumbers: true,
      claimSupportRate: 98,
      overallStatus: "passed",
    },
    outboundPayloadJson: JSON.stringify(
      {
        model: "gemini-3.8-flash",
        temperature: 0.1,
        mode: "hybrid_pseudonymised",
        promptTokens: 420,
      },
      null,
      2
    ),
    claimsCount: 4,
    latencyMs: 1180,
  },
];

const STORAGE_KEYS = {
  settings: "atelier_workspace_settings_v1",
  threads: "atelier_workspace_threads_v4",
  docs: "atelier_workspace_docs_v1",
  mappings: "sanad_pseudonym_mappings_v1",
  vault: "sanad_encrypted_vault_v1",
  auditLogs: "sanad_audit_logs_v1",
};

function getTimeGreeting(t: (k: string) => string): string {
  const hour = new Date().getHours();
  if (hour < 12) return t("greet.morning");
  if (hour < 18) return t("greet.afternoon");
  return t("greet.evening");
}

function getAvatarMode(isStreaming: boolean, text: string): AvatarMode {
  if (isStreaming) return "thinking";
  if (text.trim().length > 0) return "typing";
  return "idle";
}

function getHostname(uri: string): string {
  try {
    return new URL(uri).hostname.replace(/^www\./, "");
  } catch {
    return "web";
  }
}

function newThreadId(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  } catch {
    /* older browser: fall through */
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function threadIdFromPath(): string | null {
  const m = window.location.pathname.match(/^\/c\/([^/]+)\/?$/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function App() {
  const { t, lang } = useI18n();
  const [settings, setSettings] = useState<WorkspaceSettings>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.settings);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (!parsed.theme || parsed.theme === ThemeId.Stone) {
          parsed.theme = ThemeId.Mono;
        }
        if (parsed.theme === "balloura") parsed.theme = ThemeId.Ember; // renamed theme
        if (parsed.operatingMode === "cloud-assisted") parsed.operatingMode = "hybrid"; // cloud-assisted mode is disabled
        if (parsed.asOfDate === "2026-10-24") parsed.asOfDate = ""; // old built-in demo date: it hid every text published after it
        return { ...DEFAULT_SETTINGS, ...parsed };
      }
    } catch {
      // Ignore storage error
    }
    return DEFAULT_SETTINGS;
  });

  const [threads, setThreads] = useState<ChatThread[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.threads);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          // demo sessions of earlier versions are dropped
          return parsed.filter((t: ChatThread) => !REMOVED_DEMO_THREAD_IDS.includes(t.id));
        }
      }
    } catch {
      // Ignore storage error
    }
    return SEED_THREADS;
  });
  const threadsRef = useRef(threads);
  const firstUrlSync = useRef(true);
  threadsRef.current = threads;

  const [projectDocs, setProjectDocs] = useState<ProjectDoc[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.docs);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) return parsed.filter((d: ProjectDoc) => !REMOVED_DEMO_DOC_IDS.includes(d.id));
      }
    } catch {
      // Ignore storage error
    }
    return INITIAL_PROJECT_DOCS;
  });

  // Each session has its own address: /c/<uuid>. Opening that address (or going back / forward) opens that session; "/" is the home screen.
  const [activeThreadId, setActiveThreadId] = useState<string | null>(() => {
    const id = threadIdFromPath();
    return id && threads.some((t) => t.id === id) ? id : null;
  });
  useEffect(() => {
    const want = activeThreadId ? `/c/${encodeURIComponent(activeThreadId)}` : "/";
    const first = firstUrlSync.current;
    firstUrlSync.current = false;
    if (window.location.pathname === want) return;
    // first render on an unknown /c/<id> (deleted session, other browser): replace it, so "back" does not return to a dead address
    const replace = first;
    window.history[replace ? "replaceState" : "pushState"]({ thread: activeThreadId }, "", want + window.location.search);
  }, [activeThreadId]);
  useEffect(() => {
    const onPop = () => {
      const id = threadIdFromPath();
      setActiveThreadId(id && threadsRef.current.some((t) => t.id === id) ? id : null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.innerWidth >= 1024 : true
  );
  const [rightPanel, setRightPanel] = useState<
    "none" | "artifact" | "appearance" | "pseudonymiser"
>("none");
  const [vaultModalOpen, setVaultModalOpen] = useState<boolean>(false);
  // kept on screen while they slide out (see usePresence)
  const sidebarP = usePresence(sidebarOpen, false);
  const panelP = usePresence<typeof rightPanel>(rightPanel, "none");
  const [isPhone, setIsPhone] = useState(() => typeof window !== "undefined" && window.innerWidth < 640);
  useEffect(() => {
    const onResize = () => setIsPhone(window.innerWidth < 640);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const [sendPreviewOpen, setSendPreviewOpen] = useState<boolean>(false);
  const [newTopic, setNewTopic] = useState<boolean>(false); // the next question ignores the earlier turns of the chat

  const [pseudonymMappings, setPseudonymMappings] = useState<
    PseudonymMapping[]
  >(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.mappings);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // Ignore storage error
    }
    return DEFAULT_INITIAL_MAPPINGS;
  });

  const [vaultItems, setVaultItems] = useState<VaultItem[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.vault);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) return parsed;
      }
    } catch {
      // Ignore storage error
    }
    return [];
  });

  const [selectedArtifact, setSelectedArtifact] =
    useState<ArtifactItem | null>(null);
  const [workbenchExpanded, setWorkbenchExpanded] = useState<boolean>(false);
  const [knowledgeModalOpen, setKnowledgeModalOpen] = useState<boolean>(false);
  const [operatingModeModalOpen, setOperatingModeModalOpen] = useState<boolean>(false);
  const [boUpdateModalOpen, setBoUpdateModalOpen] = useState<boolean>(false);
  const [apiKeysModalOpen, setApiKeysModalOpen] = useState<boolean>(false);
  const [calculatorsModalOpen, setCalculatorsModalOpen] = useState<boolean>(false);
  const [concordanceModalOpen, setConcordanceModalOpen] = useState<boolean>(false);
  const [situationsModalOpen, setSituationsModalOpen] = useState<boolean>(false);
  const [statutesModalOpen, setStatutesModalOpen] = useState<boolean>(false);
  const [auditTraceModalOpen, setAuditTraceModalOpen] = useState<boolean>(false);
  const [reportErrorModalOpen, setReportErrorModalOpen] = useState<boolean>(false);
  const [consultationPrepModalOpen, setConsultationPrepModalOpen] = useState<boolean>(false);
  const [selectedSituationForPrep, setSelectedSituationForPrep] = useState<CitizenSituation | null>(null);

  const [auditLogs, setAuditLogs] = useState<AuditTraceRecord[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.auditLogs);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // Ignore
    }
    return INITIAL_AUDIT_LOGS;
  });

  const [inputText, setInputText] = useState<string>("");
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    applyWorkspaceTheme(settings);
    try {
      localStorage.setItem(STORAGE_KEYS.settings, JSON.stringify(settings));
    } catch {
      // Ignore storage quota
    }
  }, [settings]);

  useEffect(() => {
    try {
      // Vault plaintext must never be written to localStorage (it would defeat the encrypted vault).
      const safeThreads = threads.map((t) => ({
        ...t,
        messages: t.messages.map((m) =>
          m.attachments?.some((a) => a.source === "vault")
            ? { ...m, attachments: m.attachments.map((a) => (a.source === "vault" ? { ...a, textContent: undefined } : a)) }
            : m
        ),
      }));
      localStorage.setItem(STORAGE_KEYS.threads, JSON.stringify(safeThreads));
    } catch {
      // Ignore storage quota
    }
  }, [threads]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.docs, JSON.stringify(projectDocs));
    } catch {
      // Ignore storage quota
    }
  }, [projectDocs]);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEYS.mappings,
        JSON.stringify(pseudonymMappings)
      );
    } catch {
      // Ignore storage quota
    }
  }, [pseudonymMappings]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.vault, JSON.stringify(vaultItems));
    } catch {
      // Ignore storage quota
    }
  }, [vaultItems]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.auditLogs, JSON.stringify(auditLogs));
    } catch {
      // Ignore storage quota
    }
  }, [auditLogs]);

  const activeThread = useMemo(
    () => threads.find((t) => t.id === activeThreadId) || null,
    [threads, activeThreadId]
  );

  const activeThreadArtifacts = useMemo(() => {
    if (!activeThread) return [];
    const list: ArtifactItem[] = [];
    for (const msg of activeThread.messages) {
      if (msg.artifacts) {
        list.push(...msg.artifacts);
      }
    }
    return list;
  }, [activeThread]);

  const latestThreadWithArtifact = useMemo(() => {
    for (const t of threads) {
      for (let i = t.messages.length - 1; i >= 0; i--) {
        const arts = t.messages[i].artifacts;
        if (arts && arts.length > 0) {
          return { thread: t, artifact: arts[arts.length - 1] };
        }
      }
    }
    return null;
  }, [threads]);

  useEffect(() => {
    if (activeThread && activeThread.messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [activeThread?.messages.length, isStreaming]);

  const lastTraceIdRef = useRef<string | null>(null);
  const [docReview, setDocReview] = useState<{ docs: IngestResult[]; resolve: (d: IngestResult[] | null) => void } | null>(null);
  const askDocReview = (docs: IngestResult[]) =>
    new Promise<IngestResult[] | null>((resolve) =>
      setDocReview({
        docs,
        resolve: (d) => {
          setDocReview(null);
          resolve(d);
        },
      })
    );

  // Audit trace modal: show the backend's real traces (kept locally, encrypted) next to local report entries.
  useEffect(() => {
    if (!auditTraceModalOpen) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await listTraces(30);
        const recs = await Promise.all(
          list.map((r) => getTraceDetail(r.trace_id).then((d) => traceToAudit(r.created_at, d)).catch(() => null))
        );
        if (cancelled) return;
        const fresh = recs.filter((r): r is AuditTraceRecord => !!r);
        setAuditLogs((prev) => [
          ...fresh,
          ...prev.filter((p) => p.id.startsWith("report-") && !fresh.some((f) => f.id === p.id)),
        ]);
      } catch {
        /* backend offline: keep what is stored locally */
      }
    })();
    return () => { cancelled = true; };
  }, [auditTraceModalOpen]);

  // Keep backend preferences in sync with the UI (mode, audience, strict mode).
  useEffect(() => {
    patchSettings({
      mode: toBackendMode(settings.operatingMode || "hybrid"),
      citizen_mode: (settings.audienceMode || "citizen") === "citizen",
      strict_mode: !!settings.strictMode,
      explain_language: null, // null = the answer follows the language of the question (Arabic question -> Arabic answer); also clears an older saved "en"
    }).catch(() => {
      /* backend offline or token missing: surfaced when a message is sent */
    });
  }, [settings.operatingMode, settings.audienceMode, settings.strictMode, lang]);

  const updateSettings = (patch: Partial<WorkspaceSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  };

  const resetAppearance = () => {
    setSettings((prev) => ({
      ...DEFAULT_SETTINGS,
      thinkingMode: prev.thinkingMode,
      enableWebSearch: prev.enableWebSearch,
      systemInstruction: prev.systemInstruction,
    }));
  };

  const handleOpenArtifact = (artifact: ArtifactItem) => {
    setSelectedArtifact(artifact);
    setRightPanel("artifact");
  };

  const handleSelectThread = (threadId: string) => {
    setActiveThreadId(threadId);
    const target = threads.find((t) => t.id === threadId);
    if (target) {
      const foundArts: ArtifactItem[] = [];
      for (const m of target.messages) {
        if (m.artifacts) foundArts.push(...m.artifacts);
      }
      if (foundArts.length > 0) {
        setSelectedArtifact(foundArts[foundArts.length - 1]);
        if (window.innerWidth >= 1100) {
          setRightPanel("artifact");
        }
      } else if (rightPanel === "artifact") {
        setRightPanel("none");
        setSelectedArtifact(null);
      }
    }
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  };

  const handleNewChat = () => {
    if (isStreaming) {
      abortControllerRef.current?.abort();
      setIsStreaming(false);
    }
    setActiveThreadId(null);
    setInputText("");
    setAttachments([]);
    if (rightPanel === "artifact") {
      setRightPanel("none");
      setSelectedArtifact(null);
    }
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  };

  const handleToggleStar = (threadId: string) => {
    setThreads((prev) =>
      prev.map((t) => (t.id === threadId ? { ...t, starred: !t.starred } : t))
    );
  };

  const handleDeleteThread = (threadId: string) => {
    setThreads((prev) => prev.filter((t) => t.id !== threadId));
    if (activeThreadId === threadId) {
      setActiveThreadId(null);
      if (rightPanel === "artifact") {
        setRightPanel("none");
        setSelectedArtifact(null);
      }
    }
  };

  const updateAssistantMessage = (
    threadId: string,
    messageId: string,
    updater: (msg: ChatMessage) => ChatMessage
  ) => {
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t;
        return {
          ...t,
          updatedAt: new Date().toISOString(),
          messages: t.messages.map((m) => (m.id === messageId ? updater(m) : m)),
        };
      })
    );
  };

  const generateThreadTitleAsync = async (threadId: string, prompt: string) => {
    try {
      // Titles are derived locally (the backend has no title endpoint); never send the prompt elsewhere.
      const title = prompt.replace(/\s+/g, " ").trim().slice(0, 60);
      if (title) {
        setThreads((prev) =>
          prev.map((t) => (t.id === threadId ? { ...t, title } : t))
        );
      }
    } catch {
      // Keep fallback title cleanly
    }
  };

  const runAgentTurn = async (
    targetThreadId: string,
    historyMessages: ChatMessage[]
  ) => {
    const assistantMsgId = `msg-ai-${Date.now()}`;
    const placeholderAssistant: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      steps: [],
      artifacts: [],
      sources: [],
      isStreaming: true,
    };

    setThreads((prev) =>
      prev.map((t) =>
        t.id === targetThreadId
          ? {
              ...t,
              updatedAt: new Date().toISOString(),
              messages: [...historyMessages, placeholderAssistant],
            }
          : t
      )
    );

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsStreaming(true);
    let docIdsForCleanup: string[] = [];

    try {
      const lastUser = [...historyMessages].reverse().find((m) => m.role === "user");
      const typed = (lastUser?.content || "").trim();
      const atts = (lastUser?.attachments || []).filter((a) => a.textContent !== undefined || a.dataUrl);
      if (!typed && atts.length === 0) throw new Error(tr("Nothing to send."));

      // Attachments go through the backend: text extraction / OCR on the device, detection + masking, confidence gate.
      // Only masked, question-relevant excerpts can ever be sent; the user confirms the masked text first.
      const caseId = Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, "0")).join("");
      const skipped: string[] = [];
      for (const a of lastUser?.attachments || []) {
        if (a.textContent === undefined && !a.dataUrl) skipped.push(a.name);
      }
      const ingested: IngestResult[] = [];
      for (const a of atts) {
        try {
          ingested.push(await ingestAttachment(a, caseId));
        } catch (e) {
          skipped.push(`${a.name} (${(e as Error).message})`);
        }
      }
      docIdsForCleanup = ingested.map((d) => d.doc_id);
      let usableDocs = ingested;
      if (ingested.some((d) => d.status === "review_required" || d.warnings.length > 0 || d.sensitive)) {
        const confirmed = await askDocReview(ingested);
        if (!confirmed) {
          updateAssistantMessage(targetThreadId, assistantMsgId, (msg) => ({
            ...msg,
            content: "Cancelled: the attachments were not confirmed, so nothing was sent.",
          }));
          return;
        }
        usableDocs = confirmed;
      }
      const question =
        typed || (usableDocs.length ? tr("Summarise the attached document and the rules of law that apply to it.") : "");
      if (!question) throw new Error(tr("Nothing to send."));

      const stepId = `step-${Date.now()}`;
      const t0 = Date.now();
      updateAssistantMessage(targetThreadId, assistantMsgId, (msg) => ({
        ...msg,
        steps: [
          {
            id: stepId,
            kind: "search",
            title: tr("Pseudonymising and retrieving law"),
            detail: tr("Local backend: pseudonymise, retrieve, generate, verify"),
            status: StepStatus.Running,
          },
        ],
      }));

      // The chat so far (everything before this question): the backend pseudonymises it and uses it to understand follow-ups.
      const lastUserIdx = historyMessages.lastIndexOf(lastUser as ChatMessage);
      const history: HistoryTurn[] = historyMessages
        .slice(0, lastUserIdx < 0 ? 0 : lastUserIdx)
        .filter((m) => !m.error && m.content.trim())
        .slice(-30)
        .map((m) => ({
          role: m.role,
          text: m.role === "assistant" ? m.content.split(/\n\*\*Sources\*\*/)[0] : m.content,
          cited: (m.artifacts || [])
            .flatMap((a) => a.documentMeta?.snippets ?? [])
            .map((sn) => sn.provisionId)
            .filter((x): x is string => !!x),
        }));

      // 1) prepare: backend pseudonymises on-device (nothing leaves yet)
      const prepared = await prepareQuery(
        {
          question,
          history,
          new_topic: newTopic || undefined,
          session_id: targetThreadId, // the backend keeps the whole chat (summary + recent turns); history only seeds it after a restart
          mask: false, // chat text is sent as written; only uploaded files are masked (by the backend, always)
          as_of: settings.asOfDate || null,
          extra_sensitive_terms: settings.autoPseudonymise ? rulesToTerms(pseudonymMappings) : [],
          case_id: usableDocs.length ? caseId : undefined,
          document_ids: usableDocs.map((d) => d.doc_id),
        },
        controller.signal
      );
      setNewTopic(false); // one question only
      // while the backend works, show what the agent is doing (it records each step; the app polls it)
      let polling = true;
      const poll = async () => {
        while (polling) {
          try {
            const p = await getProgress(prepared.query_id, controller.signal);
            if (polling && p.steps.length) {
              updateAssistantMessage(targetThreadId, assistantMsgId, (msg) => ({ ...msg, steps: toAgentSteps(p.steps) }));
            }
          } catch {
            /* the next tick tries again */
          }
          await new Promise((r) => setTimeout(r, 600));
        }
      };
      void poll();
      // 2) run: the user already approved via the send preview / composer
      let answer: Awaited<ReturnType<typeof runQuery>>;
      try {
        answer = await runQuery(
        prepared.query_id,
        {
          approved: true,
          review_confirmed: settings.alwaysPreviewBeforeSend,
          // Deep (16K) and Maximum (32K) thinking budgets also switch on the deeper search (judge the passages, search again)
          depth: !settings.thinkingMode ? "normal" : (settings.thinkingBudget || 8000) >= 32000 ? "max" : (settings.thinkingBudget || 8000) >= 16000 ? "deep" : "normal",
        },
        controller.signal
      );
      } finally {
        polling = false;
      }

      if (answer.trace_id) lastTraceIdRef.current = answer.trace_id;
      const { content: answerText, sources, artifacts: evidenceArtifacts } = answerToMessage(answer);
      const content = skipped.length
        ? `${answerText}\n\n_Not sent (could not be read locally): ${skipped.join(", ")}_`
        : answerText;
      updateAssistantMessage(targetThreadId, assistantMsgId, (msg) => ({
        ...msg,
        content: settings.restorePseudonymsInReplies
          ? restoreRealEntities(content, pseudonymMappings)
          : content,
        sources,
        artifacts: [...(msg.artifacts || []), ...evidenceArtifacts],
        steps: answer.steps?.length
          ? toAgentSteps(answer.steps)
          : (msg.steps || []).map((s) =>
              s.id === stepId
                ? {
                    ...s,
                    status: StepStatus.Completed,
                    durationMs: Date.now() - t0,
                    detail: tr("Status: {0}; {1} source(s)", [answer.status, answer.sources?.length ?? 0]),
                  }
                : s
            ),
      }));
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        updateAssistantMessage(targetThreadId, assistantMsgId, (msg) => ({
          ...msg,
          error:
            err instanceof Error
              ? err.message
              : tr("Connection interrupted while streaming response."),
        }));
      }
    } finally {
      // The backend keeps only encrypted extracted text; remove it as soon as the turn is over.
      docIdsForCleanup.forEach((id) => deleteDocument(id).catch(() => {}));
      updateAssistantMessage(targetThreadId, assistantMsgId, (msg) => ({
        ...msg,
        isStreaming: false,
        steps: (msg.steps || []).map((s) =>
          s.status === StepStatus.Running
            ? { ...s, status: StepStatus.Completed }
            : s
        ),
      }));
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleSendMessage = async (overridePrompt?: string, keepAttachments = false) => {
    if (
      settings.alwaysPreviewBeforeSend &&
      overridePrompt === undefined &&
      (inputText.trim().length > 0 || attachments.length > 0)
    ) {
      setSendPreviewOpen(true);
      return;
    }

    let textToSend = (
      overridePrompt !== undefined ? overridePrompt : inputText
    ).trim();

    if (!textToSend && attachments.length === 0) return;
    if (isStreaming) return;

    // Masking is done ONCE, by the local backend (rules + Arabic NER + your saved rules). No second local pass,
    // so the placeholders you saw in the preview are exactly what is sent.

    const currentAttachments = overridePrompt !== undefined && !keepAttachments ? [] : attachments;

    const userMsg: ChatMessage = {
      id: `msg-user-${Date.now()}`,
      role: "user",
      content: textToSend,
      createdAt: new Date().toISOString(),
      attachments:
        currentAttachments.length > 0 ? currentAttachments : undefined,
    };

    if (overridePrompt === undefined || keepAttachments) {
      setInputText("");
      setAttachments([]);
    }

    let threadId = activeThreadId;
    let nextHistory: ChatMessage[] = [];

    if (!threadId) {
      threadId = newThreadId();
      const provisionalTitle =
        textToSend.slice(0, 44) ||
        currentAttachments[0]?.name ||
        tr("New Session");
      const newThread: ChatThread = {
        id: threadId,
        title: provisionalTitle,
        updatedAt: new Date().toISOString(),
        starred: false,
        messages: [userMsg],
      };
      nextHistory = [userMsg];
      setThreads((prev) => [newThread, ...prev]);
      setActiveThreadId(threadId);
      if (textToSend) {
        generateThreadTitleAsync(threadId, textToSend);
      }
    } else {
      const existing = threads.find((t) => t.id === threadId);
      nextHistory = existing ? [...existing.messages, userMsg] : [userMsg];
      setThreads((prev) =>
        prev.map((t) =>
          t.id === threadId
            ? {
                ...t,
                updatedAt: new Date().toISOString(),
                messages: nextHistory,
              }
            : t
        )
      );
    }

    await runAgentTurn(threadId, nextHistory);
  };

  const handleRetryLastTurn = async () => {
    if (!activeThread || isStreaming) return;
    const msgs = activeThread.messages;
    if (msgs.length === 0) return;

    const trimmed =
      msgs[msgs.length - 1].role === "assistant" ? msgs.slice(0, -1) : msgs;
    if (trimmed.length === 0) return;

    await runAgentTurn(activeThread.id, trimmed);
  };

  const handleStopStreaming = () => {
    abortControllerRef.current?.abort();
    setIsStreaming(false);
  };

  const handleCopyMessage = async (msg: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedMessageId(msg.id);
      setTimeout(() => setCopiedMessageId(null), 1800);
    } catch {
      // Clipboard ignored safely
    }
  };

  const isComfy = settings.density === LayoutDensity.Comfy;

  return (
    <div
      className="h-dvh w-full overflow-clip flex relative"
      style={{
        backgroundColor: "var(--bg-canvas)",
        color: "var(--text-primary)",
      }}
    >
      {/* Mobile Sidebar Backdrop */}
      {sidebarP.shown && (
        <div
          onClick={() => setSidebarOpen(false)}
          className={`fixed inset-0 z-30 bg-black/25 lg:hidden ${sidebarP.closing ? "anim-fade-out" : "anim-fade-in"}`}
        />
      )}

      {/* Left Workspace Sidebar */}
      {sidebarP.shown && (
        <div className={`fixed inset-y-0 left-0 z-40 lg:static lg:z-auto h-full ${sidebarP.closing ? "anim-out-left" : "anim-in-left"}`}>
          <Sidebar
            threads={threads}
            activeThreadId={activeThreadId}
            showRecent={settings.showRecentSidebar}
            projectDocCount={projectDocs.length}
            onSelectThread={handleSelectThread}
            onNewChat={handleNewChat}
            onToggleStar={handleToggleStar}
            onDeleteThread={handleDeleteThread}
            onSelectArtifactFromLibrary={(threadId, artifact) => {
              setActiveThreadId(threadId);
              handleOpenArtifact(artifact);
              if (window.innerWidth < 1024) setSidebarOpen(false);
            }}
            onOpenProjectKnowledge={() => setKnowledgeModalOpen(true)}
            onOpenAppearance={() =>
              setRightPanel((p) => (p === "appearance" ? "none" : "appearance"))
            }
            onOpenPseudonymiser={() =>
              setRightPanel((p) =>
                p === "pseudonymiser" ? "none" : "pseudonymiser"
              )
            }
            onOpenVault={() => setVaultModalOpen(true)}
            vaultItemCount={vaultItems.length}
            pseudonymRuleCount={pseudonymMappings.length}
            onCollapse={() => setSidebarOpen(false)}
            operatingMode={settings.operatingMode || "hybrid"}
            audienceMode={settings.audienceMode || "citizen"}
            asOfDate={settings.asOfDate || new Date().toISOString().slice(0, 10)}
            onOpenOperatingMode={IS_ANDROID ? undefined : () => setOperatingModeModalOpen(true)}
            onOpenBoUpdate={IS_ANDROID ? undefined : () => setBoUpdateModalOpen(true)}
            onOpenApiKeys={IS_ANDROID ? openAndroidSetup : () => setApiKeysModalOpen(true)}
            onToggleAudienceMode={() =>
              updateSettings({
                audienceMode:
                  settings.audienceMode === "citizen"
                    ? "professional"
                    : "citizen",
              })
            }
            onOpenCalculators={() => setCalculatorsModalOpen(true)}
            onOpenSituations={() => setSituationsModalOpen(true)}
            onOpenStatutes={() => setStatutesModalOpen(true)}
            onOpenAuditTrace={() => setAuditTraceModalOpen(true)}
            onOpenConcordance={() => setConcordanceModalOpen(true)}
            onOpenConsultation={() => setConsultationPrepModalOpen(true)}
          />
        </div>
      )}

      {/* Main Center Conversation Viewport */}
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-clip">
        {/* Clean Contextual Top Bar */}
        <header
          className={`flex items-center justify-between gap-3 px-4 sm:px-5 py-3 border-b shrink-0 min-w-0 ${IS_DESKTOP_FRAMELESS ? DRAG_REGION : ""}`}
          style={{
            backgroundColor: "var(--bg-canvas)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <div className="flex items-center gap-2 text-xs min-w-0 flex-1">
            {!sidebarOpen && (
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                title={tr("Open sidebar")}
                className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer shrink-0"
                style={{ color: "var(--text-muted)" }}
              >
                <PanelLeftOpen className="w-4 h-4" />
              </button>
            )}
            <div className="flex items-center gap-2 text-xs min-w-0 truncate">
              <button
                type="button"
                onClick={handleNewChat}
                className="font-editorial font-medium text-sm hover:opacity-80 cursor-pointer whitespace-nowrap shrink-0"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Sanad")}
              </button>
              <span aria-hidden="true" style={{ color: "var(--text-muted)" }}>
                /
              </span>
              <span
                className="truncate font-medium text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {activeThread ? activeThread.title : tr("New session")}
              </span>
            </div>
          </div>

          <HeaderActionsBar
            activeThreadArtifacts={activeThreadArtifacts}
            rightPanel={rightPanel}
            onToggleArtifacts={() => {
              if (rightPanel === "artifact") {
                setRightPanel("none");
              } else {
                setSelectedArtifact(
                  selectedArtifact ||
                    activeThreadArtifacts[activeThreadArtifacts.length - 1]
                );
                setRightPanel("artifact");
              }
            }}
          />
          <WindowControls />
        </header>

        {/* Home Screen vs Active Thread Conversation */}
        {!activeThread || activeThread.messages.length === 0 ? (
          <div key="home" className="flex-1 overflow-y-auto px-4 sm:px-5 py-5 sm:py-8 md:py-12 anim-page">
            <div className="max-w-2xl mx-auto flex flex-col justify-center min-h-full space-y-5 sm:space-y-7">
              {/* Calm Editorial Greeting */}
              <div className="flex items-start gap-3 sm:gap-4 md:gap-5">
                <SanadAvatar
                  size={isPhone ? 54 : 84}
                  mode={getAvatarMode(isStreaming, inputText)}
                  typingProgress={Math.min(inputText.length / 80, 1)}
                  className="mt-1"
                />
                <div className="space-y-2 min-w-0">
                  <div
                    className="text-xs font-medium tracking-wide"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {getTimeGreeting(t)}
                    <span aria-hidden="true"> · </span>
                    <em className="font-editorial font-normal">{tr("Sanad Assistant")}</em>
                  </div>
                  <h1
                    className="font-editorial font-normal heading-scalable-xl"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {t("home.hero")}
                  </h1>
                </div>
              </div>

              {/* Primary Claude-Style Agent Composer */}
              <Composer
                value={inputText}
                onChange={setInputText}
                onSend={() => handleSendMessage()}
                onStop={handleStopStreaming}
                isStreaming={isStreaming}
                attachments={attachments}
                onAddAttachments={(items) =>
                  setAttachments((prev) => [...prev, ...items])
                }
                onRemoveAttachment={(id) =>
                  setAttachments((prev) => prev.filter((a) => a.id !== id))
                }
                thinkingMode={settings.thinkingMode}
                onToggleThinking={() =>
                  updateSettings({ thinkingMode: !settings.thinkingMode })
                }
                thinkingBudget={settings.thinkingBudget}
                onChangeThinkingBudget={(budget) =>
                  updateSettings({ thinkingBudget: budget })
                }
                enableWebSearch={settings.enableWebSearch}
                onToggleWebSearch={() =>
                  updateSettings({ enableWebSearch: !settings.enableWebSearch })
                }
                autoPseudonymise={settings.autoPseudonymise}
                onOpenPseudonymiser={() => setRightPanel("pseudonymiser")}
                onOpenVault={() => setVaultModalOpen(true)}
                onOpenSendPreview={() => setSendPreviewOpen(true)}
                newTopic={newTopic}
                onToggleNewTopic={() => setNewTopic((v) => !v)}
              />

              {/* Continue Card (Toggled via Appearance > Sections > Continue) */}
              {settings.showContinueCard && latestThreadWithArtifact && (
                <div className="space-y-2">
                  <div
                    className="text-xs font-semibold"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {tr("Continue")}
                  </div>
                  <div
                    onClick={() => {
                      setActiveThreadId(latestThreadWithArtifact.thread.id);
                      handleOpenArtifact(latestThreadWithArtifact.artifact);
                    }}
                    className="group p-5 rounded-2xl border flex items-center justify-between gap-4 transition-opacity hover:opacity-95 cursor-pointer"
                    style={{
                      backgroundColor: "var(--bg-card)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    <div className="min-w-0 space-y-1">
                      <div
                        className="text-[11px] font-medium"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {tr("Interactive Artifact ·")}{" "}
                        {latestThreadWithArtifact.artifact.language}
                      </div>
                      <div
                        className="font-editorial text-lg font-medium truncate"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {latestThreadWithArtifact.artifact.title}
                      </div>
                      {latestThreadWithArtifact.artifact.summary && (
                        <p
                          className="text-xs line-clamp-1"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {latestThreadWithArtifact.artifact.summary}
                        </p>
                      )}
                    </div>

                    <button
                      type="button"
                      aria-label={tr("Open artifact session")}
                      className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 transition-transform duration-150 group-hover:scale-105 cursor-pointer"
                      style={{
                        backgroundColor: "var(--accent-primary)",
                        color: "var(--accent-primary-fg)",
                      }}
                    >
                      <Play className="w-4 h-4 fill-current ml-0.5" />
                    </button>
                  </div>
                </div>
              )}

              {/* Explore Starter Prompts (Toggled via Appearance > Sections > Explore) */}
              {settings.showExplorePrompts && (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span
                      className="text-xs font-semibold"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {t("home.explore")}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {STARTER_PROMPTS.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => handleSendMessage(item.prompt)}
                        className="group p-4 rounded-2xl border text-left transition-colors hover:opacity-90 cursor-pointer flex flex-col justify-between gap-2"
                        style={{
                          backgroundColor: "var(--bg-surface)",
                          borderColor: "var(--border-subtle)",
                        }}
                      >
                        <div className="space-y-1">
                          <div
                            className="text-[11px]"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {item.category}
                          </div>
                          <div
                            className="font-editorial text-sm font-medium"
                            style={{ color: "var(--text-heading)" }}
                          >
                            {item.title}
                          </div>
                        </div>

                        <div
                          className="inline-flex items-center gap-1 text-xs font-medium pt-1"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          <span>{tr("Run workflow")}</span>
                          <ArrowRight className="w-3.5 h-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Scrollable Conversation Thread */}
            <div key={activeThread.id} className="flex-1 overflow-y-auto overflow-x-hidden px-3.5 sm:px-6 anim-page">
              <div
                className={`max-w-3xl mx-auto ${
                  isComfy ? "py-8 space-y-8" : "py-5 space-y-5"
                }`}
              >
                {activeThread.messages.map((msg, idx) => {
                  const isUser = msg.role === "user";
                  const isLastAssistant =
                    !isUser && idx === activeThread.messages.length - 1;

                  if (isUser) {
                    const isGoldUserBubble =
                      settings.theme === ThemeId.Emerald && settings.darkMode;
                    return (
                      <div key={msg.id} className="flex justify-end w-full">
                        <div
                          className="w-fit max-w-[95%] sm:max-w-[88%] min-w-0 rounded-2xl px-4 py-3 border space-y-2.5 shadow-xs overflow-hidden box-border"
                          style={{
                            backgroundColor: isGoldUserBubble
                              ? "var(--accent-warm)"
                              : "var(--bg-card)",
                            borderColor: isGoldUserBubble
                              ? "var(--accent-warm)"
                              : "var(--border-subtle)",
                            color: isGoldUserBubble
                              ? "var(--accent-primary-fg)"
                              : "var(--text-primary)",
                          }}
                        >
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="flex flex-col sm:flex-row flex-wrap gap-2 max-w-full">
                              {msg.attachments.map((att) =>
                                att.dataUrl ? (
                                  <img
                                    key={att.id}
                                    src={att.dataUrl}
                                    alt={att.name}
                                    referrerPolicy="no-referrer"
                                    className="max-h-44 max-w-full rounded-xl object-cover border"
                                    style={{
                                      borderColor: "var(--border-subtle)",
                                    }}
                                  />
                                ) : (
                                  <div
                                    key={att.id}
                                    role="button"
                                    onClick={() => {
                                      const matchingDoc = activeThreadArtifacts.find(
                                        (a: ArtifactItem) =>
                                          a.documentMeta?.filename === att.name ||
                                          a.title
                                            .toLowerCase()
                                            .includes(
                                              att.name
                                                .toLowerCase()
                                                .replace(/\.pdf$/, "")
                                            ) ||
                                          att.name
                                            .toLowerCase()
                                            .includes(a.title.toLowerCase())
                                      );
                                      if (matchingDoc) {
                                        handleOpenArtifact(matchingDoc);
                                      }
                                    }}
                                    title={tr("Click to view verified evidence in workbench")}
                                    className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs border transition-all duration-150 hover:opacity-90 hover:shadow-xs cursor-pointer w-full sm:w-auto max-w-full min-w-0 overflow-hidden box-border"
                                    style={{
                                      backgroundColor: isGoldUserBubble
                                        ? "rgba(16, 24, 20, 0.2)"
                                        : "var(--bg-surface)",
                                      borderColor: isGoldUserBubble
                                        ? "rgba(16, 24, 20, 0.3)"
                                        : "var(--border-subtle)",
                                      color: isGoldUserBubble
                                        ? "var(--accent-primary-fg)"
                                        : "var(--text-heading)",
                                    }}
                                  >
                                    <div
                                      className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
                                      style={{
                                        backgroundColor: isGoldUserBubble
                                          ? "rgba(255, 255, 255, 0.15)"
                                          : "rgba(89, 32, 26, 0.1)",
                                        color: isGoldUserBubble
                                          ? "var(--accent-primary-fg)"
                                          : "var(--accent-primary)",
                                      }}
                                    >
                                      <FileText className="w-3.5 h-3.5" />
                                    </div>
                                    <div className="flex flex-col text-left min-w-0 flex-1 overflow-hidden">
                                      <span className="font-semibold text-xs truncate max-w-full block">
                                        {att.name}
                                      </span>
                                      <span className="text-[10px] opacity-70 truncate max-w-full block">
                                        {tr("PDF Document · Evidence Attached")}
                                      </span>
                                    </div>
                                  </div>
                                )
                              )}
                            </div>
                          )}

                          {msg.content && (
                            <div
                              className="font-ui text-sm prose-scalable leading-relaxed break-words text-pretty min-w-0"
                              style={{
                                color: isGoldUserBubble
                                  ? "var(--accent-primary-fg)"
                                  : "var(--text-primary)",
                              }}
                            >
                              {msg.content}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  }

                  return (
                    <article key={msg.id} className="group space-y-3">
                      <div className="flex items-center gap-2 text-xs">
                        <SanadAvatar
                          size={26}
                          glow={false}
                          interactive={isLastAssistant}
                          mode={
                            msg.isStreaming
                              ? "thinking"
                              : isLastAssistant
                              ? getAvatarMode(false, inputText)
                              : "idle"
                          }
                          typingProgress={Math.min(inputText.length / 80, 1)}
                        />
                        <span
                          className="font-editorial font-medium text-sm"
                          style={{ color: "var(--text-heading)" }}
                        >
                          {tr("Sanad")}
                        </span>
                      </div>

                      {/* Multi-step Agent Execution Trace */}
                      {msg.steps && msg.steps.length > 0 && (
                        <AgentTrace
                          steps={msg.steps}
                          isStreaming={msg.isStreaming}
                        />
                      )}

                      {/* Main Markdown Prose */}
                      {msg.content ? (
                        <MarkdownRenderer content={msg.content} />
                      ) : msg.isStreaming &&
                        (!msg.steps || msg.steps.length === 0) ? (
                        <div
                          className="text-xs italic font-editorial py-1"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {tr("Preparing response...")}
                        </div>
                      ) : null}

                      {/* Inline Artifact Cards */}
                      {msg.artifacts && msg.artifacts.length > 0 && (
                        <div className="space-y-2 pt-1">
                          {msg.artifacts.map((art) => {
                            const isSelected =
                              rightPanel === "artifact" &&
                              selectedArtifact?.id === art.id;
                            return (
                              <button
                                key={art.id}
                                type="button"
                                onClick={() => handleOpenArtifact(art)}
                                className="w-full sm:max-w-md flex items-center justify-between gap-3 p-3.5 rounded-xl border text-left transition-colors hover:opacity-90 cursor-pointer"
                                style={{
                                  backgroundColor: isSelected
                                    ? "var(--bg-card)"
                                    : "var(--bg-surface)",
                                  borderColor: isSelected
                                    ? "var(--ring-active)"
                                    : "var(--border-strong)",
                                }}
                              >
                                <div className="flex items-center gap-3 min-w-0">
                                  <div
                                    className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                                    style={{
                                      backgroundColor: "var(--bg-muted)",
                                      color:
                                        art.kind === ArtifactKind.Document
                                          ? "var(--accent-warm)"
                                          : "var(--accent-primary)",
                                    }}
                                  >
                                    {art.kind === ArtifactKind.Document ? (
                                      <FileText className="w-4 h-4" />
                                    ) : (
                                      <FileCode2 className="w-4 h-4" />
                                    )}
                                  </div>
                                  <div className="min-w-0">
                                    <div
                                      className="font-editorial text-sm font-medium truncate"
                                      style={{ color: "var(--text-heading)" }}
                                    >
                                      {art.title}
                                    </div>
                                    <div
                                      className="text-[11px] font-code"
                                      style={{ color: "var(--text-muted)" }}
                                    >
                                      {art.kind === ArtifactKind.Document
                                        ? art.documentMeta?.snippets &&
                                          art.documentMeta.snippets.length > 1
                                          ? tr("PDF Evidence · {0} passages (pp. {1}) · Click to inspect", [art.documentMeta.snippets.length, [
                                              ...new Set(
                                                art.documentMeta.snippets.map(
                                                  (s) => s.page
                                                )
                                              ),
                                            ].join(", ")])
                                          : tr("PDF Evidence · Page {0} · Click to inspect excerpt", [art.documentMeta?.page || "1"])
                                        : tr("{0} · {1} lines · Click to inspect", [art.language, art.content.split("\n").length])}
                                    </div>
                                  </div>
                                </div>

                                <ArrowRight
                                  className="w-4 h-4 shrink-0"
                                  style={{ color: "var(--accent-primary)" }}
                                />
                              </button>
                            );
                          })}
                        </div>
                      )}

                      {/* Grounding Citations (Clean unboxed typography) */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div
                          className="pt-2 border-t text-xs space-y-1.5"
                          style={{ borderColor: "var(--border-subtle)" }}
                        >
                          <div
                            className="font-medium"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {tr(IS_ANDROID ? "Sources" : "Verified web sources")}
                          </div>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                            {msg.sources.map((src, sIdx) => (
                              <a
                                key={`${src.uri}-${sIdx}`}
                                href={src.uri}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 hover:underline underline-offset-3"
                                style={{ color: "var(--accent-primary)" }}
                              >
                                <span className="truncate max-w-[220px]">
                                  {src.title}
                                </span>
                                <span
                                  aria-hidden="true"
                                  style={{ color: "var(--text-muted)" }}
                                >
                                  ·
                                </span>
                                <span
                                  className="font-code text-[11px]"
                                  style={{ color: "var(--text-muted)" }}
                                >
                                  {getHostname(src.uri)}
                                </span>
                                <ExternalLink className="w-3 h-3 opacity-70 shrink-0" />
                              </a>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Error Display */}
                      {msg.error && (
                        <div
                          className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                          style={{
                            backgroundColor: "var(--bg-surface)",
                            borderColor: "#DC2626",
                            color: "var(--text-primary)",
                          }}
                        >
                          <AlertCircle className="w-4 h-4 text-[#DC2626] shrink-0 mt-0.5" />
                          <span>{msg.error}</span>
                        </div>
                      )}

                      {/* Message Action Controls */}
                      {!msg.isStreaming && (msg.content || msg.error) && (
                        <div className="flex items-center gap-3 pt-1 opacity-75 group-hover:opacity-100 transition-opacity">
                          {msg.content && (
                            <button
                              type="button"
                              onClick={() => handleCopyMessage(msg)}
                              className="inline-flex items-center gap-1 text-xs hover:opacity-80 cursor-pointer whitespace-nowrap"
                              style={{ color: "var(--text-muted)" }}
                            >
                              {copiedMessageId === msg.id ? (
                                <>
                                  <Check className="w-3.5 h-3.5" />
                                  <span>{tr("Copied")}</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="w-3.5 h-3.5" />
                                  <span>{tr("Copy")}</span>
                                </>
                              )}
                            </button>
                          )}

                          {isLastAssistant && (
                            <button
                              type="button"
                              onClick={handleRetryLastTurn}
                              className="inline-flex items-center gap-1 text-xs hover:opacity-80 cursor-pointer whitespace-nowrap"
                              style={{ color: "var(--text-muted)" }}
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                              <span>{tr("Retry")}</span>
                            </button>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Bottom Floating Follow-Up Composer */}
            <div className="px-4 sm:px-6 pb-4 pt-2 shrink-0">
              <div className="max-w-3xl mx-auto">
                <Composer
                  value={inputText}
                  onChange={setInputText}
                  onSend={() => handleSendMessage()}
                  onStop={handleStopStreaming}
                  isStreaming={isStreaming}
                  attachments={attachments}
                  onAddAttachments={(items) =>
                    setAttachments((prev) => [...prev, ...items])
                  }
                  onRemoveAttachment={(id) =>
                    setAttachments((prev) => prev.filter((a) => a.id !== id))
                  }
                  thinkingMode={settings.thinkingMode}
                  onToggleThinking={() =>
                    updateSettings({ thinkingMode: !settings.thinkingMode })
                  }
                  thinkingBudget={settings.thinkingBudget}
                  onChangeThinkingBudget={(budget) =>
                    updateSettings({ thinkingBudget: budget })
                  }
                  enableWebSearch={settings.enableWebSearch}
                  onToggleWebSearch={() =>
                    updateSettings({
                      enableWebSearch: !settings.enableWebSearch,
                    })
                  }
                  autoPseudonymise={settings.autoPseudonymise}
                  onOpenPseudonymiser={() => setRightPanel("pseudonymiser")}
                  onOpenVault={() => setVaultModalOpen(true)}
                  onOpenSendPreview={() => setSendPreviewOpen(true)}
                newTopic={newTopic}
                onToggleNewTopic={() => setNewTopic((v) => !v)}
                  placeholder={tr("Reply to Sanad or ask to refine an artifact...")}
                />
              </div>
            </div>
          </>
        )}
      </main>

      {/* Right Split-Pane: Artifact Workbench */}
      {panelP.shown === "artifact" && selectedArtifact && (
        <div className={`fixed inset-0 z-40 lg:static lg:z-auto lg:contents ${panelP.closing ? "anim-out-right" : "anim-in-right"}`}>
          <ArtifactWorkbench
            artifact={selectedArtifact}
            allArtifacts={
              activeThreadArtifacts.length > 0
                ? activeThreadArtifacts
                : [selectedArtifact]
            }
            onSelectArtifact={setSelectedArtifact}
            onClose={() => setRightPanel("none")}
            isExpanded={workbenchExpanded}
            onToggleExpand={() => setWorkbenchExpanded((v) => !v)}
          />
        </div>
      )}

      {/* Right Split-Pane: Appearance & Tweaks Drawer */}
      {panelP.shown === "appearance" && (
        <div className={`fixed inset-0 sm:left-auto z-40 lg:static lg:z-auto h-full ${panelP.closing ? "anim-out-right" : "anim-in-right"}`}>
          <AppearanceDrawer
            settings={settings}
            onChange={updateSettings}
            onReset={resetAppearance}
            onClose={() => setRightPanel("none")}
          />
        </div>
      )}

      {/* Right Split-Pane: Pseudonymiser & Privacy Shield Drawer */}
      {panelP.shown === "pseudonymiser" && (
        <div className={`fixed inset-0 z-40 lg:static lg:inset-auto lg:z-auto h-full ${panelP.closing ? "anim-out-right" : "anim-in-right"}`}>
          <PseudonymiserPanel
            mappings={pseudonymMappings}
            onUpdateMappings={setPseudonymMappings}
            settings={settings}
            onUpdateSettings={updateSettings}
            currentPromptText={inputText}
            onClose={() => setRightPanel("none")}
          />
        </div>
      )}

      {/* Project Knowledge Modal */}
      {knowledgeModalOpen && (
        <ProjectKnowledgeModal
          systemInstruction={settings.systemInstruction}
          onChangeSystemInstruction={(val) =>
            updateSettings({ systemInstruction: val })
          }
          docs={projectDocs}
          onAddDoc={(doc) => setProjectDocs((prev) => [doc, ...prev])}
          onRemoveDoc={(id) =>
            setProjectDocs((prev) => prev.filter((d) => d.id !== id))
          }
          onClose={() => setKnowledgeModalOpen(false)}
        />
      )}

      {/* Encrypted Vault Modal (Client-side AES-GCM 256) */}
      <EncryptedVaultModal
        isOpen={vaultModalOpen}
        onClose={() => setVaultModalOpen(false)}
        vaultItems={vaultItems}
        onUpdateVaultItems={setVaultItems}
        onAttachVaultItemToPrompt={(att) => {
          setAttachments((prev) => [...prev, att]);
          setVaultModalOpen(false);
        }}
      />

      {/* Send Preview & Privacy Inspection Modal */}
      <SendPreviewModal
        isOpen={sendPreviewOpen}
        onClose={() => setSendPreviewOpen(false)}
        onConfirmSend={(finalText) => {
          handleSendMessage(finalText, true);
        }}
        onAddMappings={(rules) =>
          setPseudonymMappings((prev) => [
            ...rules.filter((r) => !prev.some((p) => p.original.trim().toLowerCase() === r.original.trim().toLowerCase())),
            ...prev,
          ])
        }
        rawText={inputText}
        attachments={attachments}
        mappings={pseudonymMappings}
        autoPseudonymise={false}
        onToggleAutoPseudonymise={(val) =>
          updateSettings({ autoPseudonymise: val })
        }
        alwaysPreview={settings.alwaysPreviewBeforeSend}
        onToggleAlwaysPreview={(val) =>
          updateSettings({ alwaysPreviewBeforeSend: val })
        }
        onOpenPseudonymiser={() => {
          setSendPreviewOpen(false);
          setRightPanel("pseudonymiser");
        }}
        modelName="gemini-3.8-flash"
        thinkingBudget={settings.thinkingBudget || 8000}
      />

      {/* Moroccan Legal RAG Blueprint Modals */}

      {/* 1. Operating Mode Switcher & Benchmark */}
      <OperatingModeModal
        isOpen={operatingModeModalOpen}
        onClose={() => setOperatingModeModalOpen(false)}
        currentMode={settings.operatingMode || "hybrid"}
        onSelectMode={(mode: OperatingMode) => updateSettings({ operatingMode: mode })}
      />

      <BoUpdateModal isOpen={boUpdateModalOpen} onClose={() => setBoUpdateModalOpen(false)} />
      <ApiKeysModal isOpen={apiKeysModalOpen} onClose={() => setApiKeysModalOpen(false)} />

      {/* 2. Pure-Function Certified Legal Calculators (Rule 4) */}
      <LegalCalculatorsModal
        isOpen={calculatorsModalOpen}
        onClose={() => setCalculatorsModalOpen(false)}
        currentAsOfDate={settings.asOfDate || new Date().toISOString().slice(0, 10)}
        onAttachCalculationToPrompt={(txt: string) => {
          setInputText((prev) => (prev ? `${prev}\n\n${txt}` : txt));
        }}
      />

      {/* 3. Citizen Situation Navigator & Practical Guides */}
      <SituationNavigatorModal
        isOpen={situationsModalOpen}
        asOfDate={settings.asOfDate}
        onClose={() => setSituationsModalOpen(false)}
        onSelectPrompt={(p) => setInputText(p)}
        onOpenConsultationPrep={(sit) => {
          setSelectedSituationForPrep(sit);
          setConsultationPrepModalOpen(true);
        }}
      />

      {/* 4. Concordance & Transitional Rules Wizard (Law 58.25 vs CPC 1974) */}
      <ConcordanceWizardModal
        isOpen={concordanceModalOpen}
        onClose={() => setConcordanceModalOpen(false)}
        onApplyDate={(d) => updateSettings({ asOfDate: d })}
      />

      {/* 5. Instant Statute & Article Browser (Dual Arabic/French BO) */}
      <StatuteBrowserModal
        isOpen={statutesModalOpen}
        asOfDate={settings.asOfDate}
        onClose={() => setStatutesModalOpen(false)}
        onInsertToPrompt={(t) => {
          setInputText((prev) => (prev ? `${prev}\n\n${t}` : t));
        }}
      />

      {/* 6. Local Audit & NLI Contradiction Trace (Zero Telemetry) */}
      <AuditTraceModal
        isOpen={auditTraceModalOpen}
        onClose={() => setAuditTraceModalOpen(false)}
        auditLogs={auditLogs}
        onWipeAuditLogs={() => {
          clearHistory().catch(() => {});
          setAuditLogs([]);
          try {
            localStorage.removeItem(STORAGE_KEYS.auditLogs);
          } catch {
            // Ignore
          }
        }}
      />

      {/* 7. Report Divergence & Cite BO Source Form */}
      <ReportErrorModal
        isOpen={reportErrorModalOpen}
        onClose={() => setReportErrorModalOpen(false)}
        onSubmitReport={(rep) => {
          // local draft on the backend (pseudonymised; the user submits it from there)
          createErrorReport({
            trace_id: lastTraceIdRef.current,
            what_is_wrong: `[${rep.errorType}] ${rep.articleRef} (${rep.boNumber}): ${rep.details}\nCorrection proposée : ${rep.suggestedFix}`,
            correct_source: rep.boNumber,
          }).catch(() => {});
          const newTrace: AuditTraceRecord = {
            id: `report-${Date.now()}`,
            timestamp: new Date().toISOString().replace("T", " ").slice(0, 19),
            rawQuestionLength: rep.details.length,
            pseudonymisedQuery: `[Signalement BO] Article ${rep.articleRef} (${rep.boNumber}) : ${rep.errorType}`,
            asOfDate: settings.asOfDate || new Date().toISOString().slice(0, 10),
            operatingMode: settings.operatingMode || "hybrid",
            retrievedChunkIds: [rep.articleRef],
            verification: {
              citationExists: true,
              quoteMatches: true,
              placeholdersIntact: true,
              versionValid: true,
              noStrayNumbers: true,
              claimSupportRate: 100,
              overallStatus: "passed",
            },
            outboundPayloadJson: JSON.stringify(rep, null, 2),
            claimsCount: 1,
            latencyMs: 120,
          };
          setAuditLogs((prev) => [newTrace, ...prev]);
        }}
      />

      {docReview && <DocumentReviewModal docs={docReview.docs} onResolve={docReview.resolve} />}

      {/* 8. Printable 1-Page Consultation-Prep Dossier for Attorneys */}
      <ConsultationPrepModal
        isOpen={consultationPrepModalOpen}
        onClose={() => setConsultationPrepModalOpen(false)}
        situation={selectedSituationForPrep}
        asOfDate={settings.asOfDate || new Date().toISOString().slice(0, 10)}
      />
    </div>
  );
}

export default App;
