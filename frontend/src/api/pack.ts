// The published law pack (backend: /v1/pack/update*): compare with the installed one, then download + verify + install it.
import { call } from "./legalrag";

export interface PackCheck {
  installed_version: string | null;
  installed_built_at: string | null;
  published_version?: string;
  size_bytes?: number;
  update_available?: boolean;
  key_matches?: boolean;
  problems: string[];
  error?: string;
  job: PackJob | null;
  checked_at: string;
}
export interface PackJob {
  state: "queued" | "running" | "done" | "error" | "cancelled";
  step: "check" | "download" | "verify" | "install";
  detail: string;
  done_bytes: number;
  total_bytes: number;
  progress: number;
  error: string | null;
  installed_version: string | null;
}

export const checkPackUpdate = () => call<PackCheck>("/v1/pack/update");
export const startPackUpdate = () => call<PackJob>("/v1/pack/update", { method: "POST" });
export const getPackUpdateJob = () => call<{ job: PackJob | null }>("/v1/pack/update/progress");
export const cancelPackUpdate = () => call<{ cancelling: boolean }>("/v1/pack/update/cancel", { method: "POST" });
