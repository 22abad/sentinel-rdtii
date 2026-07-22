import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckSquare,
  Download,
  ExternalLink,
  Loader2,
  Settings2,
  Square,
} from "lucide-react";
import { useDiscovery } from "../../hooks/useDiscovery";
import { listDiscoveryCountries } from "../../services/workflowNodes";
import type {
  DiscoveryCountry,
  DiscoverySourceMode,
  LegalCandidate,
} from "../../types";
import { DiscoverySourceManager } from "./DiscoverySourceManager";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/Select";
import { RightDrawer } from "../ui/RightDrawer";

type DiscoveryPanelProps = {
  country: string;
  pillarFilter: string;
  extracting: boolean;
  batchProgress: { current: number; total: number; currentUrl: string };
  onUseCandidate: (candidate: LegalCandidate) => void;
  onExtractCandidate: (candidate: LegalCandidate) => void;
  onExtractShortlist: (candidates: LegalCandidate[]) => void;
};

const DEFAULT_COUNTRY_OPTIONS: DiscoveryCountry[] = [
  {
    country_code: "AUS",
    label: "Australia",
    languages: ["en"],
    source_count: 1,
    supported_pillars: [6, 7],
  },
  {
    country_code: "CHN",
    label: "China",
    languages: ["zh", "en"],
    source_count: 3,
    supported_pillars: [6, 7],
  },
  {
    country_code: "SGP",
    label: "Singapore",
    languages: ["en"],
    source_count: 4,
    supported_pillars: [6, 7],
  },
  {
    country_code: "THA",
    label: "Thailand",
    languages: ["th", "en"],
    source_count: 3,
    supported_pillars: [6, 7],
  },
  {
    country_code: "MYS",
    label: "Malaysia",
    languages: ["en", "ms"],
    source_count: 3,
    supported_pillars: [6, 7],
  },
];

const SOURCE_MODE_OPTIONS: Array<{
  value: DiscoverySourceMode;
  label: string;
}> = [
  { value: "official_first", label: "Official first" },
  { value: "official_only", label: "Official only" },
];

const SOURCE_MODE_LABELS: Partial<Record<DiscoverySourceMode, string>> = {
  official_first: "Official first",
  official_only: "Official only",
};

function initialPillars(pillarFilter: string) {
  if (pillarFilter === "6") return [6];
  if (pillarFilter === "7") return [7];
  return [6, 7];
}

export function DiscoveryPanel({
  country,
  pillarFilter,
  extracting,
  batchProgress,
  onUseCandidate,
  onExtractCandidate,
  onExtractShortlist,
}: DiscoveryPanelProps) {
  const [countries, setCountries] = useState<DiscoveryCountry[]>(
    DEFAULT_COUNTRY_OPTIONS,
  );
  const [countryCode, setCountryCode] = useState(() =>
    DEFAULT_COUNTRY_OPTIONS.some((item) => item.country_code === country)
      ? country
      : "SGP",
  );
  const [pillars, setPillars] = useState<number[]>(() =>
    initialPillars(pillarFilter),
  );
  const [keywords, setKeywords] = useState("");
  const [sourceMode, setSourceMode] =
    useState<DiscoverySourceMode>("official_first");
  const [languageMode, setLanguageMode] = useState("auto");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [sourceManagerOpen, setSourceManagerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const { data, error, loading, search, reset } = useDiscovery();

  // Country switch must not leave the previous economy's candidates on
  // screen: clear stale results/selection, and if the panel was already
  // showing results, re-run discovery for the new economy automatically so a
  // demo flows without an extra click.
  const hasResultsRef = useRef(false);
  useEffect(() => {
    hasResultsRef.current = Boolean(data);
  }, [data]);
  const isFirstCountryRender = useRef(true);
  useEffect(() => {
    if (isFirstCountryRender.current) {
      isFirstCountryRender.current = false;
      return;
    }
    setSelectedIds([]);
    if (!hasResultsRef.current) return;
    reset();
    search({
      countryCode,
      pillars,
      keywords,
      sourceMode,
      languages: requestLanguages(),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countryCode]);

  useEffect(() => {
    let cancelled = false;
    listDiscoveryCountries()
      .then((items) => {
        if (cancelled || !items.length) return;
        setCountries(items);
        setCountryCode((current) => {
          if (items.some((item) => item.country_code === current))
            return current;
          if (items.some((item) => item.country_code === country))
            return country;
          return items[0].country_code;
        });
      })
      .catch(() => {
        // Keep the bundled defaults so the panel remains usable offline.
      });
    return () => {
      cancelled = true;
    };
  }, [country]);

  const selectedCountry = useMemo(
    () => countries.find((item) => item.country_code === countryCode),
    [countries, countryCode],
  );

  const localLanguage = useMemo(() => {
    const languages = selectedCountry?.languages ?? [];
    return languages.find((language) => language !== "en") ?? "en";
  }, [selectedCountry]);

  useEffect(() => {
    if (languageMode === "local" && localLanguage === "en") {
      setLanguageMode("auto");
    }
  }, [languageMode, localLanguage]);

  const diagnosticsText = useMemo(() => {
    if (!data) return "";
    const raw = data.diagnostics.raw_hits ?? 0;
    const deduped = data.diagnostics.deduped_hits ?? data.candidates.length;
    const duration = data.diagnostics.duration_ms ?? 0;
    return `${raw} raw, ${deduped} deduped, ${duration} ms`;
  }, [data]);

  const retrievalStatusText = useMemo(() => {
    if (!data) return "";
    const live = data.diagnostics.live_hits ?? 0;
    const fixture = data.diagnostics.fixture_hits ?? 0;
    const fallback = data.diagnostics.fallback_hits ?? 0;
    const parts = [
      live ? `${live} live` : "",
      fallback ? `${fallback} fallback` : "",
      fixture ? `${fixture} fixture` : "",
    ].filter(Boolean);
    return parts.join(", ") || "no hits";
  }, [data]);

  const retrievalDisclosure = useMemo(() => {
    if (!data) return null;
    const live =
      data.diagnostics.live_hits ??
      data.candidates.filter((candidate) => candidate.retrieval_mode === "live")
        .length;
    const fixture =
      data.diagnostics.fixture_hits ??
      data.candidates.filter(
        (candidate) => candidate.retrieval_mode === "fixture",
      ).length;
    const fallback =
      data.diagnostics.fallback_hits ??
      data.candidates.filter(
        (candidate) => candidate.retrieval_mode === "fallback",
      ).length;
    const fixtureFallback = fixture + fallback;

    // Live results win the badge: configured fallback seeds are ALWAYS
    // present, so "any fallback → Offline Mode" mislabelled every session as
    // offline even when live search succeeded. Only an all-fixture/fallback
    // result set is genuinely offline.
    if (live > 0) {
      return {
        kind: "live",
        label:
          fixtureFallback > 0
            ? `Live Search (${live} live · ${fixtureFallback} fallback)`
            : "Live Search",
        live,
        fixtureFallback,
      } as const;
    }
    if (fixtureFallback > 0) {
      return {
        kind: "fallback",
        label: "Offline Mode",
        live,
        fixtureFallback,
      } as const;
    }
    return {
      kind: "empty",
      label: "No evidence",
      live,
      fixtureFallback,
    } as const;
  }, [data]);

  function togglePillar(pillar: number) {
    setPillars((current) => {
      if (current.includes(pillar)) {
        const next = current.filter((item) => item !== pillar);
        return next.length ? next : current;
      }
      return [...current, pillar].sort();
    });
  }

  function toggleCandidate(candidateId: string) {
    setSelectedIds((current) =>
      current.includes(candidateId)
        ? current.filter((id) => id !== candidateId)
        : [...current, candidateId],
    );
  }

  function selectedCandidates() {
    return (
      data?.candidates.filter((candidate) =>
        selectedIds.includes(candidate.id),
      ) ?? []
    );
  }

  function requestLanguages() {
    if (languageMode === "auto") return [];
    if (languageMode === "en") return ["en"];
    return [localLanguage];
  }

  function exportSelectedCsv() {
    const rows = selectedCandidates();
    if (!rows.length) return;
    const headers = [
      "title",
      "url",
      "source_domain",
      "source_grade",
      "document_type",
      "language",
      "last_update",
      "matched_pillars",
      "matched_indicators",
      "rank_score",
      "reasons",
      "warnings",
      "snippet",
    ];
    const csv = [
      headers.join(","),
      ...rows.map((candidate) =>
        headers.map((header) => csvCell(candidate, header)).join(","),
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `discovery-shortlist-${countryCode.toLowerCase()}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 100);
  }

  return (
    <section className="discovery-panel swiss-form" aria-label="Discovery">
      <div className="panel-header discovery-header">
        <div>
          <h2>Discovery</h2>
          <p>Search official legal sources before extraction.</p>
        </div>
        <button
          type="button"
          className="panel-collapse nodrag"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand panel" : "Collapse panel"}
        >
          {collapsed ? "▸" : "▾"}
        </button>
      </div>
      {!collapsed && (
        <>

      <div className="discovery-controls">
        <label>
          Country
          <Select value={countryCode} onValueChange={setCountryCode}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="swiss-dropdown">
              {countries.map((item) => (
                <SelectItem key={item.country_code} value={item.country_code}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label>
          Source mode
          <Select
            value={sourceMode}
            onValueChange={(value) =>
              setSourceMode(value as DiscoverySourceMode)
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="swiss-dropdown">
              {SOURCE_MODE_OPTIONS.map(({ value, label }) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label>
          Language
          <Select value={languageMode} onValueChange={setLanguageMode}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="swiss-dropdown">
              <SelectItem value="auto">Auto</SelectItem>
              <SelectItem value="en">English</SelectItem>
              {localLanguage !== "en" && (
                <SelectItem value="local">Local ({localLanguage})</SelectItem>
              )}
            </SelectContent>
          </Select>
        </label>

        <label className="discovery-keywords">
          Keywords
          <input
            value={keywords}
            onChange={(event) => setKeywords(event.target.value)}
            placeholder="data export security assessment"
          />
        </label>

        <label className="discovery-pillars-select" style={{ gridColumn: "1 / -1" }}>
          Pillars
          <Select
            value={[...pillars].sort((a, b) => a - b).join(",") || "6,7"}
            onValueChange={(v) => setPillars(v.split(",").map(Number))}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="swiss-dropdown">
              <SelectItem value="6,7">P6 · P7</SelectItem>
              <SelectItem value="6">P6</SelectItem>
              <SelectItem value="7">P7</SelectItem>
            </SelectContent>
          </Select>
        </label>
      </div>

      {error && <p className="discovery-error">{error}</p>}

      {data && (
        <div className="discovery-results">
          {retrievalDisclosure && (
            <div
              className={`retrieval-disclosure ${retrievalDisclosure.kind}`}
              role="status"
            >
              {/* Just the mode, oversized — no counts, no note */}
              <strong>{retrievalDisclosure.label}</strong>
            </div>
          )}

          <div className="discovery-summary">
            <span>{data.candidates.length} candidates</span>
            <span>{diagnosticsText}</span>
          </div>

          <div className="discovery-diagnostics">
            <span>
              {SOURCE_MODE_LABELS[data.diagnostics.source_mode ?? sourceMode] ??
                data.diagnostics.source_mode ??
                sourceMode}
            </span>
            <span>
              {(data.diagnostics.languages ?? requestLanguages()).join("/") ||
                "auto"}
            </span>
            <span>{data.diagnostics.sources_considered ?? 0} sources</span>
            <span>{data.diagnostics.filtered_low_relevance ?? 0} filtered</span>
            {(data.diagnostics.validation_attempted ?? 0) > 0 && (
              <span>
                {data.diagnostics.validation_verified ?? 0}/
                {data.diagnostics.validation_attempted} validated
              </span>
            )}
            <span
              className={
                data.diagnostics.live_search
                  ? "discovery-mode-live"
                  : "discovery-mode-fallback"
              }
            >
              {retrievalStatusText}
            </span>
          </div>

          <div className="shortlist-tray">
            <span>{selectedIds.length} selected</span>
            <button
              type="button"
              className="secondary"
              disabled={extracting}
              onClick={() =>
                setSelectedIds(
                  data.candidates.slice(0, 5).map((candidate) => candidate.id),
                )
              }
            >
              Top 5
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!selectedIds.length || extracting}
              onClick={() => setSelectedIds([])}
            >
              Clear
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!selectedIds.length || extracting}
              onClick={exportSelectedCsv}
            >
              <Download size={13} />
              CSV
            </button>
            <button
              type="button"
              disabled={!selectedIds.length || extracting}
              onClick={() => onExtractShortlist(selectedCandidates())}
            >
              {extracting ? "Extracting" : "Extract selected"}
            </button>
          </div>

          {batchProgress.total > 0 && extracting && (
            <div className="shortlist-progress">
              <div>
                <span
                  style={{
                    width: `${Math.min(100, (batchProgress.current / batchProgress.total) * 100)}%`,
                  }}
                />
              </div>
              <p>
                {batchProgress.current} / {batchProgress.total}
                {batchProgress.currentUrl
                  ? ` · ${batchProgress.currentUrl}`
                  : ""}
              </p>
            </div>
          )}

          {(data.diagnostics.warnings ?? []).slice(0, 2).map((warning) => (
            <p className="discovery-warning" key={warning}>
              {warning}
            </p>
          ))}

          {(data.diagnostics.sources_skipped ?? [])
            .slice(0, 3)
            .map((source) => (
              <p className="discovery-warning" key={source}>
                {source}
              </p>
            ))}

          <div className="candidate-list">
            {data.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                selected={selectedIds.includes(candidate.id)}
                extracting={extracting}
                onToggleSelected={() => toggleCandidate(candidate.id)}
                onUse={() => onUseCandidate(candidate)}
                onExtract={() => onExtractCandidate(candidate)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="discovery-actions-bar nodrag">
        <button
          type="button"
          className="secondary discovery-source-menu-button"
          onClick={() => setSourceManagerOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={sourceManagerOpen}
          title="Source manager"
        >
          <Settings2 size={16} />
          <span>Sources</span>
        </button>
        <button
          type="button"
          onClick={() => {
            setSelectedIds([]);
            search({
              countryCode,
              pillars,
              keywords,
              sourceMode,
              languages: requestLanguages(),
            });
          }}
          disabled={loading || pillars.length === 0}
          className="discovery-run group flex items-center justify-center gap-2 h-14 cursor-pointer uppercase tracking-[0.2em] font-bold text-white transition-all duration-300"
          style={{ minHeight: 0, border: "none" }}
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          <span>{loading ? "Searching" : "Discover"}</span>
          {!loading && (
            <svg className="w-5 h-5 shrink-0 transition-transform duration-300 group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          )}
        </button>
      </div>
        </>
      )}

      <RightDrawer
        open={sourceManagerOpen}
        onOpenChange={setSourceManagerOpen}
        title="Source manager"
        closeLabel="Close source manager"
        className="source-manager-drawer"
      >
        <DiscoverySourceManager initialCountry={countryCode} />
      </RightDrawer>
    </section>
  );
}

function csvCell(candidate: LegalCandidate, header: string) {
  const value = (() => {
    switch (header) {
      case "matched_pillars":
        return candidate.matched_pillars.join("|");
      case "matched_indicators":
        return candidate.matched_indicators.join("|");
      case "reasons":
        return candidate.reasons.join("|");
      case "warnings":
        return candidate.warnings.join("|");
      default:
        return String(candidate[header as keyof LegalCandidate] ?? "");
    }
  })();
  return `"${value.replace(/"/g, '""')}"`;
}

function CandidateCard({
  candidate,
  selected,
  extracting,
  onToggleSelected,
  onUse,
  onExtract,
}: {
  candidate: LegalCandidate;
  selected: boolean;
  extracting: boolean;
  onToggleSelected: () => void;
  onUse: () => void;
  onExtract: () => void;
}) {
  const [open, setOpen] = useState(false);
  const grade = candidate.source_grade;
  const reasons = candidate.reasons ?? [];
  const warnings = candidate.warnings ?? [];
  const hasReport = reasons.length > 0 || warnings.length > 0;
  const rank = candidate.rank_score;

  return (
    <article
      className={`candidate-file${selected ? " selected" : ""}${open ? " open" : ""}`}
    >
      <div className="candidate-file-head">
        <button
          type="button"
          className="candidate-select"
          onClick={onToggleSelected}
          disabled={extracting}
          aria-label={selected ? "Remove from shortlist" : "Add to shortlist"}
        >
          {selected ? <CheckSquare size={16} /> : <Square size={16} />}
        </button>
        {/* The row itself is the disclosure toggle (file-list behaviour). */}
        <button
          type="button"
          className="candidate-file-main"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          <span className="candidate-chevron" aria-hidden="true">
            {open ? "▾" : "▸"}
          </span>
          <span className="candidate-name" title={candidate.title}>
            {candidate.title}
          </span>
          <span className="candidate-head-meta">
            <span className={`candidate-grade ${grade}`}>{grade}</span>
            {candidate.matched_pillars.length > 0 && (
              <span className="candidate-meta-pillars">
                {candidate.matched_pillars.map((p) => `P${p}`).join("·")}
              </span>
            )}
            {Number.isFinite(rank) && rank > 0 && (
              <span className="candidate-meta-rank">{rank.toFixed(2)}</span>
            )}
          </span>
        </button>
      </div>

      {open && (
        <div className="candidate-report reasoning-report">
          <section className="rr-section">
            <h4>Source</h4>
            <div className="candidate-report-value">
              {candidate.source_name || candidate.source_domain || "—"}
              {candidate.url && (
                <a
                  className="candidate-link"
                  href={candidate.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink size={12} />
                  Open
                </a>
              )}
            </div>
          </section>

          <section className="rr-section rr-sec-provenance">
            <h4>Provenance</h4>
            <div className="candidate-report-badges">
              <span className={`candidate-badge grade-${grade}`}>
                {gradeLabel(grade)}
              </span>
              <span
                className={`candidate-badge val-${candidate.validation_status}`}
              >
                {validationStatusLabel(candidate.validation_status)}
              </span>
              <span className={`candidate-badge retr-${candidate.retrieval_mode}`}>
                {retrievalModeLabel(candidate.retrieval_mode)}
              </span>
              {candidate.document_type && (
                <span className="candidate-badge">{candidate.document_type}</span>
              )}
              {candidate.language && (
                <span className="candidate-badge">
                  {candidate.language.toUpperCase()}
                </span>
              )}
              {candidate.last_update && (
                <span className="candidate-badge">{candidate.last_update}</span>
              )}
            </div>
          </section>

          {candidate.matched_indicators.length > 0 && (
            <section className="rr-section">
              <h4>Indicators</h4>
              <div className="candidate-report-value">
                {candidate.matched_indicators.join(" · ")}
              </div>
            </section>
          )}

          {candidate.snippet && (
            <section className="rr-section">
              <h4>Excerpt</h4>
              <p className="candidate-snippet">“{candidate.snippet}”</p>
            </section>
          )}

          {/* Match report as a band (audit result-list report style): WHY this
              candidate surfaced (numbered reasons) and any caveats (warnings). */}
          <section className="rr-section">
            <h4>Match report</h4>
            {reasons.length > 0 && (
              <ol className="candidate-reasons">
                {reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ol>
            )}
            {warnings.length > 0 && (
              <ul className="candidate-warnings">
                {warnings.map((warning, i) => (
                  <li key={i}>⚠ {warning}</li>
                ))}
              </ul>
            )}
            {!hasReport && (
              <p className="candidate-report-empty">
                No match reasons or warnings reported for this source.
              </p>
            )}
          </section>

          <div className="candidate-actions">
            <button
              type="button"
              className="secondary"
              onClick={onUse}
              disabled={extracting}
            >
              Use as source
            </button>
            <button type="button" onClick={onExtract} disabled={extracting}>
              Extract
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

function gradeLabel(grade: LegalCandidate["source_grade"]) {
  if (grade === "primary") return "Primary source";
  if (grade === "secondary") return "Secondary source";
  return "Unverified source";
}

function retrievalModeLabel(mode: LegalCandidate["retrieval_mode"]) {
  if (mode === "live") return "Live";
  if (mode === "fallback") return "Fixture fallback";
  return "Fixture";
}

function validationStatusLabel(status: string) {
  if (status === "verified") return "Validated";
  if (status === "weak") return "Weak validation";
  if (status === "failed") return "Validation failed";
  return status;
}
