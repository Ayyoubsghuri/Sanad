// Bulletin Officiel auto-update (backend: /v1/bo/*). One job at a time; the UI polls GET /v1/bo/update.
import { call } from "./legalrag";

export type StepStatus = "pending" | "running" | "done" | "skipped" | "error";
export interface BoStep {
  id: "check" | "download" | "extract" | "ingest" | "install";
  label: string;
  status: StepStatus;
  done: number;
  total: number;
  detail: string;
}
export interface BoJob {
  id: string;
  state: "queued" | "running" | "done" | "error" | "cancelled";
  dry_run: boolean;
  progress: number; // 0..1 over all steps
  steps: BoStep[];
  found: { name: string; number: number; url: string }[];
  added: { issues?: number; instruments?: number; articles?: number; chunks?: number; edges?: number; pack_version?: string };
  warnings: string[];
  log: string[];
  error: string | null;
  started_at: string;
  finished_at: string | null;
}
export interface BoStatus {
  problems: string[];
  newest_local: number | null;
  issues_local: number;
  last_bo_check: string | null;
  job: BoJob | null;
}

export const getBoStatus = () => call<BoStatus>("/v1/bo/status");
export const startBoUpdate = (dryRun = false) => call<BoJob>("/v1/bo/update", { method: "POST", body: JSON.stringify({ dry_run: dryRun }) });
export const getBoJob = () => call<BoJob>("/v1/bo/update");
export const cancelBoUpdate = () => call<{ cancelling: boolean }>("/v1/bo/update/cancel", { method: "POST" });
