import { tr } from "../i18n";
import { StepStatus, type AgentStep } from "../types/agent";
import type { ProgressStep } from "./legalrag";

/** The backend's step titles are English keys; translate them (the "Deep search · round N: …" ones carry a number). */
function title(t: string): string {
  const m = t.match(/^Deep search · round (\d+): (.+)$/);
  if (m) return `${tr("Deep search")} · ${tr("round {0}: " + m[2], [m[1]])}`;
  return tr(t);
}

const STAGE: Record<string, [string, string]> = {
  thinking: ["Thinking", "Thought"],
  search: ["Searching", "Searched"],
  evidence: ["Crystallizing", "Crystallized"],
  analysis: ["Analyzing", "Analyzed"],
  artifact: ["Drafting", "Drafted"],
  memory: ["Planning", "Planned"],
};

/** Law numbers found in a step's detail (e.g. 1.58.376, 65.99, 22.01), shown as one compact line. */
function lawNumbers(detail?: string): string | undefined {
  if (!detail) return undefined;
  const found = Array.from(new Set(detail.match(/\b\d{1,3}[.\-]\d{2,3}(?:[.\-]\d{2,3})?\b/g) || []));
  return found.length ? found.slice(0, 6).join(" · ") + (found.length > 6 ? " …" : "") : undefined;
}

export function toAgentSteps(steps: ProgressStep[]): AgentStep[] {
  return steps.map((s) => ({
    id: `bk-${s.id}`,
    kind: (["thinking", "search", "artifact", "analysis", "memory", "evidence"].includes(s.kind) ? s.kind : "search") as AgentStep["kind"],
    title: tr((STAGE[s.kind] || STAGE.search)[s.status === "running" ? 0 : 1]),
    detail: s.kind === "memory" && s.detail && !/one issue/.test(s.detail)
      ? tr("{0} issues", [String(s.detail.split("\n").filter((l) => l.trim()).length)])
      : lawNumbers(s.detail),
    status: s.status === "running" ? StepStatus.Running : StepStatus.Completed,
    durationMs: s.duration_ms ?? undefined,
  }));
}
