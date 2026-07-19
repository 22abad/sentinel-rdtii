import { useEffect, useMemo, useState } from "react";
import { Copy, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import {
  getDiscoveryConfig,
  saveDiscoveryConfig,
} from "../../services/workflowNodes";
import type { DiscoveryRegistry, DiscoverySourceConfig } from "../../types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/Select";

const DEFAULT_SOURCE: DiscoverySourceConfig = {
  name: "New official source",
  base_url: "https://",
  domains: [],
  adapter: "search_engine",
  source_grade: "primary",
  source_type: "official_website",
  languages: ["en"],
  pillars: [6, 7],
  priority: 50,
  notes: "",
};

const SOURCE_GRADES: DiscoverySourceConfig["source_grade"][] = [
  "primary",
  "secondary",
  "unknown",
];
const ADAPTER_OPTIONS = [
  "australia_legislation",
  "search_engine",
  "china_flk",
  "malaysia_lom",
  "singapore_sso",
  "thailand_ocs",
];
const SOURCE_TYPES = [
  "statute_portal",
  "regulator",
  "government_portal",
  "official_website",
  "secondary_source",
];

export function DiscoverySourceManager() {
  const [registry, setRegistry] = useState<DiscoveryRegistry>({});
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedSourceIndex, setSelectedSourceIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const countryCodes = useMemo(() => Object.keys(registry).sort(), [registry]);
  const country = selectedCountry ? registry[selectedCountry] : undefined;
  const sources = country?.sources ?? [];
  const selectedSource = sources[selectedSourceIndex];

  useEffect(() => {
    void loadConfig();
  }, []);

  async function loadConfig() {
    if (dirty && !window.confirm("Discard unsaved discovery source changes?")) {
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const config = await getDiscoveryConfig();
      const codes = Object.keys(config).sort();
      setRegistry(config);
      setSelectedCountry((current) =>
        current && config[current] ? current : (codes[0] ?? ""),
      );
      setSelectedSourceIndex(0);
      setDirty(false);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load discovery source config.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function saveConfig() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveDiscoveryConfig(registry);
      setRegistry(saved);
      setDirty(false);
      setMessage("Saved");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to save discovery source config.",
      );
    } finally {
      setSaving(false);
    }
  }

  function replaceRegistry(next: DiscoveryRegistry) {
    setRegistry(next);
    setDirty(true);
    setError("");
    setMessage("");
  }

  function addCountry() {
    const rawCode = window.prompt("Country code, for example JPN");
    const code = rawCode?.trim().toUpperCase();
    if (!code) return;
    if (registry[code]) {
      setSelectedCountry(code);
      setSelectedSourceIndex(0);
      return;
    }
    replaceRegistry({
      ...registry,
      [code]: {
        label: code,
        languages: ["en"],
        sources: [],
      },
    });
    setSelectedCountry(code);
    setSelectedSourceIndex(0);
  }

  function deleteCountry() {
    if (!selectedCountry) return;
    const confirmed = window.confirm(
      `Delete ${selectedCountry} and all configured sources?`,
    );
    if (!confirmed) return;
    const next = { ...registry };
    delete next[selectedCountry];
    const nextCode = Object.keys(next).sort()[0] ?? "";
    replaceRegistry(next);
    setSelectedCountry(nextCode);
    setSelectedSourceIndex(0);
  }

  function updateCountryField(
    field: "label" | "languages",
    value: string | string[],
  ) {
    if (!selectedCountry || !country) return;
    replaceRegistry({
      ...registry,
      [selectedCountry]: {
        ...country,
        [field]: value,
      },
    });
  }

  function addSource() {
    if (!selectedCountry || !country) return;
    const nextSource = cloneSource(DEFAULT_SOURCE);
    replaceRegistry({
      ...registry,
      [selectedCountry]: {
        ...country,
        sources: [...sources, nextSource],
      },
    });
    setSelectedSourceIndex(sources.length);
  }

  function duplicateSource() {
    if (!selectedCountry || !country || !selectedSource) return;
    const copy = cloneSource(selectedSource);
    copy.name = `${copy.name} copy`;
    replaceRegistry({
      ...registry,
      [selectedCountry]: {
        ...country,
        sources: [
          ...sources.slice(0, selectedSourceIndex + 1),
          copy,
          ...sources.slice(selectedSourceIndex + 1),
        ],
      },
    });
    setSelectedSourceIndex(selectedSourceIndex + 1);
  }

  function deleteSource() {
    if (!selectedCountry || !country || !selectedSource) return;
    const confirmed = window.confirm(`Delete source "${selectedSource.name}"?`);
    if (!confirmed) return;
    const nextSources = sources.filter(
      (_source, index) => index !== selectedSourceIndex,
    );
    replaceRegistry({
      ...registry,
      [selectedCountry]: {
        ...country,
        sources: nextSources,
      },
    });
    setSelectedSourceIndex(
      Math.max(0, Math.min(selectedSourceIndex, nextSources.length - 1)),
    );
  }

  function updateSourceField<K extends keyof DiscoverySourceConfig>(
    field: K,
    value: DiscoverySourceConfig[K],
  ) {
    if (!selectedCountry || !country || !selectedSource) return;
    const nextSources = sources.map((source, index) =>
      index === selectedSourceIndex ? { ...source, [field]: value } : source,
    );
    replaceRegistry({
      ...registry,
      [selectedCountry]: {
        ...country,
        sources: nextSources,
      },
    });
  }

  return (
    <section
      className="source-manager-panel swiss-form"
      aria-label="Discovery source manager"
    >
      <div className="panel-header source-manager-header">
        <div>
          <h2>Source Manager</h2>
          <p>
            Maintain the configured official and secondary discovery sources.
          </p>
        </div>
        <div className="source-manager-actions">
          <button
            type="button"
            className="secondary"
            onClick={loadConfig}
            disabled={loading || saving}
          >
            <RefreshCw size={15} />
            Reload
          </button>
          <button
            type="button"
            onClick={saveConfig}
            disabled={loading || saving || !dirty}
          >
            <Save size={15} />
            {saving ? "Saving" : "Save"}
          </button>
        </div>
      </div>

      {error && <p className="discovery-error source-manager-alert">{error}</p>}
      {message && <p className="source-manager-success">{message}</p>}

      <div className="source-manager-layout">
        <aside className="source-manager-sidebar">
          <div className="source-manager-section-title">
            <span>Countries</span>
            <button type="button" onClick={addCountry} title="Add country">
              <Plus size={15} />
            </button>
          </div>

          {loading ? (
            <p className="source-manager-muted">Loading...</p>
          ) : countryCodes.length === 0 ? (
            <p className="source-manager-muted">No countries configured.</p>
          ) : (
            <div className="source-manager-country-list">
              {countryCodes.map((code) => (
                <button
                  key={code}
                  type="button"
                  className={code === selectedCountry ? "active" : ""}
                  onClick={() => {
                    setSelectedCountry(code);
                    setSelectedSourceIndex(0);
                  }}
                >
                  <span>{registry[code].label || code}</span>
                  <small>{code}</small>
                </button>
              ))}
            </div>
          )}
        </aside>

        <div className="source-manager-main">
          {country ? (
            <>
              <div className="source-manager-country-form">
                <label>
                  Country code
                  <input value={selectedCountry} readOnly />
                </label>
                <label>
                  Label
                  <input
                    value={country.label}
                    onChange={(event) =>
                      updateCountryField("label", event.target.value)
                    }
                  />
                </label>
                <label>
                  Languages
                  <ListInput
                    value={country.languages}
                    onCommit={(value) => updateCountryField("languages", value)}
                    placeholder="en, zh"
                  />
                </label>
                <button
                  type="button"
                  className="danger"
                  onClick={deleteCountry}
                >
                  <Trash2 size={15} />
                  Country
                </button>
              </div>

              <div className="source-manager-sources">
                <div className="source-manager-section-title">
                  <span>Sources</span>
                  <button type="button" onClick={addSource} title="Add source">
                    <Plus size={15} />
                  </button>
                </div>

                <div className="source-manager-source-list">
                  {sources.map((source, index) => (
                    <button
                      key={`${source.name}-${index}`}
                      type="button"
                      className={index === selectedSourceIndex ? "active" : ""}
                      onClick={() => setSelectedSourceIndex(index)}
                    >
                      <span>{source.name || "Untitled source"}</span>
                      <small>
                        {source.source_grade} · {source.adapter}
                      </small>
                    </button>
                  ))}
                  {sources.length === 0 && (
                    <p className="source-manager-muted">
                      No sources for this country.
                    </p>
                  )}
                </div>
              </div>

              {selectedSource ? (
                <SourceEditor
                  source={selectedSource}
                  onChange={updateSourceField}
                  onDuplicate={duplicateSource}
                  onDelete={deleteSource}
                />
              ) : (
                <div className="empty-state">
                  Add a source to start configuring discovery for this country.
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">
              Add a country to start managing discovery sources.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function SourceEditor({
  source,
  onChange,
  onDuplicate,
  onDelete,
}: {
  source: DiscoverySourceConfig;
  onChange: <K extends keyof DiscoverySourceConfig>(
    field: K,
    value: DiscoverySourceConfig[K],
  ) => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="source-manager-editor">
      <div className="source-manager-editor-header">
        <h3>{source.name || "Untitled source"}</h3>
        <div>
          <button type="button" className="secondary" onClick={onDuplicate}>
            <Copy size={15} />
            Copy
          </button>
          <button type="button" className="danger" onClick={onDelete}>
            <Trash2 size={15} />
            Delete
          </button>
        </div>
      </div>

      <div className="source-manager-form-grid">
        <label>
          Name
          <input
            value={source.name}
            onChange={(event) => onChange("name", event.target.value)}
          />
        </label>
        <label>
          Base URL
          <input
            value={source.base_url}
            onChange={(event) => onChange("base_url", event.target.value)}
          />
        </label>
        <label>
          Domains
          <ListInput
            value={source.domains}
            onCommit={(value) => onChange("domains", value)}
            placeholder="example.gov, www.example.gov"
          />
        </label>
        <label>
          Adapter
          <SourceSelect
            value={source.adapter}
            options={ADAPTER_OPTIONS}
            onChange={(value) => onChange("adapter", value)}
          />
        </label>
        <label>
          Source grade
          <SourceSelect
            value={source.source_grade}
            options={SOURCE_GRADES}
            onChange={(value) =>
              onChange(
                "source_grade",
                value as DiscoverySourceConfig["source_grade"],
              )
            }
          />
        </label>
        <label>
          Source type
          <SourceSelect
            value={source.source_type ?? "official_website"}
            options={SOURCE_TYPES}
            onChange={(value) => onChange("source_type", value)}
          />
        </label>
        <label>
          Languages
          <ListInput
            value={source.languages}
            onCommit={(value) => onChange("languages", value)}
            placeholder="en, zh"
          />
        </label>
        <label>
          Priority
          <input
            type="number"
            min={0}
            max={100}
            value={source.priority ?? 50}
            onChange={(event) =>
              onChange("priority", Number(event.target.value))
            }
          />
        </label>
        <label>
          Pillars
          <ListInput
            value={source.pillars}
            onCommit={(value) => onChange("pillars", splitNumbers(value))}
            placeholder="6, 7"
          />
        </label>
        <label>
          Indicators
          <ListInput
            value={source.indicators}
            onCommit={(value) => onChange("indicators", value)}
            placeholder="6.4, 7.1"
          />
        </label>
        <label>
          Search paths
          <ListInput
            value={source.search_paths}
            onCommit={(value) => onChange("search_paths", value)}
            placeholder="/laws, /policies"
          />
        </label>
        <label>
          Include patterns
          <ListInput
            value={source.include_patterns}
            onCommit={(value) => onChange("include_patterns", value)}
            placeholder="law, regulation, act"
          />
        </label>
        <label>
          Exclude patterns
          <ListInput
            value={source.exclude_patterns}
            onCommit={(value) => onChange("exclude_patterns", value)}
            placeholder="draft, consultation, archived"
          />
        </label>
        <label className="source-manager-notes">
          Notes
          <textarea
            value={source.notes ?? ""}
            onChange={(event) => onChange("notes", event.target.value)}
          />
        </label>
      </div>
    </div>
  );
}

function SourceSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="swiss-dropdown">
        {options.map((option) => (
          <SelectItem key={option} value={option}>
            {option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ListInput({
  value,
  onCommit,
  placeholder,
}: {
  value: Array<string | number> | undefined;
  onCommit: (value: string[]) => void;
  placeholder?: string;
}) {
  const serialized = joinList(value);
  const [draft, setDraft] = useState(serialized);

  useEffect(() => {
    setDraft(serialized);
  }, [serialized]);

  function commit() {
    onCommit(splitList(draft));
  }

  return (
    <input
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
      placeholder={placeholder}
    />
  );
}

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitNumbers(value: string | string[]): number[] {
  const items = Array.isArray(value) ? value : splitList(value);
  return items
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
}

function joinList(value: Array<string | number> | undefined): string {
  return (value ?? []).join(", ");
}

function cloneSource(source: DiscoverySourceConfig): DiscoverySourceConfig {
  return {
    ...source,
    domains: [...(source.domains ?? [])],
    languages: [...(source.languages ?? [])],
    pillars: [...(source.pillars ?? [])],
    indicators: [...(source.indicators ?? [])],
    search_paths: [...(source.search_paths ?? [])],
    include_patterns: [...(source.include_patterns ?? [])],
    exclude_patterns: [...(source.exclude_patterns ?? [])],
  };
}
