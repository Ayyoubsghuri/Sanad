import type { AuditTraceRecord, OperatingMode } from "../types/agent";
import type { TraceDetail } from "./legalrag";

export function traceToAudit(created_at: string, t: TraceDetail): AuditTraceRecord {
  const total = t.checks?.claims_total ?? 0;
  const passed = t.checks?.claims_passed ?? 0;
  const failures = t.checks?.failures ?? [];
  const status = t.status;
  return {
    id: t.trace_id,
    timestamp: created_at.replace("T", " ").slice(0, 19),
    rawQuestionLength: t.pseudonymised_question?.length ?? 0,
    pseudonymisedQuery: t.pseudonymised_question ?? "(texte de la question non conservé)",
    asOfDate: t.as_of ?? "",
    operatingMode: ((t.mode ?? "hybrid").replace("_", "-") as OperatingMode),
    retrievedChunkIds: (t.retrieved ?? []).map((r) => `${r.provision_id}@${r.valid_from}`),
    verification: {
      citationExists: !failures.some((f) => /citation|unknown source/i.test(f)),
      quoteMatches: !failures.some((f) => /quote/i.test(f)),
      placeholdersIntact: !failures.some((f) => /placeholder/i.test(f)),
      versionValid: !failures.some((f) => /version|date/i.test(f)),
      noStrayNumbers: !failures.some((f) => /number/i.test(f)),
      claimSupportRate: total ? Math.round((passed / total) * 100) : 0,
      overallStatus: status === "answered" || status === "partial" ? "passed" : status === "abstained" || status === "extractive_only" ? "abstained" : "retried",
      abstainReason: failures.length ? failures.join("; ") : undefined,
    },
    outboundPayloadJson: JSON.stringify(
      { status, provider: t.provider, model: t.model, prompt_version: t.prompt_version, pack_version: t.pack_version, checks: t.checks },
      null,
      2
    ),
    claimsCount: t.claims?.length ?? 0,
    latencyMs: t.elapsed_ms ?? 0,
  };
}
