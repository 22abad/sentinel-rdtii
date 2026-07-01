import { useEffect, useMemo, useState } from "react";
import { CheckSquare, Download, ExternalLink, FileInput, Loader2, Search, Square } from "lucide-react";
import { useDiscovery } from "../../hooks/useDiscovery";
import { listDiscoveryCountries } from "../../services/workflowNodes";
import type { DiscoveryCountry, DiscoverySourceMode, LegalCandidate } from "../../types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/Select";

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
  { country_code: "AUS", label: "Australia", languages: ["en"], source_count: 1, supported_pillars: [6, 7] },
  { country_code: "CHN", label: "China", languages: ["zh", "en"], source_count: 3, supported_pillars: [6, 7] },
  { country_code: "SGP", label: "Singapore", languages: ["en"], source_count: 4, supported_pillars: [6, 7] },
  { country_code: "THA", label: "Thailand", languages: ["th", "en"], source_count: 3, supported_pillars: [6, 7] },
  { country_code: "MYS", label: "Malaysia", languages: ["en", "ms"], source_count: 3, supported_pillars: [6, 7] },
];

const SOURCE_MODE_OPTIONS: Array<{ value: DiscoverySourceMode; label: string }> = [
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
  const [countries, setCountries] = useState<DiscoveryCountry[]>(DEFAULT_COUNTRY_OPTIONS);
  const [countryCode, setCountryCode] = useState(() =>
    DEFAULT_COUNTRY_OPTIONS.some((item) => item.country_code === country) ? country : "SGP",
  );
  const [pillars, setPillars] = useState<number[]>(() => initialPillars(pillarFilter));
  const [keywords, setKeywords] = useState("");
  const [sourceMode, setSourceMode] = useState<DiscoverySourceMode>("official_first");
  const [languageMode, setLanguageMode] = useState("auto");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const { data, error, loading, search } = useDiscovery();

  useEffect(() => {
    let cancelled = false;
    listDiscoveryCountries()
      .then((items) => {
        if (cancelled || !items.length) return;
        setCountries(items);
        setCountryCode((current) => {
          if (items.some((item) => item.country_code === country)) return country;
          if (items.some((item) => item.country_code === current)) return current;
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
    return data?.candidates.filter((candidate) => selectedIds.includes(candidate.id)) ?? [];
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
      ...rows.map((candidate) => headers.map((header) => csvCell(candidate, header)).join(",")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `discovery-shortlist-${countryCode.toLowerCase()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="discovery-panel" aria-label="Discovery">
      <div className="panel-header discovery-header">
        <div>
          <h2>Discovery</h2>
          <p>Search official legal sources before extraction.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setSelectedIds([]);
            search({ countryCode, pillars, keywords, sourceMode, languages: requestLanguages() });
          }}
          disabled={loading || pillars.length === 0}
          className="group flex items-center justify-center rounded-full text-md h-10 px-5 cursor-pointer transition-all duration-500 bg-[#0f766e] text-white"
          style={{ minHeight: 0, border: "none" }}
        >
          {loading ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Search size={16} className="mr-2" />}
          <span>{loading ? "Searching" : "Discover"}</span>
        </button>
      </div>

      <div className="discovery-controls">
        <label>
          Country
          <Select value={countryCode} onValueChange={setCountryCode}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {countries.map((item) => (
                <SelectItem key={item.country_code} value={item.country_code}>{item.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label>
          Source mode
          <Select value={sourceMode} onValueChange={(value) => setSourceMode(value as DiscoverySourceMode)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {SOURCE_MODE_OPTIONS.map(({ value, label }) => (
                <SelectItem key={value} value={value}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label>
          Language
          <Select value={languageMode} onValueChange={setLanguageMode}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
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

        <div className="discovery-pillars" aria-label="Pillars">
          {[6, 7].map((pillar) => (
            <button
              key={pillar}
              type="button"
              className={pillars.includes(pillar) ? "discovery-toggle active" : "discovery-toggle"}
              onClick={() => togglePillar(pillar)}
            >
              P{pillar}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="discovery-error">{error}</p>}

      {data && (
        <div className="discovery-results">
          <div className="discovery-summary">
            <span>{data.candidates.length} candidates</span>
            <span>{diagnosticsText}</span>
          </div>

          <div className="discovery-diagnostics">
            <span>{SOURCE_MODE_LABELS[data.diagnostics.source_mode ?? sourceMode] ?? data.diagnostics.source_mode ?? sourceMode}</span>
            <span>{(data.diagnostics.languages ?? requestLanguages()).join("/") || "auto"}</span>
            <span>{data.diagnostics.sources_considered ?? 0} sources</span>
            <span>{data.diagnostics.filtered_low_relevance ?? 0} filtered</span>
          </div>

          <div className="shortlist-tray">
            <span>{selectedIds.length} selected</span>
            <button
              type="button"
              className="secondary"
              disabled={extracting}
              onClick={() => setSelectedIds(data.candidates.slice(0, 5).map((candidate) => candidate.id))}
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
                <span style={{ width: `${Math.min(100, (batchProgress.current / batchProgress.total) * 100)}%` }} />
              </div>
              <p>
                {batchProgress.current} / {batchProgress.total}
                {batchProgress.currentUrl ? ` · ${batchProgress.currentUrl}` : ""}
              </p>
            </div>
          )}

          {(data.diagnostics.warnings ?? []).slice(0, 2).map((warning) => (
            <p className="discovery-warning" key={warning}>{warning}</p>
          ))}

          {(data.diagnostics.sources_skipped ?? []).slice(0, 3).map((source) => (
            <p className="discovery-warning" key={source}>{source}</p>
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
  return (
    <article className={selected ? "candidate-card selected" : "candidate-card"}>
      <div className="candidate-topline">
        <button
          type="button"
          className="candidate-select"
          onClick={onToggleSelected}
          disabled={extracting}
          aria-label={selected ? "Remove from shortlist" : "Add to shortlist"}
        >
          {selected ? <CheckSquare size={18} /> : <Square size={18} />}
        </button>
        <div className="candidate-title-group">
          <h3>{candidate.title}</h3>
          <p>{candidate.source_domain}</p>
        </div>
        <span className="candidate-score">{Math.round(candidate.rank_score)}</span>
      </div>

      <div className="candidate-badges">
        <span>{candidate.source_grade}</span>
        <span>{candidate.document_type}</span>
        {candidate.matched_indicators.slice(0, 4).map((indicator) => (
          <span key={indicator}>{indicator}</span>
        ))}
      </div>

      {candidate.snippet && <p className="candidate-snippet">{candidate.snippet}</p>}

      {candidate.reasons.length > 0 && (
        <p className="candidate-reasons">{candidate.reasons.slice(0, 3).join(" · ")}</p>
      )}

      {candidate.warnings.length > 0 && (
        <div className="candidate-warnings">
          {candidate.warnings.slice(0, 2).map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </div>
      )}

      <div className="candidate-actions">
        <a href={candidate.url} target="_blank" rel="noreferrer">
          <ExternalLink size={14} />
          Open
        </a>
        <button type="button" className="secondary" onClick={onUse} disabled={extracting}>
          <FileInput size={14} />
          Use URL
        </button>
        <button type="button" onClick={onExtract} disabled={extracting}>
          <Search size={14} />
          Extract
        </button>
      </div>
    </article>
  );
}
