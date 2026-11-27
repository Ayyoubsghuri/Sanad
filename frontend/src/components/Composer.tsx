import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { tr } from "../i18n";
import { useI18n } from "../i18n";
import { createPortal } from "react-dom";
import {
  ArrowUp,
  Brain,
  MessageSquarePlus,
  Check,
  ChevronDown,
  FileText,
  Lock,
  Plus,
  ShieldCheck,
  Sparkles,
  Square,
  UserCheck,
  X,
} from "lucide-react";
import { AttachmentItem } from "../types/agent";

interface ComposerProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  attachments: AttachmentItem[];
  onAddAttachments: (items: AttachmentItem[]) => void;
  allowAttachments?: boolean;   // false on a public server: files are not sent to it
  onRemoveAttachment: (id: string) => void;
  thinkingMode: boolean;
  onToggleThinking: () => void;
  thinkingBudget?: number;
  onChangeThinkingBudget?: (budget: number) => void;
  autoPseudonymise?: boolean;
  onOpenPseudonymiser?: () => void;
  onOpenVault?: () => void;
  onOpenSendPreview?: () => void;
  newTopic?: boolean;
  onToggleNewTopic?: () => void;
  placeholder?: string;
}

const PRESET_BUDGETS = [
  { label: "2K", desc: "Quick", value: 2048 },
  { label: "8K", desc: "Balanced", value: 8000 },
  { label: "16K", desc: "Deep", value: 16000 },
  { label: "32K", desc: "Maximum", value: 32768 },
];

function formatTokens(val: number): string {
  if (val >= 1000) {
    const k = Math.round(val / 1000);
    return `${k}K`;
  }
  return String(val);
}

export const Composer: React.FC<ComposerProps> = ({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming,
  attachments,
  onAddAttachments,
  allowAttachments = true,
  onRemoveAttachment,
  thinkingMode,
  onToggleThinking,
  thinkingBudget = 8000,
  onChangeThinkingBudget,
  autoPseudonymise = true,
  onOpenPseudonymiser,
  onOpenVault,
  onOpenSendPreview,
  newTopic = false,
  onToggleNewTopic,
  placeholder,
}) => {
  const { t } = useI18n();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const toolbarScrollRef = useRef<HTMLDivElement | null>(null);
  const thinkingButtonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [isThinkingMenuOpen, setIsThinkingMenuOpen] = useState(false);
  const [popoverPos, setPopoverPos] = useState({ bottom: 80, left: 20, width: 316, originX: 40 });

  const updatePopoverPos = useCallback(() => {
    if (!thinkingButtonRef.current) return;
    const rect = thinkingButtonRef.current.getBoundingClientRect();
    const width = Math.min(316, window.innerWidth - 24);
    const bottom = window.innerHeight - rect.top + 8;
    const idealLeft = rect.left - 4;
    const maxLeft = window.innerWidth - width - 12;
    const left = Math.max(12, Math.min(idealLeft, maxLeft));
    // transform-origin = the button's centre, so the liquid grows out of the button itself
    const originX = Math.max(16, Math.min(width - 16, rect.left + rect.width / 2 - left));
    setPopoverPos({ bottom, left, width, originX });
  }, []);

  // useLayoutEffect: position is measured BEFORE first paint, so the popover never flashes at the default spot and slides over.
  useLayoutEffect(() => {
    if (isThinkingMenuOpen) {
      updatePopoverPos();
      window.addEventListener("resize", updatePopoverPos);
      window.addEventListener("scroll", updatePopoverPos, true);
      return () => {
        window.removeEventListener("resize", updatePopoverPos);
        window.removeEventListener("scroll", updatePopoverPos, true);
      };
    }
  }, [isThinkingMenuOpen, updatePopoverPos]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (
        popoverRef.current &&
        !popoverRef.current.contains(target) &&
        thinkingButtonRef.current &&
        !thinkingButtonRef.current.contains(target)
      ) {
        setIsThinkingMenuOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setIsThinkingMenuOpen(false);
      }
    }
    if (isThinkingMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [isThinkingMenuOpen]);

  // Toolbar horizontal scroll wheel support
  useEffect(() => {
    const el = toolbarScrollRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent) => {
      if (el.scrollWidth > el.clientWidth) {
        if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
          el.scrollLeft += e.deltaY;
          e.preventDefault();
        } else {
          el.scrollLeft += e.deltaX;
        }
      }
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, []);

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    const processed: AttachmentItem[] = [];

    for (const file of Array.from(fileList)) {
      const id = `att-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      if (file.type.startsWith("image/")) {
        const dataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.readAsDataURL(file);
        });
        processed.push({
          id,
          name: file.name,
          mimeType: file.type,
          sizeBytes: file.size,
          dataUrl,
        });
      } else {
        const textContent = await file.text();
        processed.push({
          id,
          name: file.name,
          mimeType: file.type || "text/plain",
          sizeBytes: file.size,
          textContent: textContent.slice(0, 60000),
        });
      }
    }

    if (processed.length > 0) {
      onAddAttachments(processed);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && (value.trim().length > 0 || attachments.length > 0)) {
        onSend();
      }
    }
  };

  const adjustHeight = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  };

  // the box follows its text: after a long message is sent (value cleared), it goes back to one line
  useLayoutEffect(() => {
    if (textareaRef.current) adjustHeight(textareaRef.current);
  }, [value]);

  const canSend = value.trim().length > 0 || attachments.length > 0;

  return (
    <div
      className="w-full rounded-2xl sm:rounded-3xl border transition-all duration-150 shadow-xs focus-within:shadow-md"
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-strong)",
      }}
    >
      {/* Attached Files Carousel */}
      {attachments.length > 0 && (
        <div className="flex items-center gap-2 px-4 pt-3.5 pb-1 overflow-x-auto">
          {attachments.map((att) => (
            <div
              key={att.id}
              className="group relative flex items-center gap-2 pl-2 pr-7 py-1.5 rounded-xl border text-xs shrink-0 max-w-[200px]"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
              }}
            >
              {att.dataUrl ? (
                <img
                  src={att.dataUrl}
                  alt={att.name}
                  referrerPolicy="no-referrer"
                  className="w-6 h-6 rounded-md object-cover shrink-0"
                />
              ) : (
                <FileText
                  className="w-4 h-4 shrink-0"
                  style={{ color: "var(--accent-primary)" }}
                />
              )}
              <span
                className="truncate font-medium text-[12px]"
                style={{ color: "var(--text-primary)" }}
              >
                {att.name}
              </span>
              <button
                type="button"
                onClick={() => onRemoveAttachment(att.id)}
                aria-label={tr("Remove {0}", [att.name])}
                className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded-md opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
                style={{ color: "var(--text-muted)" }}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Main Textarea */}
      <div className="px-3.5 pt-2.5 pb-0.5 sm:px-4.5 sm:pt-3.5 sm:pb-2">
        <textarea
          ref={textareaRef}
          rows={typeof window !== "undefined" && window.innerWidth < 640 ? 1 : 2}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            adjustHeight(e.target);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? t("composer.placeholder")}
          className="w-full resize-none bg-transparent border-0 outline-none text-[15px] sm:text-[15.5px] leading-relaxed placeholder:opacity-45"
          style={{
            color: "var(--text-primary)",
          }}
        />
      </div>

      {/* Single-Row Clean Claude-Style Bottom Bar */}
      <div className="flex items-center justify-between px-2 pb-2 pt-0.5 sm:px-3 sm:pb-3 sm:pt-1 gap-1.5 sm:gap-2 relative min-w-0">
        {/* Left Cluster: Attach + Mode Toggles (Horizontally scrollable with wheel/touch/drag) */}
        <div
          ref={toolbarScrollRef}
          className="flex items-center gap-1.5 min-w-0 flex-1 overflow-x-auto scrollbar-none py-1 px-0.5 select-none scroll-smooth"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,.txt,.md,.csv,.json,.ts,.tsx,.js,.py,.html"
            onChange={(e) => handleFiles(e.target.files)}
            className="hidden"
          />

          {/* Claude-style Plus Attach Button */}
          {allowAttachments && <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title={t("composer.attach")}
            className="inline-flex items-center justify-center w-8 h-8 rounded-full border transition-colors hover:opacity-85 cursor-pointer shrink-0"
            style={{
              backgroundColor: "var(--bg-canvas)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-muted)",
            }}
          >
            <Plus className="w-4 h-4" />
          </button>}

          {/* Extended Thinking Button */}
          <button
            ref={thinkingButtonRef}
            type="button"
            onClick={() => setIsThinkingMenuOpen((prev) => !prev)}
            title={
              thinkingMode
                ? tr("Extended thinking active ({0} tokens) - Click to configure", [formatTokens(
                    thinkingBudget || 8000
                  )])
                : tr("Enable extended thinking")
            }
            aria-expanded={isThinkingMenuOpen}
            className="inline-flex items-center gap-1.5 h-8 px-2 sm:px-2.5 rounded-full text-xs font-medium transition-all duration-150 cursor-pointer whitespace-nowrap shrink-0 border"
            style={{
              backgroundColor: thinkingMode
                ? "var(--bg-card)"
                : "transparent",
              borderColor: thinkingMode
                ? "var(--border-strong)"
                : "var(--border-subtle)",
              color: thinkingMode
                ? "var(--text-heading)"
                : "var(--text-muted)",
            }}
          >
            <Brain
              className={`w-3.5 h-3.5 transition-colors ${
                thinkingMode ? "opacity-100" : "opacity-60"
              }`}
              style={{
                color: thinkingMode
                  ? "var(--accent-warm)"
                  : "var(--text-muted)",
              }}
            />
            <span className="hidden md:inline">{t("composer.thinking")}</span>
            {thinkingMode && (
              <span
                className="font-code text-[10px] font-semibold px-1.5 py-0.5 rounded-full tracking-tight shrink-0"
                style={{
                  backgroundColor: "var(--bg-muted)",
                  color: "var(--accent-primary)",
                }}
              >
                {formatTokens(thinkingBudget || 8000)}
              </span>
            )}
            <ChevronDown
              className={`w-3.5 h-3.5 transition-transform duration-200 shrink-0 ${
                isThinkingMenuOpen ? "rotate-180" : ""
              } ${thinkingMode ? "opacity-80" : "opacity-50"}`}
            />
          </button>

          {/* New topic: the next question is answered on its own, without the earlier turns of this chat */}
          {onToggleNewTopic && (
            <button
              type="button"
              onClick={onToggleNewTopic}
              title={newTopic ? tr("New topic: the next question ignores this chat (click to cancel)") : tr("New topic: answer the next question on its own")}
              className="inline-flex items-center justify-center gap-1.5 h-8 w-8 sm:w-auto sm:px-2.5 rounded-full border transition-all duration-150 cursor-pointer shrink-0 text-xs font-medium"
              style={{
                backgroundColor: newTopic ? "var(--bg-card)" : "var(--bg-canvas)",
                borderColor: newTopic ? "var(--border-strong)" : "var(--border-subtle)",
                color: newTopic ? "var(--accent-warm)" : "var(--text-muted)",
              }}
            >
              <MessageSquarePlus className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{tr("New topic")}</span>
            </button>
          )}

          {/* Clean Circular Pseudonymiser Toggle */}
          {onOpenPseudonymiser && (
            <button
              type="button"
              onClick={onOpenPseudonymiser}
              title={
                autoPseudonymise
                  ? tr("Pseudonymiser active: PII will be masked (Click to inspect rules)")
                  : tr("Pseudonymiser inactive (Click to configure)")
              }
              className="inline-flex items-center justify-center w-8 h-8 rounded-full border transition-all duration-150 cursor-pointer shrink-0 relative"
              style={{
                backgroundColor: autoPseudonymise
                  ? "var(--bg-card)"
                  : "var(--bg-canvas)",
                borderColor: autoPseudonymise
                  ? "var(--border-strong)"
                  : "var(--border-subtle)",
                color: autoPseudonymise
                  ? "var(--accent-warm)"
                  : "var(--text-muted)",
              }}
            >
              <UserCheck className="w-3.5 h-3.5" />
              {autoPseudonymise && (
                <span
                  className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full"
                  style={{
                    backgroundColor: "var(--accent-warm)",
                  }}
                />
              )}
            </button>
          )}

          {/* Encrypted Vault Access Button */}
          {onOpenVault && (
            <button
              type="button"
              onClick={onOpenVault}
              title={t("composer.vault")}
              className="inline-flex items-center justify-center w-8 h-8 rounded-full border transition-colors hover:opacity-85 cursor-pointer shrink-0"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-muted)",
              }}
            >
              <Lock className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Right Action: Send Preview + Clean circular Send / Stop Button */}
        <div className="flex items-center gap-1.5 shrink-0">
          {onOpenSendPreview && !isStreaming && (
            <button
              type="button"
              disabled={!canSend}
              onClick={onOpenSendPreview}
              title={t("composer.preview")}
              className="inline-flex items-center justify-center w-8 h-8 rounded-full border transition-all duration-150 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed hover:opacity-85 shrink-0"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-muted)",
              }}
            >
              <ShieldCheck className="w-4 h-4" />
            </button>
          )}

          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              title={t("composer.stop")}
              className="inline-flex items-center justify-center w-8 h-8 rounded-full transition-transform hover:scale-105 active:scale-95 cursor-pointer shrink-0 shadow-xs"
              style={{
                backgroundColor: "var(--accent-primary)",
                color: "var(--accent-primary-fg)",
              }}
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              disabled={!canSend}
              onClick={onSend}
              title={t("composer.send")}
              className="inline-flex items-center justify-center w-8 h-8 rounded-full transition-all duration-150 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed hover:scale-105 active:scale-95 shrink-0 shadow-xs"
              style={{
                backgroundColor: canSend
                  ? "var(--accent-primary)"
                  : "var(--bg-card)",
                color: canSend
                  ? "var(--accent-primary-fg)"
                  : "var(--text-muted)",
              }}
            >
              <ArrowUp className="w-4 h-4 stroke-[2.2]" />
            </button>
          )}
        </div>
      </div>

      {/* Expandable Thinking Budget & Reasoning Settings Popover rendered via Portal */}
      {isThinkingMenuOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={popoverRef}
            style={{
              position: "fixed",
              bottom: `${popoverPos.bottom}px`,
              left: `${popoverPos.left}px`,
              width: `${popoverPos.width}px`,
              zIndex: 99999,
              backgroundColor: "var(--bg-surface)",
              borderColor: "var(--border-strong)",
              transformOrigin: `${popoverPos.originX}px 100%`,
            }}
            className="sanad-liquid-pop rounded-2xl border p-3.5 shadow-2xl"
          >
            {/* Header with Switch */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                  style={{
                    backgroundColor: "var(--bg-muted)",
                    color: "var(--accent-warm)",
                  }}
                >
                  <Brain className="w-4 h-4" />
                </div>
                <div>
                  <div
                    className="font-semibold text-xs flex items-center gap-1"
                    style={{ color: "var(--text-heading)" }}
                  >
                    {t("think.title")}
                    <Sparkles
                      className="w-3 h-3 shrink-0"
                      style={{ color: "var(--accent-warm)" }}
                    />
                  </div>
                  <div
                    className="text-[10.5px]"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("think.sub")}
                  </div>
                </div>
              </div>

              <button
                type="button"
                role="switch"
                aria-checked={thinkingMode}
                onClick={() => onToggleThinking()}
                className="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
                style={{
                  backgroundColor: thinkingMode
                    ? "var(--accent-primary)"
                    : "var(--border-strong)",
                }}
              >
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                    thinkingMode ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            <p
              className="text-[11px] leading-relaxed mt-2"
              style={{ color: "var(--text-muted)" }}
            >
              {t("think.desc")}
            </p>

            {thinkingMode ? (
              <div
                className="border-t pt-2.5 mt-2.5 space-y-2.5"
                style={{ borderColor: "var(--border-subtle)" }}
              >
                <div className="flex items-center justify-between">
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("think.budget")}
                  </span>
                  <span
                    className="font-code text-xs font-semibold px-2 py-0.5 rounded"
                    style={{
                      backgroundColor: "var(--bg-muted)",
                      color: "var(--accent-primary)",
                    }}
                  >
                    {(thinkingBudget || 8000).toLocaleString()} {tr("tokens")}
                  </span>
                </div>

                <input
                  type="range"
                  min={1024}
                  max={32768}
                  step={1024}
                  value={thinkingBudget || 8000}
                  onChange={(e) =>
                    onChangeThinkingBudget?.(Number(e.target.value))
                  }
                  className="w-full h-1.5 rounded-lg appearance-none cursor-pointer"
                  style={{
                    accentColor: "var(--accent-primary)",
                  }}
                />

                {/* Presets Grid */}
                <div className="grid grid-cols-4 gap-1 pt-0.5">
                  {PRESET_BUDGETS.map((preset) => {
                    const isSelected =
                      (thinkingBudget || 8000) === preset.value;
                    return (
                      <button
                        key={preset.value}
                        type="button"
                        onClick={() =>
                          onChangeThinkingBudget?.(preset.value)
                        }
                        className="flex flex-col items-center py-1.5 px-0.5 rounded-lg border text-center transition-all cursor-pointer"
                        style={{
                          backgroundColor: isSelected
                            ? "var(--bg-card)"
                            : "var(--bg-canvas)",
                          borderColor: isSelected
                            ? "var(--accent-primary)"
                            : "var(--border-subtle)",
                          color: isSelected
                            ? "var(--accent-primary)"
                            : "var(--text-primary)",
                        }}
                      >
                        <span className="font-code font-bold text-xs flex items-center justify-center gap-0.5">
                          {preset.label}
                          {isSelected && (
                            <Check className="w-2.5 h-2.5 ml-0.5 stroke-[2.5]" />
                          )}
                        </span>
                        <span
                          className="text-[9.5px] opacity-75"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {preset.desc}
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div
                  className="flex items-center justify-between text-[11px] pt-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  <span>{tr("Deep and Maximum also search the law again when the first results are not enough")}</span>
                  <button
                    type="button"
                    onClick={() => setIsThinkingMenuOpen(false)}
                    className="font-medium hover:underline cursor-pointer"
                    style={{ color: "var(--accent-primary)" }}
                  >
                    {t("think.done")}
                  </button>
                </div>
              </div>
            ) : (
              <div
                className="border-t pt-3 mt-3 flex items-center justify-between text-[11px]"
                style={{
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-muted)",
                }}
              >
                <span>{t("think.turnOnHint")}</span>
                <button
                  type="button"
                  onClick={() => {
                    onToggleThinking();
                  }}
                  className="font-medium underline cursor-pointer"
                  style={{ color: "var(--accent-primary)" }}
                >
                  {t("think.turnOn")}
                </button>
              </div>
            )}
          </div>,
          document.body
        )}
    </div>
  );
};
