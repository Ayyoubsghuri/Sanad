import React, { useEffect, useState } from "react";
import { tr } from "../i18n";
import {
  Brain,
  Calculator,
  Check,
  ChevronDown,
  ChevronRight,
  Compass,
  FileCode2,
  FileText,
  Loader2,
  NotebookPen,
} from "lucide-react";
import { AgentStep, StepStatus } from "../types/agent";

interface AgentTraceProps {
  steps: AgentStep[];
  isStreaming?: boolean;
}

export const AgentTrace: React.FC<AgentTraceProps> = ({
  steps,
  isStreaming,
}) => {
  const working = Boolean(isStreaming) || (steps || []).some((st) => st.status === StepStatus.Running);
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // the trace opens by itself while the agent is working, so its steps can be followed live
  useEffect(() => {
    // open while the agent works, fold back to the one-line summary when it finishes
    setIsOpen(working);
  }, [working]);

  if (!steps || steps.length === 0) return null;

  const runningStep = steps.find((s) => s.status === StepStatus.Running);
  const totalMs = steps.reduce((sum, s) => sum + (s.durationMs || 0), 0);

  const renderStepIcon = (step: AgentStep) => {
    if (step.status === StepStatus.Running) {
      return (
        <Loader2
          className="w-3.5 h-3.5 animate-spin shrink-0"
          style={{ color: "var(--accent-warm)" }}
        />
      );
    }
    switch (step.kind) {
      case "thinking":
        return <Brain className="w-3.5 h-3.5 shrink-0 opacity-75" />;
      case "search":
        return <Compass className="w-3.5 h-3.5 shrink-0 opacity-75" />;
      case "artifact":
        return <FileCode2 className="w-3.5 h-3.5 shrink-0 opacity-75" />;
      case "analysis":
        return <Calculator className="w-3.5 h-3.5 shrink-0 opacity-75" />;
      case "memory":
        return <NotebookPen className="w-3.5 h-3.5 shrink-0 opacity-75" />;
      case "evidence":
        return <FileText className="w-3.5 h-3.5 shrink-0 opacity-75" />;
      default:
        return <Check className="w-3.5 h-3.5 shrink-0 opacity-75" />;
    }
  };

  return (
    <div
      className="mb-3.5 rounded-xl border transition-colors"
      style={{
        backgroundColor: "var(--bg-muted)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 text-left text-xs transition-opacity hover:opacity-90 cursor-pointer"
        style={{ color: "var(--text-muted)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {runningStep || isStreaming ? (
            <Loader2
              className="w-3.5 h-3.5 animate-spin shrink-0"
              style={{ color: "var(--accent-warm)" }}
            />
          ) : isOpen ? (
            <ChevronDown className="w-3.5 h-3.5 shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 shrink-0" />
          )}
          <span
            className="font-medium truncate"
            style={{ color: "var(--text-primary)" }}
          >
            {runningStep
              ? runningStep.title
              : tr("{0} {1} completed", [steps.length, steps.length === 1 ? tr("agent step") : tr("agent steps")])}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 font-code text-[11px]">
          {totalMs > 0 && (
            <span>{(totalMs / 1000).toFixed(2)}s</span>
          )}
          <span aria-hidden="true">·</span>
          <span>{isOpen ? tr("Hide trace") : "Inspect"}</span>
        </div>
      </button>

      {isOpen && (
        <div
          className="border-t px-3.5 py-2.5 space-y-2"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          {steps.map((step) => {
            const hasDetail = Boolean(step.detail && step.detail.trim());
            
            return (
              <div key={step.id} className="text-xs">
                <div className="flex items-center justify-between gap-2 py-1">
                  <div className="flex items-center gap-2 min-w-0">
                    {renderStepIcon(step)}
                    <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                      {step.title}
                    </span>
                    {hasDetail && (
                      <span className="truncate font-code text-[11px]" style={{ color: "var(--text-muted)" }}>
                        {step.detail}
                      </span>
                    )}
                  </div>
                  {typeof step.durationMs === "number" && (
                    <span className="shrink-0 font-code text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {(step.durationMs / 1000).toFixed(2)}s
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
