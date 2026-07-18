import { RELEASE_YEAR_API_URL, TIMESTAMP_API_URL } from "../lib/constants";
import { authHeaders } from "../lib/http";
import type { IndicatorMapping } from "../types";

// Mirrors the TUI report: resolve a law's release year (4 weighted signals,
// LLM-decided) and forensically verify its timestamp — both on demand.

export type ReleaseYear = {
  year: number | null;
  confidence: number;
  decided_by: string;
  candidates: Record<string, number>;
  tally: Record<string, number>;
};

export async function verifyReleaseYear(m: IndicatorMapping): Promise<ReleaseYear> {
  const features = (m.features ?? {}) as Record<string, unknown>;
  const res = await fetch(RELEASE_YEAR_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      source_legislation: m.source_legislation ?? "",
      quote: m.verbatim_quote ?? "",
      last_update: m.last_update ?? "",
      timeframe_column: String(features["_timeframe_column"] ?? ""),
    }),
  });
  if (!res.ok) throw new Error(`Release-year HTTP ${res.status}`);
  return (await res.json()) as ReleaseYear;
}

export type TimestampSource = { source: string; date: string; status: string };
export type TimestampVerification = {
  verified: boolean;
  best_date: string;
  verification_log: string;
  source_details: TimestampSource[];
};

export async function verifyTimestamp(
  url: string,
  lastUpdate: string,
): Promise<TimestampVerification> {
  const res = await fetch(TIMESTAMP_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ url, last_update: lastUpdate }),
  });
  if (!res.ok) throw new Error(`Timestamp HTTP ${res.status}`);
  return (await res.json()) as TimestampVerification;
}
