import { CANVAS_FILES_API_URL, PARSE_FILE_API_URL } from "../lib/constants";
import { authHeaders, safeJsonParse } from "../lib/http";

/** Parse a file to plain text on the backend (no LLM run). */
export async function parseFile(file: File): Promise<{ text: string }> {
  // Plain-text formats don't need the backend PDF parser.
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return { text: await file.text() };
  }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(PARSE_FILE_API_URL, { method: "POST", body: form });
  const raw = await res.text();
  const payload = raw ? safeJsonParse(raw) : null;
  if (!res.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : null;
    throw new Error(typeof detail === "string" ? detail : `File parsing failed (HTTP ${res.status}).`);
  }
  return payload as { text: string };
}

export type CanvasFileUploadResponse = {
  document_id: string;
  status: string;
  deduplicated: boolean;
};

export type CanvasFileInfo = {
  document_id: string;
  filename: string;
  status: string;
  country_code: string | null;
  created_at: string | null;
};

/** List ingested documents (newest first). */
export async function listCanvasFiles(): Promise<CanvasFileInfo[]> {
  const res = await fetch(CANVAS_FILES_API_URL, { headers: authHeaders() });
  if (!res.ok) throw new Error(`List failed (HTTP ${res.status}).`);
  return (await res.json()) as CanvasFileInfo[];
}

/** Poll a document's ingestion status ('processing' / 'processed' / 'failed'). */
export async function getCanvasFileStatus(documentId: string): Promise<string> {
  const res = await fetch(`${CANVAS_FILES_API_URL}/${encodeURIComponent(documentId)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Status check failed (HTTP ${res.status}).`);
  const payload = (await res.json()) as { status: string };
  return payload.status;
}

/** Permanently delete an ingested document (chunks + embeddings cascade). */
/** Broadcast knowledge-base mutations so panels (Documents) refresh live. */
export const DOCUMENTS_CHANGED_EVENT = "rdtii:documents-changed";
function notifyDocumentsChanged() {
  window.dispatchEvent(new CustomEvent(DOCUMENTS_CHANGED_EVENT));
}

export async function deleteCanvasFile(documentId: string): Promise<void> {
  const res = await fetch(`${CANVAS_FILES_API_URL}/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Delete failed (HTTP ${res.status}).`);
  notifyDocumentsChanged();
}

/** Upload a canvas file to the backend for RAG ingestion (extract → chunk → embed). */
export async function uploadCanvasFile(
  file: File,
  countryCode?: string,
): Promise<CanvasFileUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (countryCode) form.append("country_code", countryCode);

  const res = await fetch(CANVAS_FILES_API_URL, {
    method: "POST",
    headers: authHeaders(), // no Content-Type — the browser sets the multipart boundary
    body: form,
  });
  const raw = await res.text();
  const payload = raw ? safeJsonParse(raw) : null;
  if (!res.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : null;
    throw new Error(
      typeof detail === "string" ? detail : `File ingest failed (HTTP ${res.status}).`,
    );
  }
  notifyDocumentsChanged();
  return payload as CanvasFileUploadResponse;
}
