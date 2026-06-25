import { useState } from "react";
import { DISCOVERY_API_URL } from "../lib/constants";
import type { DiscoverySearchResponse, DiscoverySourceMode } from "../types";

type DiscoveryRequest = {
  countryCode: string;
  pillars: number[];
  keywords: string;
  sourceMode: DiscoverySourceMode;
  languages: string[];
};

export function useDiscovery() {
  const [data, setData] = useState<DiscoverySearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search(request: DiscoveryRequest) {
    setLoading(true);
    setError("");
    setData(null);

    try {
      const res = await fetch(DISCOVERY_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          country_code: request.countryCode,
          pillars: request.pillars,
          keywords: request.keywords,
          source_mode: request.sourceMode,
          languages: request.languages,
          limit: 12,
          browser_mode: "auto",
        }),
      });
      const rawPayload = await res.text();
      const payload = rawPayload ? safeJsonParse(rawPayload) : null;
      if (!res.ok) {
        throw new Error(payload?.detail || rawPayload || "Discovery search failed.");
      }
      if (!payload) {
        throw new Error("Discovery search returned an empty response.");
      }
      setData(payload);
      return payload as DiscoverySearchResponse;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Discovery search failed.";
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }

  return {
    data,
    error,
    loading,
    search,
  };
}

function safeJsonParse(value: string): any {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
