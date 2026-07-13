import { EXCEL_EXPORT_API_URL } from "../lib/constants";
import { authHeaders, readErrorMessage } from "../lib/http";
import type { IndicatorMapping } from "../types";

export type ExcelExportRequest = {
  country: string;
  mappings: IndicatorMapping[];
  filename?: string;
};

export type ExcelExportOptions = {
  signal?: AbortSignal;
};

export type ExcelExportResult = {
  blob: Blob;
  filename: string;
};

export const RDTII_EXCEL_HEADERS = [
  "Pillar",
  "Indicator",
  "Score",
  "Act and/or practice",
  "Coverage",
  "Impacts or comments",
  "Timeframe",
  "Reference (URL)",
  "Verbatim Quote",
  "Provision Article",
  "Source Validation",
] as const;

export type ExcelPreviewRow = Record<
  (typeof RDTII_EXCEL_HEADERS)[number],
  string
>;

export async function exportMappingsExcel(
  request: ExcelExportRequest,
  options: ExcelExportOptions = {},
): Promise<ExcelExportResult> {
  const filename = request.filename ?? excelFilename(request.country);
  const res = await fetch(EXCEL_EXPORT_API_URL, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      country: request.country || "unknown",
      mappings: request.mappings,
      filename,
    }),
    signal: options.signal,
  });

  if (!res.ok) {
    throw new Error(
      await readErrorMessage(
        res,
        `Excel export failed with status ${res.status}.`,
      ),
    );
  }

  return {
    blob: await res.blob(),
    filename:
      filenameFromDisposition(res.headers.get("Content-Disposition")) ??
      filename,
  };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 100);
}

export function mappingsToExcelPreviewRows(
  mappings: IndicatorMapping[],
  limit?: number,
): ExcelPreviewRow[] {
  const visibleMappings =
    typeof limit === "number" ? mappings.slice(0, limit) : mappings;
  return visibleMappings.map((mapping) => {
    const features = mapping.features ?? {};
    return {
      Pillar: `Pillar ${mapping.pillar}`,
      Indicator: mapping.indicator,
      Score: String(mapping.score),
      "Act and/or practice": mapping.source_legislation || "",
      Coverage: mapping.scope === "unknown" ? "" : mapping.scope,
      "Impacts or comments": impactComment(mapping),
      Timeframe: timeframeDisplay(mapping),
      "Reference (URL)": mapping.source_url || "",
      "Verbatim Quote": mapping.verbatim_quote || "",
      "Provision Article":
        mapping.article_clause || mapping.verbatim_quote?.slice(0, 80) || "",
      "Source Validation": features._source_grade
        ? `Grade: ${String(features._source_grade)}`
        : "",
    };
  });
}

function excelFilename(country: string): string {
  const countrySlug =
    (country || "unknown")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "unknown";
  return `rdtii_mappings_${countrySlug}_${Date.now()}.xlsx`;
}

function impactComment(mapping: IndicatorMapping): string {
  const prefix = mapping.article_clause ? `[${mapping.article_clause}] ` : "";
  const interpretation =
    mapping.impact || `Mapping for indicator ${mapping.indicator}`;
  const provision = mapping.verbatim_quote
    ? `\nProvision: ${mapping.verbatim_quote.slice(0, 200)}`
    : "";
  return `${prefix}Interpretation: ${interpretation}${provision}`;
}

function timeframeDisplay(mapping: IndicatorMapping): string {
  const timeframeColumn = mapping.features?._timeframe_column;
  if (typeof timeframeColumn === "string" && timeframeColumn)
    return timeframeColumn;
  return mapping.last_update || "In force (date unknown)";
}

function filenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null;
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1].replace(/"/g, ""));
  const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
  return asciiMatch?.[1] ?? null;
}
