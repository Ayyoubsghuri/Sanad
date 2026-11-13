import { entriesToMappings, kindToCategory, rulesToTerms, useServerMasking } from "../api/useServerMasking";
import { tr } from "../i18n";
import { deleteCase, getVaultReveal, previewPseudonymise } from "../api/legalrag";
import React, { useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Eye,
  EyeOff,
  Filter,
  KeyRound,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Undo2,
  UserCheck,
  X,
} from "lucide-react";
import { PseudonymMapping, WorkspaceSettings } from "../types/agent";
import {
  applyPseudonyms,
  DEFAULT_INITIAL_MAPPINGS,
  restoreRealEntities,
  scanAndDetectEntities,
} from "../utils/pseudonymiser";

interface PseudonymiserPanelProps {
  mappings: PseudonymMapping[];
  onUpdateMappings: (mappings: PseudonymMapping[]) => void;
  settings: WorkspaceSettings;
  onUpdateSettings: (patch: Partial<WorkspaceSettings>) => void;
  currentPromptText?: string;
  onClose: () => void;
}

export const PseudonymiserPanel: React.FC<PseudonymiserPanelProps> = ({
  mappings,
  onUpdateMappings,
  settings,
  onUpdateSettings,
  currentPromptText = "",
  onClose,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<
    "all" | PseudonymMapping["category"]
  >("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sandboxInput, setSandboxInput] = useState(
    currentPromptText ||
      "Confidential briefing for Dr. Sarah Jenkins regarding Acme Corporation and Helios Bio-Analytics AG acquisition for $48,000,000. Send questions to sarah.jenkins@acme-research.org."
  );

  // New rule form states
  const [showAddForm, setShowAddForm] = useState(false);
  const [newOriginal, setNewOriginal] = useState("");
  const [newReplacement, setNewReplacement] = useState("");
  const [newCategory, setNewCategory] =
    useState<PseudonymMapping["category"]>("person");

  const filteredMappings = useMemo(() => {
    return mappings.filter((m) => {
      if (selectedCategory !== "all" && m.category !== selectedCategory) {
        return false;
      }
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        m.original.toLowerCase().includes(q) ||
        m.replacement.toLowerCase().includes(q)
      );
    });
  }, [mappings, selectedCategory, searchQuery]);

  // Live Sandbox computation
  // Same engine as the send preview and the real send: the local backend (rules + Arabic NER + your saved rules).
  const server = useServerMasking(sandboxInput, rulesToTerms(mappings), true);
  const localSandbox = useMemo(() => applyPseudonyms(sandboxInput, mappings), [sandboxInput, mappings]);
  const sandboxResult =
    server.masked !== null
      ? { text: server.masked, replacedCount: server.entries.length }
      : { text: localSandbox.text, replacedCount: localSandbox.replacedCount };

  const handleToggleRule = (id: string) => {
    onUpdateMappings(
      mappings.map((m) => (m.id === id ? { ...m, active: !m.active } : m))
    );
  };

  const handleDeleteRule = (id: string) => {
    onUpdateMappings(mappings.filter((m) => m.id !== id));
  };

  const handleAddRule = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newOriginal.trim() || !newReplacement.trim()) return;

    const newRule: PseudonymMapping = {
      id: `map-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      original: newOriginal.trim(),
      replacement: newReplacement.trim().toUpperCase().startsWith("[")
        ? newReplacement.trim().toUpperCase()
        : `[${newReplacement.trim().toUpperCase()}]`,
      category: newCategory,
      detectedAt: tr("Manual Rule"),
      active: true,
    };

    onUpdateMappings([newRule, ...mappings]);
    setNewOriginal("");
    setNewReplacement("");
    setShowAddForm(false);
  };

  const [scanning, setScanning] = useState(false);
  const handleScanPromptForEntities = async () => {
    // Backend detections (names, addresses, IDs, phones...) become saved rules, with the SAME placeholders the preview shows.
    const textToScan = currentPromptText || sandboxInput;
    if (!textToScan.trim()) return;
    setScanning(true);
    try {
      const p = await previewPseudonymise(textToScan, rulesToTerms(mappings));
      const v = await getVaultReveal(p.case_id);
      deleteCase(p.case_id).catch(() => {});
      const fresh = entriesToMappings(
        v.entries.map((e) => ({ ...e, category: kindToCategory(e.kind) })),
        mappings
      );
      if (fresh.length > 0) onUpdateMappings([...fresh, ...mappings]);
    } catch {
      // backend unreachable: fall back to the local heuristic scanner
      const detected = scanAndDetectEntities(textToScan, mappings);
      if (detected.length > 0) onUpdateMappings([...detected, ...mappings]);
    } finally {
      setScanning(false);
    }
  };

  const handleResetDefaults = () => {
    onUpdateMappings(DEFAULT_INITIAL_MAPPINGS);
  };

  return (
    <aside
      className="sanad-liquid-side w-full lg:w-[460px] h-full shrink-0 border-l flex flex-col select-none z-30"
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4 border-b shrink-0"
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
            <UserCheck className="w-4 h-4" />
          </div>
          <div>
            <h2
              className="font-editorial text-sm sm:text-base font-semibold leading-tight"
              style={{ color: "var(--text-heading)" }}
            >
              {tr("Pseudonymiser & Privacy Shield")}
            </h2>
            <div
              className="text-[11px] font-code"
              style={{ color: "var(--text-muted)" }}
            >
              {tr("De-identify entities before cloud model processing")}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label={tr("Close pseudonymiser panel")}
          className="p-1.5 rounded-lg opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
          style={{ color: "var(--text-muted)" }}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Main Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Master Toggles Card */}
        <div
          className="p-4 rounded-2xl border space-y-3.5 shadow-xs"
          style={{
            backgroundColor: "var(--bg-canvas)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div
                className="text-xs font-semibold"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Mask uploaded files")}
              </div>
              <div
                className="text-[11px] leading-relaxed"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Files you attach are always masked before anything leaves your device. Your chat messages are sent as you write them.")}
              </div>
            </div>

            <span className="text-[11px] font-semibold" style={{ color: "#10B981" }}>{tr("Files only")}</span>
          </div>

          <div
            className="border-t pt-3 flex items-center justify-between"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <div className="space-y-0.5">
              <div
                className="text-xs font-semibold"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Restore Entities Locally in Replies")}
              </div>
              <div
                className="text-[11px] leading-relaxed"
                style={{ color: "var(--text-muted)" }}
              >
                {tr("Automatically swap [ORG_1] back to real names in assistant chat bubbles")}
              </div>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={settings.restorePseudonymsInReplies}
              onClick={() =>
                onUpdateSettings({
                  restorePseudonymsInReplies:
                    !settings.restorePseudonymsInReplies,
                })
              }
              className="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
              style={{
                backgroundColor: settings.restorePseudonymsInReplies
                  ? "var(--accent-primary)"
                  : "var(--border-strong)",
              }}
            >
              <span
                aria-hidden="true"
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                  settings.restorePseudonymsInReplies
                    ? "translate-x-4"
                    : "translate-x-0"
                }`}
              />
            </button>
          </div>
        </div>

        {/* Live Test Sandbox */}
        <div
          className="p-4 rounded-2xl border space-y-3"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-semibold flex items-center gap-1.5"
              style={{ color: "var(--text-heading)" }}
            >
              <Sparkles className="w-3.5 h-3.5 text-[var(--accent-warm)]" />
              {tr("Live Masking Sandbox")}
            </span>
            <span
              className="font-code text-[11px] px-2 py-0.5 rounded"
              style={{
                backgroundColor: "var(--bg-muted)",
                color: "var(--accent-primary)",
              }}
            >
              {sandboxResult.replacedCount} {tr("masked")}
            </span>
          </div>

          <textarea
            rows={2}
            value={sandboxInput}
            onChange={(e) => setSandboxInput(e.target.value)}
            placeholder={tr("Type text with names, emails, or financials...")}
            className="w-full text-xs font-code p-2.5 rounded-xl border bg-transparent resize-none outline-none"
            style={{
              borderColor: "var(--border-subtle)",
              color: "var(--text-primary)",
            }}
          />

          <div
            className="p-3 rounded-xl border font-code text-xs leading-relaxed whitespace-pre-wrap select-text"
            style={{
              backgroundColor: "var(--bg-surface)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-primary)",
            }}
          >
            {sandboxResult.text}
          </div>
        </div>

        {/* Rules Table & Filter Header */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-semibold"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Mapping Rules (")}{mappings.length})
              </span>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleScanPromptForEntities}
                title={tr("Scan current text for unmapped entities")}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium border hover:opacity-85 cursor-pointer"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              >
                <Search className="w-3 h-3" />
                <span>{scanning ? tr("Scanning…") : "Auto-Scan"}</span>
              </button>

              <button
                type="button"
                onClick={() => setShowAddForm((v) => !v)}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold cursor-pointer shadow-xs hover:opacity-90"
                style={{
                  backgroundColor: "var(--accent-primary)",
                  color: "var(--accent-primary-fg)",
                }}
              >
                <Plus className="w-3 h-3" />
                <span>{tr("Add Rule")}</span>
              </button>
            </div>
          </div>

          {/* Add New Rule Form */}
          {showAddForm && (
            <form
              onSubmit={handleAddRule}
              className="p-3.5 rounded-2xl border space-y-3 animate-in fade-in"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-strong)",
              }}
            >
              <div className="text-xs font-semibold" style={{ color: "var(--text-heading)" }}>
                {tr("Add Entity Replacement")}
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <label className="text-[11px] opacity-75 mb-1 block">
                    {tr("Original Name / Text")}
                  </label>
                  <input
                    type="text"
                    required
                    value={newOriginal}
                    onChange={(e) => setNewOriginal(e.target.value)}
                    placeholder={tr("e.g. John Doe")}
                    className="w-full px-2.5 py-1.5 rounded-lg border bg-transparent text-xs"
                    style={{ borderColor: "var(--border-subtle)" }}
                  />
                </div>
                <div>
                  <label className="text-[11px] opacity-75 mb-1 block">
                    {tr("Replacement Token")}
                  </label>
                  <input
                    type="text"
                    required
                    value={newReplacement}
                    onChange={(e) => setNewReplacement(e.target.value)}
                    placeholder={tr("e.g. PERSON_EXEC_1")}
                    className="w-full px-2.5 py-1.5 rounded-lg border bg-transparent text-xs font-code"
                    style={{ borderColor: "var(--border-subtle)" }}
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-1">
                <select
                  value={newCategory}
                  onChange={(e) =>
                    setNewCategory(
                      e.target.value as PseudonymMapping["category"]
                    )
                  }
                  className="px-2.5 py-1 rounded-lg border bg-transparent text-xs"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <option value="person">{tr("Person")}</option>
                  <option value="org">{tr("Organization")}</option>
                  <option value="contact">{tr("Contact / Email")}</option>
                  <option value="financial">{tr("Financial / IBAN")}</option>
                  <option value="secret">{tr("Secret / Key")}</option>
                  <option value="custom">{tr("Custom")}</option>
                </select>

                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setShowAddForm(false)}
                    className="px-2.5 py-1 rounded-lg text-xs border"
                    style={{ borderColor: "var(--border-subtle)" }}
                  >
                    {tr("Cancel")}
                  </button>
                  <button
                    type="submit"
                    className="px-3 py-1 rounded-lg text-xs font-semibold"
                    style={{
                      backgroundColor: "var(--accent-primary)",
                      color: "var(--accent-primary-fg)",
                    }}
                  >
                    {tr("Save Rule")}
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Category Tabs */}
          <div className="flex items-center gap-1 overflow-x-auto pb-1 text-xs">
            {(
              [
                "all",
                "person",
                "org",
                "contact",
                "financial",
                "secret",
              ] as const
            ).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded-lg capitalize whitespace-nowrap transition-colors cursor-pointer text-[11px] ${
                  selectedCategory === cat
                    ? "font-semibold border"
                    : "opacity-70 hover:opacity-100"
                }`}
                style={{
                  backgroundColor:
                    selectedCategory === cat
                      ? "var(--bg-canvas)"
                      : "transparent",
                  borderColor:
                    selectedCategory === cat
                      ? "var(--border-strong)"
                      : "transparent",
                  color:
                    selectedCategory === cat
                      ? "var(--text-heading)"
                      : "var(--text-muted)",
                }}
              >
                {cat === "all" ? tr("All Rules") : cat}
              </button>
            ))}
          </div>

          {/* Mappings List */}
          <div className="space-y-2">
            {filteredMappings.length === 0 ? (
              <div
                className="p-6 rounded-2xl border text-center text-xs"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-muted)",
                }}
              >
                {tr("No rules found for this category.")}
              </div>
            ) : (
              filteredMappings.map((m) => (
                <div
                  key={m.id}
                  className="p-3 rounded-xl border flex items-center justify-between gap-3 text-xs transition-colors"
                  style={{
                    backgroundColor: m.active
                      ? "var(--bg-surface)"
                      : "var(--bg-canvas)",
                    borderColor: "var(--border-subtle)",
                    opacity: m.active ? 1 : 0.6,
                  }}
                >
                  <div className="min-w-0 flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={m.active}
                      onChange={() => handleToggleRule(m.id)}
                      className="rounded accent-[var(--accent-primary)] cursor-pointer"
                    />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="font-medium truncate max-w-[130px] sm:max-w-[160px]"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {m.original}
                        </span>
                        <ChevronRight className="w-3 h-3 opacity-40 shrink-0" />
                        <span
                          className="font-code font-bold truncate max-w-[130px] sm:max-w-[160px]"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          {m.replacement}
                        </span>
                      </div>
                      <div
                        className="text-[10px] capitalize font-code"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {m.category} · {m.detectedAt || "Active"}
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleDeleteRule(m.id)}
                    aria-label={tr("Delete rule for {0}", [m.original])}
                    className="p-1 rounded-md opacity-50 hover:opacity-100 transition-opacity cursor-pointer shrink-0"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Footer Reset */}
      <div
        className="px-5 py-3 border-t flex items-center justify-between text-xs shrink-0"
        style={{
          backgroundColor: "var(--bg-canvas)",
          borderColor: "var(--border-subtle)",
        }}
      >
        <button
          type="button"
          onClick={handleResetDefaults}
          className="inline-flex items-center gap-1 text-[11px] opacity-75 hover:opacity-100 cursor-pointer"
          style={{ color: "var(--text-muted)" }}
        >
          <RotateCcw className="w-3 h-3" />
          <span>{tr("Reset standard enterprise rules")}</span>
        </button>

        <button
          type="button"
          onClick={onClose}
          className="px-3 py-1 rounded-lg text-xs font-medium border cursor-pointer hover:opacity-90"
          style={{
            backgroundColor: "var(--bg-surface)",
            borderColor: "var(--border-subtle)",
            color: "var(--text-primary)",
          }}
        >
          {tr("Done")}
        </button>
      </div>
    </aside>
  );
};
