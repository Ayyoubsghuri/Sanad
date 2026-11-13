import { API_URL, ApiError, getToken } from "./legalrag";
import type { AttachmentItem } from "../types/agent";

export interface IngestResult {
  doc_id: string;
  case_id: string;
  status: "ready" | "review_required" | "reviewed";
  confidence: number;
  entity_counts: Record<string, number>;
  warnings: string[];
  unknown_capitalised_words?: string[];
  pseudonymised_preview: string;
  chars?: number;
  // client side
  filename: string;
  sensitive: boolean; // came from the encrypted vault
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [head, b64] = dataUrl.split(",");
  const mime = /data:([^;]+)/.exec(head)?.[1] || "application/octet-stream";
  const bin = atob(b64 || "");
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/** Text attachments are sent as .txt; PDFs / Word / images are sent as the original file (the backend extracts or OCRs them on the device). */
export function attachmentToFile(att: AttachmentItem): { blob: Blob; filename: string } | null {
  const safe = att.name.replace(/[\\/:*?"<>|]+/g, "_");
  if (att.textContent !== undefined) {
    return { blob: new Blob([att.textContent], { type: "text/plain" }), filename: /\.(txt|md|csv)$/i.test(safe) ? safe : `${safe}.txt` };
  }
  if (att.dataUrl) return { blob: dataUrlToBlob(att.dataUrl), filename: safe };
  return null;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { Authorization: `Bearer ${getToken()}`, ...(init.headers || {}) } });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* ignore */ }
    const detail = (body as { detail?: string } | null)?.detail;
    throw new ApiError(res.status, body, typeof detail === "string" ? detail : `Backend error ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Runs extraction + detection + masking on the device. The file itself is not kept by the backend (only encrypted extracted text). */
export async function ingestAttachment(att: AttachmentItem, caseId: string): Promise<IngestResult> {
  const f = attachmentToFile(att);
  if (!f) throw new ApiError(415, null, `${att.name}: nothing to read`);
  const form = new FormData();
  form.append("file", f.blob, f.filename);
  form.append("case_id", caseId);
  const r = await request<Omit<IngestResult, "filename" | "sensitive">>("/v1/documents", { method: "POST", body: form });
  return { ...r, filename: att.name, sensitive: att.source === "vault" };
}

export interface ReviewResult {
  doc_id: string;
  status: IngestResult["status"];
  confidence: number;
  entity_counts: Record<string, number>;
  warnings: string[];
  pseudonymised_preview: string;
}
export const reviewDocument = (docId: string, markTerms: string[], confirm: boolean) =>
  request<ReviewResult>(`/v1/documents/${docId}/review?confirm=${confirm}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(markTerms),
  });

export const deleteDocument = (docId: string) => request<void>(`/v1/documents/${docId}`, { method: "DELETE" });
