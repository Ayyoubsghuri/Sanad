// Search by meaning: local models or Cloudflare Workers AI (backend: /v1/compute). The API token is sent once and kept in the keychain.
import { call } from "./legalrag";

export interface ComputeState {
  source: "local" | "cloudflare";
  ram_gb: number | null;
  min_ram_gb: number;
  low_ram: boolean;
  local_models_installed: boolean;
  cloudflare_account: string;
  cloudflare_token_saved: boolean;
  cloudflare_ready: boolean;
  offline: boolean;
  pack_has_bge_m3: boolean;
}
export const getCompute = () => call<ComputeState>("/v1/compute");
export const setCompute = (body: { source?: "local" | "cloudflare"; account?: string; token?: string }) =>
  call<ComputeState>("/v1/compute", { method: "POST", body: JSON.stringify(body) });
export const testCompute = () => call<{ ok: boolean; dimensions?: number; error?: string }>("/v1/compute/test", { method: "POST" });
