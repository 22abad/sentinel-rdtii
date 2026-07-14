import { CANVAS_FILES_API_URL } from "../lib/constants";
import { authHeaders, safeJsonParse } from "../lib/http";

export type CanvasFileUploadResponse = {
  document_id: string;
  status: string;
  deduplicated: boolean;
};

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
