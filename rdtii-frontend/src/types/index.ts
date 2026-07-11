export type Pillar = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12;
export type Score = 0 | 0.25 | 0.5 | 1;
export type Scope = "horizontal" | "sectoral" | "unknown";

export type IndicatorMapping = {
  pillar: Pillar;
  indicator: string;
  score: Score;
  verbatim_quote: string;
  quote_start: number;
  quote_end: number;
  article_clause?: string;
  source_legislation: string;
  last_update: string;
  source_url: string;
  scope: Scope;
  coverage: string;
  cluster: string;
  region: string;
  cov_name: string;
  name: string;
  policy_description: string;
  features: Record<string, boolean | number | string>;
  impact: string;
  requires_human_review: boolean;
  flag_reasons?: string[];
  extraction_provider: string;
  timestamp_verification?: Record<string, unknown>;
};

export type RejectedExtraction = {
  reason: string;
  chunk_preview: string;
  raw_output: Record<string, unknown>;
};

export type RunUsageSummary = {
  run_id: string;
  llm_calls: number;
  successful_calls: number;
  failed_calls: number;
  calls_with_unknown_usage: number;
  input_tokens: number | null;
  output_tokens: number | null;
  known_input_tokens: number;
  known_output_tokens: number;
  cost_usd: number | null;
  known_cost_usd: number;
  latency_sum_ms: number;
  wall_clock_ms: number;
  operations: Record<string, number>;
};

export type ExtractionResponse = {
  mappings: IndicatorMapping[];
  rejected: RejectedExtraction[];
  provider: string;
  source_text?: string;
  usage?: RunUsageSummary | null;
};

export type ReviewDecision = "pending" | "approved" | "rejected";

export type Status = "idle" | "loading" | "ready" | "error";

export type DiscoverySourceMode = "official_first" | "official_only" | "broad_web";
export type DiscoveryRetrievalMode = "live" | "fixture" | "fallback";
export type DiscoveryValidationStatus =
  | "unverified"
  | "verified"
  | "weak"
  | "failed";

export type DiscoveryCountry = {
  country_code: string;
  label: string;
  languages: string[];
  source_count: number;
  supported_pillars: number[];
};

export type DiscoverySourceConfig = {
  name: string;
  base_url: string;
  domains: string[];
  source_grade: "primary" | "secondary" | "unknown";
  adapter: string;
  source_type?: string;
  languages?: string[];
  pillars?: number[];
  indicators?: string[];
  search_paths?: string[];
  include_patterns?: string[];
  exclude_patterns?: string[];
  priority?: number;
  notes?: string;
};

export type DiscoveryCountryRegistry = {
  label: string;
  languages: string[];
  sources: DiscoverySourceConfig[];
};

export type DiscoveryRegistry = Record<string, DiscoveryCountryRegistry>;

export type LegalCandidate = {
  id: string;
  country_code: string;
  title: string;
  url: string;
  source_domain: string;
  source_name: string;
  source_grade: "primary" | "secondary" | "unknown";
  document_type: string;
  language: string;
  last_update: string;
  matched_pillars: number[];
  matched_indicators: string[];
  snippet: string;
  confidence: number;
  rank_score: number;
  reasons: string[];
  warnings: string[];
  external_id: string;
  source_adapter: string;
  query: string;
  retrieval_mode: DiscoveryRetrievalMode;
  validation_status: DiscoveryValidationStatus;
  validation_metadata?: Record<string, unknown>;
};

export type DiscoverySearchResponse = {
  country_code: string;
  queries: string[];
  candidates: LegalCandidate[];
  diagnostics: {
    adapters_used?: string[];
    raw_hits?: number;
    deduped_hits?: number;
    filtered_low_relevance?: number;
    duration_ms?: number;
    mode?: string;
    retrieval_modes?: Partial<Record<DiscoveryRetrievalMode, number>>;
    live_hits?: number;
    fixture_hits?: number;
    fallback_hits?: number;
    live_search?: boolean;
    source_retrieval_modes?: Record<string, DiscoveryRetrievalMode[]>;
    source_mode?: DiscoverySourceMode;
    warnings?: string[];
    languages?: string[];
    sources_considered?: number;
    sources_skipped?: string[];
    validation_attempted?: number;
    validation_verified?: number;
    validation_failed?: number;
    validation_weak?: number;
  };
};
