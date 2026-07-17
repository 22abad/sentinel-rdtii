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

/** Poll a document's ingestion status ('processing' / 'processed' / 'failed'). */
export async function getCanvasFileStatus(documentId: string): Promise<string> {
  const res = await fetch(`${CANVAS_FILES_API_URL}/${encodeURIComponent(documentId)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Status check failed (HTTP ${res.status}).`);
  const payload = (await res.json()) as { status: string };
  return payload.status;
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
  return payload as CanvasFileUploadResponse;
}
