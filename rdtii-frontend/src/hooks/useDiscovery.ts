import { useState } from "react";
import type { DiscoverySearchResponse, DiscoverySourceMode } from "../types";
import { runDiscoverySearchNode } from "../services/workflowNodes";

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
      const payload = await runDiscoverySearchNode(request);
      setData(payload);
      return payload;
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
