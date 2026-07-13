export const API_URL =
  import.meta.env.VITE_EXTRACT_API_URL ?? "/api/extract";

export const INGEST_API_URL =
  import.meta.env.VITE_INGEST_API_URL ?? "/api/ingest/document";

export const FETCH_TEXT_API_URL =
  import.meta.env.VITE_FETCH_TEXT_API_URL ?? "/api/fetch-text";

export const DISCOVERY_API_URL =
  import.meta.env.VITE_DISCOVERY_API_URL ?? "/api/discovery/search";

export const DISCOVERY_BASE_URL =
  import.meta.env.VITE_DISCOVERY_BASE_URL ?? "/api/discovery";

export const REVIEW_API_URL =
  import.meta.env.VITE_REVIEW_API_URL ?? "/api/mappings/review";

export const EXCEL_EXPORT_API_URL =
  import.meta.env.VITE_EXCEL_EXPORT_API_URL ?? "/api/excel/export";

export const WORKFLOW_API_URL =
  import.meta.env.VITE_WORKFLOW_API_URL ?? "/api/workflows";

export const DISCOVERY_SEARCH_TIMEOUT_MS = envNumber(
  import.meta.env.VITE_DISCOVERY_SEARCH_TIMEOUT_MS,
  60_000,
);

export const WORKBENCH_CANVAS_API_URL =
  import.meta.env.VITE_WORKBENCH_CANVAS_API_URL ?? "/api/workbench-canvas";

export const AUTH_API_URL =
  import.meta.env.VITE_AUTH_API_URL ?? "/auth";

export const QUOTE_TRUNCATE = 280;

export const sampleText = "";

function envNumber(value: unknown, fallback: number): number {
  if (typeof value !== "string" || value.trim() === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}
