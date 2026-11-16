// AI providers chosen in the app (backend: /v1/llm-providers). Keys are sent once and stored in the OS keychain; the API only says has_key.
import { call } from "./legalrag";

export type ProviderKind = "openai" | "anthropic" | "openai_compat" | "local";
export interface Provider {
  id: string;
  kind: ProviderKind;
  label: string;
  model: string;
  base_url: string | null;
  has_key: boolean;
}
export interface Preset {
  kind: ProviderKind;
  label: string;
  base_url: string;
  models: string[];
  needs_key: boolean;
  note?: string;
}
export interface ProvidersState {
  active: string | null;
  checker: string | null;
  offline: string | null;
  providers: Provider[];
  presets: Preset[];
  mode: string;
  key_storage: string;
  environment_provider: { provider: string; model: string | null } | null;
}

export const listProviders = () => call<ProvidersState>("/v1/llm-providers");
export const saveProvider = (id: string, body: { kind: ProviderKind; label: string; model: string; base_url?: string | null; api_key?: string | null }) =>
  call<ProvidersState>(`/v1/llm-providers/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) });
export const deleteProvider = (id: string) => call<void>(`/v1/llm-providers/${encodeURIComponent(id)}`, { method: "DELETE" });
export const setActiveProvider = (id: string | null) => call<ProvidersState>("/v1/llm-providers/active", { method: "POST", body: JSON.stringify({ id }) });
export const setCheckerProvider = (id: string | null) => call<ProvidersState>("/v1/llm-providers/checker", { method: "POST", body: JSON.stringify({ id }) });
export const testProvider = (id: string) => call<{ ok: boolean; model?: string; error?: string }>(`/v1/llm-providers/${encodeURIComponent(id)}/test`, { method: "POST" });
export const setOfflineProvider = (id: string | null) => call<ProvidersState>("/v1/llm-providers/offline", { method: "POST", body: JSON.stringify({ id }) });
export const localModels = (base_url: string) =>
  call<{ ok: boolean; base_url: string; models: string[]; error?: string }>(`/v1/llm-providers/local-models?base_url=${encodeURIComponent(base_url)}`);
