import { useState, useEffect, useCallback, useSyncExternalStore } from "react";
import { INGEST_API_URL, REVIEW_API_URL } from "../lib/constants";
import {
  DEFAULT_THREAD_ID,
  getThreadAbortRef,
  getThreadDetectTimerRef,
  getThreadSnapshot,
  subscribeThread,
  updateThread,
  type ExtractionThreadState,
} from "./extractionStore";
import { demoAuditExtraction } from "../data/demoAuditMappings";
import { authHeaders, readErrorMessage } from "../lib/http";
import { t } from "../lib/i18n";
import { mappingKey } from "../lib/utils";
import {
  formatWorkflowErrorPayload,
  streamExtractMappingsNode,
  type NodeResult,
  type WorkflowRunEvent,
} from "../services/workflowNodes";
import type {
  ExtractionResponse,
  IndicatorMapping,
  RejectedExtraction,
  ReviewDecision,
  RunUsageSummary,
  Status,
} from "../types";

const DEFAULT_PROVIDER = "deepseek";
const DEFAULT_PROVIDER_VERSION = "deepseek-v4-default";
const DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash";
const DEEPSEEK_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"] as const;
const DEFAULT_PROVIDERS = [
  "deepseek",
  "gemini",
  "openai",
  "claude",
  "groq",
  "mistral",
  "openrouter",
  "together",
  "ollama",
];

function initialSelectedProvider() {
  if (
    localStorage.getItem("providerDefaultVersion") !== DEFAULT_PROVIDER_VERSION
  ) {
    localStorage.setItem("providerDefaultVersion", DEFAULT_PROVIDER_VERSION);
    localStorage.setItem("selectedProvider", DEFAULT_PROVIDER);
    return DEFAULT_PROVIDER;
  }
  return localStorage.getItem("selectedProvider") || DEFAULT_PROVIDER;
}

function normalizeDeepSeekModel(value: string | null) {
  return DEEPSEEK_MODELS.includes(value as (typeof DEEPSEEK_MODELS)[number])
    ? value!
    : DEFAULT_DEEPSEEK_MODEL;
}

type ExtractionStreamPayload =
  | Record<string, unknown>
  | IndicatorMapping
  | RejectedExtraction
  | NodeResult<ExtractionResponse>
  | string
  | null;

function mergeUsageSummaries(
  current: RunUsageSummary | null,
  next: RunUsageSummary | null | undefined,
  runId: string,
): RunUsageSummary | null {
  if (!next) return current;
  if (!current) return { ...next, run_id: runId };
  const operations = { ...current.operations };
  for (const [name, count] of Object.entries(next.operations)) {
    operations[name] = (operations[name] ?? 0) + count;
  }
  return {
    run_id: runId,
    llm_calls: current.llm_calls + next.llm_calls,
    successful_calls: current.successful_calls + next.successful_calls,
    failed_calls: current.failed_calls + next.failed_calls,
    calls_with_unknown_usage:
      current.calls_with_unknown_usage + next.calls_with_unknown_usage,
    input_tokens:
      current.input_tokens !== null && next.input_tokens !== null
        ? current.input_tokens + next.input_tokens
        : null,
    output_tokens:
      current.output_tokens !== null && next.output_tokens !== null
        ? current.output_tokens + next.output_tokens
        : null,
    known_input_tokens: current.known_input_tokens + next.known_input_tokens,
    known_output_tokens: current.known_output_tokens + next.known_output_tokens,
    cost_usd:
      current.cost_usd !== null && next.cost_usd !== null
        ? current.cost_usd + next.cost_usd
        : null,
    known_cost_usd: current.known_cost_usd + next.known_cost_usd,
    latency_sum_ms: current.latency_sum_ms + next.latency_sum_ms,
    wall_clock_ms: current.wall_clock_ms + next.wall_clock_ms,
    operations,
  };
}

// A short, human-readable page label for a batch document: the URL's last path
// segment (decoded), falling back to host, then the raw string.
function shortDocTitle(url: string): string {
  try {
    const u = new URL(url);
    const seg = u.pathname.split("/").filter(Boolean).pop();
    return decodeURIComponent(seg || u.hostname);
  } catch {
    return url;
  }
}

export function useExtractionThread(threadId: string = DEFAULT_THREAD_ID) {
  // Per-thread run state lives in the external store (see extractionStore.ts)
  // so it survives panel unmount and can be shared by sibling canvas nodes.
  const thread = useSyncExternalStore(
    useCallback((callback: () => void) => subscribeThread(threadId, callback), [threadId]),
    () => getThreadSnapshot(threadId),
  );
  const {
    country,
    pillarFilter,
    sourceUrl,
    text,
    status,
    error,
    warning,
    response,
    isStopping,
    activeKey,
    decisions,
    showRejected,
    extractionProgress,
    batchProgress,
    foundPdfs,
    detectedCountry,
  } = thread;

  // React-style setters (functional updates included) writing to the thread
  // slice — names preserved so the extraction logic below stays unchanged.
  function makeSetter<K extends keyof ExtractionThreadState>(key: K) {
    return (
      value:
        | ExtractionThreadState[K]
        | ((prev: ExtractionThreadState[K]) => ExtractionThreadState[K]),
    ) =>
      updateThread(threadId, (prev) => ({
        [key]:
          typeof value === "function"
            ? (value as (p: ExtractionThreadState[K]) => ExtractionThreadState[K])(prev[key])
            : value,
      }) as Partial<ExtractionThreadState>);
  }
  const setCountry = makeSetter("country");
  const setPillarFilter = makeSetter("pillarFilter");
  const setSourceUrl = makeSetter("sourceUrl");
  const setText = makeSetter("text");
  const setStatus = makeSetter("status");
  const setError = makeSetter("error");
  const setWarning = makeSetter("warning");
  const setResponse = makeSetter("response");
  const setIsStopping = makeSetter("isStopping");
  const setActiveKey = makeSetter("activeKey");
  const setDecisions = makeSetter("decisions");
  const setShowRejected = makeSetter("showRejected");
  const setExtractionProgress = makeSetter("extractionProgress");
  const setBatchProgress = makeSetter("batchProgress");
  const setFoundPdfs = makeSetter("foundPdfs");
  const setDetectedCountry = makeSetter("detectedCountry");

  const extractionAbortRef = getThreadAbortRef(threadId);

  const [availableProviders, setAvailableProviders] =
    useState<string[]>(DEFAULT_PROVIDERS);

  // Persistent state using localStorage to remember user's last selection
  const [selectedProvider, setSelectedProviderState] = useState(
    initialSelectedProvider,
  );
  const setSelectedProvider = (val: string) => {
    setSelectedProviderState(val);
    localStorage.setItem("selectedProvider", val);
  };

  const [selectedOllamaModel, setSelectedOllamaModelState] = useState(
    () => localStorage.getItem("selectedOllamaModel") || "qwen2.5:14b",
  );
  const setSelectedOllamaModel = (val: string) => {
    setSelectedOllamaModelState(val);
    localStorage.setItem("selectedOllamaModel", val);
  };

  const [selectedGeminiModel, setSelectedGeminiModelState] = useState(
    () => localStorage.getItem("selectedGeminiModel") || "gemini-2.0-flash",
  );
  const setSelectedGeminiModel = (val: string) => {
    setSelectedGeminiModelState(val);
    localStorage.setItem("selectedGeminiModel", val);
  };

  const [selectedDeepSeekModel, setSelectedDeepSeekModelState] = useState(() =>
    normalizeDeepSeekModel(localStorage.getItem("selectedDeepSeekModel")),
  );
  const setSelectedDeepSeekModel = (val: string) => {
    const next = normalizeDeepSeekModel(val);
    setSelectedDeepSeekModelState(next);
    localStorage.setItem("selectedDeepSeekModel", next);
  };

  const [vertexModels, setVertexModels] = useState<string[]>([]);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);

  // ── Country auto-detection ──────────────────────────────────────
  const detectTimer = getThreadDetectTimerRef(threadId);

  function triggerCountryDetect(srcUrl: string, srcText: string) {
    if (detectTimer.current) clearTimeout(detectTimer.current);
    const hasUrl = srcUrl.trim().length > 0;
    const hasText = srcText.trim().length > 80;
    if (!hasUrl && !hasText) return;

    detectTimer.current = setTimeout(
      async () => {
        try {
          const body = hasUrl
            ? JSON.stringify({
                source_url: srcUrl,
                text: srcText.slice(0, 3000),
              })
            : JSON.stringify({ text: srcText.slice(0, 3000) });
          const res = await fetch("/api/detect/country", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body,
          });
          if (!res.ok) return;
          const data = await res.json();
          if (data.detected && data.code) {
            setDetectedCountry({
              code: data.code,
              name: data.name,
              detected: true,
            });
            setCountry(data.code);
          } else if (!detectedCountry) {
            // Only clear if user hasn't manually selected
            setDetectedCountry({ code: "", name: "", detected: false });
          }
        } catch {
          /* network errors — ignore */
        }
      },
      hasUrl ? 300 : 800,
    );
  }

  // Trigger on initial text
  useEffect(() => {
    if (text.trim().length > 80) {
      triggerCountryDetect(sourceUrl, text);
    }
  }, []);

  useEffect(() => {
    fetch("/health")
      .then((res) => res.json())
      .then((data) => {
        if (data.available_providers?.length)
          setAvailableProviders(data.available_providers);
        if (data.active_provider && !localStorage.getItem("selectedProvider")) {
          setSelectedProvider(data.active_provider);
        }
      })
      .catch(() => {});
    fetch("/providers/ollama-models")
      .then((res) => res.json())
      .then((data) => {
        if (data.models && data.models.length > 0) {
          setOllamaModels(data.models);
          if (
            !localStorage.getItem("selectedOllamaModel") &&
            !data.models.includes("gemma4:12b")
          ) {
            setSelectedOllamaModel(data.models[0]);
          }
        }
      })
      .catch(() => {});
    fetch("/providers/vertex-models")
      .then((res) => res.json())
      .then((data) => {
        if (data.models && data.models.length > 0) {
          setVertexModels(data.models);
        }
      })
      .catch(() => {});
  }, []);

  const mappings = response?.mappings ?? [];
  const rejected = response?.rejected ?? [];
  const provider = response?.provider ?? "—";
  const usage = response?.usage ?? null;
  const activeMapping =
    mappings.find((m) => mappingKey(m) === activeKey) ?? null;

  // pillarFilter is "all" or a comma list ("6,7") — multi-select chips.
  const visibleMappings = mappings.filter((m) =>
    pillarFilter === "all" ? true : pillarFilter.split(",").includes(String(m.pillar)),
  );

  const pendingCount = mappings.filter(
    (m) => (decisions[mappingKey(m)] ?? "pending") === "pending",
  ).length;

  function _fixMapping(
    m: IndicatorMapping,
    fallbackUrl: string,
  ): IndicatorMapping {
    const isHallucinatedUrl =
      !m.source_url ||
      m.source_url.toLowerCase().includes("n/a") ||
      m.source_url.toLowerCase().includes("not specified");
    const isHallucinatedDate =
      !m.last_update ||
      m.last_update.toLowerCase().includes("n/a") ||
      m.last_update.toLowerCase().includes("not specified");
    const isLegislationUrl =
      /^https?:\/\//i.test(m.source_legislation ?? "") ||
      (m.source_legislation ?? "").includes("://");
    return {
      ...m,
      source_url: isHallucinatedUrl ? fallbackUrl : m.source_url,
      last_update: isHallucinatedDate
        ? new Date().toISOString().split("T")[0]
        : m.last_update,
      source_legislation: isLegislationUrl ? "" : m.source_legislation,
    };
  }

  async function runExtractionStream({
    runSourceUrl,
    requestText,
    baseMappings = [],
    baseRejected = [],
    updateTextFromSource = true,
    setReadyOnDone = true,
    signal,
  }: {
    runSourceUrl: string;
    requestText: string;
    baseMappings?: IndicatorMapping[];
    baseRejected?: RejectedExtraction[];
    updateTextFromSource?: boolean;
    setReadyOnDone?: boolean;
    signal?: AbortSignal;
  }): Promise<ExtractionResponse> {
    // Unify Vertex AI under Gemini brand in frontend, and handle DeepSeek options
    let actualProvider = selectedProvider;
    let actualModel = "";
    if (selectedProvider === "ollama") {
      actualModel = selectedOllamaModel;
    } else if (selectedProvider === "gemini") {
      if (vertexModels.includes(selectedGeminiModel)) {
        actualProvider = "vertex-ai";
      }
      actualModel = selectedGeminiModel;
    } else if (selectedProvider === "deepseek") {
      actualModel = selectedDeepSeekModel;
    }

    const collectedMappings: IndicatorMapping[] = [...baseMappings];
    const collectedRejected: RejectedExtraction[] = [...baseRejected];
    const newMappings: IndicatorMapping[] = [];
    const newRejected: RejectedExtraction[] = [];
    let sourceText = "";
    let providerName = "";
    let runUsage: RunUsageSummary | null = null;

    for await (const event of streamExtractMappingsNode({
      text: runSourceUrl ? "" : requestText,
      sourceUrl: runSourceUrl,
      provider: actualProvider,
      model: actualModel || undefined,
      browserMode: "auto",
    }, { signal }) as AsyncIterable<WorkflowRunEvent<ExtractionStreamPayload>>) {
      const payload = event.payload;

      if (event.event === "error" || event.status === "failed") {
        throw new Error(extractionStreamError(payload));
      }

      if (event.event === "warning" && isRecord(payload)) {
        const data = payload as Record<string, unknown>;
        setWarning(String(data.message ?? ""));
      }

      if (event.event === "progress" && isRecord(payload)) {
        const data = payload as Record<string, unknown>;
        setExtractionProgress({
          current: Number(data.current ?? 0),
          total: Number(data.total ?? 0),
          phase: String(data.phase ?? ""),
        });
      }

      if (event.event === "started" && isRecord(payload)) {
        const data = payload as Record<string, unknown>;
        const nextSourceText =
          typeof data.source_text === "string" ? data.source_text : "";
        if (nextSourceText) {
          sourceText = nextSourceText;
          if (updateTextFromSource) setText(nextSourceText);
        }
      }

      if (event.event === "mapping" && isRecord(payload)) {
        const m = _fixMapping(payload as IndicatorMapping, runSourceUrl);
        newMappings.push(m);
        collectedMappings.push(m);
        // Progressive render — derive state from local arrays, never from prev
        // (avoids stale-closure bleed when setResponse(null) hasn't flushed yet)
        setResponse({
          mappings: [...collectedMappings],
          rejected: [...collectedRejected],
          provider: providerName,
          source_text: sourceText,
          usage: runUsage,
        });
      }

      if (event.event === "rejected" && isRecord(payload)) {
        const rejectedItem = payload as RejectedExtraction;
        newRejected.push(rejectedItem);
        collectedRejected.push(rejectedItem);
        setResponse({
          mappings: [...collectedMappings],
          rejected: [...collectedRejected],
          provider: providerName,
          source_text: sourceText,
          usage: runUsage,
        });
      }

      if (event.event === "done" && isRecord(payload)) {
        const data = payload as Record<string, unknown>;
        providerName = String(data.provider ?? providerName);
        if (isRunUsageSummary(data.usage)) runUsage = data.usage;
        if (setReadyOnDone) setStatus("ready");
      }

      if (event.event === "usage" && isRunUsageSummary(payload)) {
        runUsage = payload;
        setResponse({
          mappings: [...collectedMappings],
          rejected: [...collectedRejected],
          provider: providerName,
          source_text: sourceText,
          usage: runUsage,
        });
      }

      if (event.event === "node_output" && isNodeResult(payload)) {
        if (payload.status !== "success") {
          throw new Error(payload.error || t("error.stream"));
        }
        providerName = String(payload.outputs.provider ?? providerName);
        sourceText = String(payload.outputs.source_text ?? sourceText);
        // Safety net for replayed/cached runs that skipped the `started`
        // event: the highlight view needs the source text in the panel.
        if (updateTextFromSource && sourceText) setText(sourceText);
        // Same safety net for the rejected log — it's the "what was filtered
        // out and why" evidence; a replay that omitted the per-item events
        // must not present a run as if nothing was ever rejected.
        if (
          newRejected.length === 0 &&
          Array.isArray(payload.outputs.rejected) &&
          payload.outputs.rejected.length > 0
        ) {
          for (const item of payload.outputs.rejected as RejectedExtraction[]) {
            newRejected.push(item);
            collectedRejected.push(item);
          }
        }
        if (isRunUsageSummary(payload.outputs.usage)) {
          runUsage = payload.outputs.usage;
        }
        setResponse({
          mappings: [...collectedMappings],
          rejected: [...collectedRejected],
          provider: providerName,
          source_text: sourceText,
          usage: runUsage,
        });
      }
    }

    return {
      mappings: newMappings,
      rejected: newRejected,
      provider: providerName,
      source_text: sourceText,
      usage: runUsage,
    };
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
  }

  function isNodeResult(
    value: unknown,
  ): value is NodeResult<ExtractionResponse> {
    return (
      isRecord(value) &&
      typeof value.status === "string" &&
      isRecord(value.outputs)
    );
  }

  function isRunUsageSummary(value: unknown): value is RunUsageSummary {
    return (
      isRecord(value) &&
      typeof value.run_id === "string" &&
      typeof value.llm_calls === "number" &&
      typeof value.wall_clock_ms === "number"
    );
  }

  function extractionStreamError(payload: unknown): string {
    if (isNodeResult(payload)) {
      return payload.error || t("error.stream");
    }
    return formatWorkflowErrorPayload(payload, t("error.stream"));
  }

  function isAbortError(err: unknown): boolean {
    return isRecord(err) && err.name === "AbortError";
  }

  function stopExtraction() {
    if (!extractionAbortRef.current) return;
    setIsStopping(true);
    extractionAbortRef.current.abort();
  }

  async function extract(nextSourceUrl?: string, nextText?: string) {
    // nextText: run the streaming extraction on injected text (e.g. parsed
    // from file nodes linked to the Source panel) instead of current state.
    const runSourceUrl = nextText !== undefined ? "" : (nextSourceUrl ?? sourceUrl).trim();
    if (nextText !== undefined) {
      setText(nextText);
      setSourceUrl("");
      triggerCountryDetect("", nextText);
    } else if (nextSourceUrl !== undefined) {
      setSourceUrl(runSourceUrl);
      setText("");
      triggerCountryDetect(runSourceUrl, "");
    }

    setStatus("loading");
    setError("");
    setWarning("");
    setResponse(null);
    setFoundPdfs([]);
    setExtractionProgress({ current: 0, total: 0, phase: "" });
    setActiveKey(null);
    setDecisions({});
    setBatchProgress({ current: 0, total: 0, currentUrl: "" });
    const controller = new AbortController();
    extractionAbortRef.current = controller;

    try {
      await runExtractionStream({
        runSourceUrl,
        requestText: nextText !== undefined ? nextText : nextSourceUrl !== undefined ? "" : text,
        signal: controller.signal,
      });
      // Defensive terminal state: some stream endings (node_output without a
      // parseable 'done' payload) left status stuck on "loading" forever —
      // the Audit then shows "Extracting mappings…" for a run that finished.
      setStatus("ready");
    } catch (err) {
      if (isAbortError(err)) {
        setWarning(t("status.extractionStopped"));
        setStatus("ready");
        return;
      }
      setError(
        err instanceof Error ? err.message : t("error.extractionFailed"),
      );
      setResponse(null);
      setStatus("error");
    } finally {
      if (extractionAbortRef.current === controller) {
        extractionAbortRef.current = null;
      }
      setIsStopping(false);
      setExtractionProgress({ current: 0, total: 0, phase: "" });
    }
  }

  async function extractShortlist(urls: string[]) {
    const uniqueUrls = Array.from(
      new Set(urls.map((url) => url.trim()).filter(Boolean)),
    );
    if (!uniqueUrls.length) return;

    setStatus("loading");
    setError("");
    setWarning("");
    setResponse({ mappings: [], rejected: [], provider: "", source_text: "" });
    setFoundPdfs([]);
    setExtractionProgress({ current: 0, total: 0, phase: "" });
    setActiveKey(null);
    setDecisions({});
    setText("");
    setBatchProgress({
      current: 0,
      total: uniqueUrls.length,
      currentUrl: uniqueUrls[0] ?? "",
    });

    let accumulatedMappings: IndicatorMapping[] = [];
    let accumulatedRejected: RejectedExtraction[] = [];
    let accumulatedProvider = "";
    let accumulatedUsage: RunUsageSummary | null = null;
    // Per-URL runs use updateTextFromSource:false (each crawl would otherwise
    // stomp the panel). Collect every document's source_text into ONE blob so
    // the highlight viewer has text to show — `=== title ===` markers are the
    // page delimiters the SourceView pager splits on, one page per document.
    const sourcePages: { title: string; text: string }[] = [];
    const batchRunId = `shortlist-${Date.now()}`;
    const failedUrls: string[] = [];
    const controller = new AbortController();
    extractionAbortRef.current = controller;
    let stopped = false;

    for (const [index, url] of uniqueUrls.entries()) {
      setBatchProgress({
        current: index + 1,
        total: uniqueUrls.length,
        currentUrl: url,
      });
      setSourceUrl(url);
      triggerCountryDetect(url, "");

      try {
        const result = await runExtractionStream({
          runSourceUrl: url,
          requestText: "",
          baseMappings: accumulatedMappings,
          baseRejected: accumulatedRejected,
          updateTextFromSource: false,
          setReadyOnDone: false,
          signal: controller.signal,
        });
        accumulatedMappings = [...accumulatedMappings, ...result.mappings];
        accumulatedRejected = [...accumulatedRejected, ...result.rejected];
        accumulatedProvider = result.provider || accumulatedProvider;
        accumulatedUsage = mergeUsageSummaries(
          accumulatedUsage,
          result.usage,
          batchRunId,
        );
        // Keep the crawled source so the highlight viewer can display and
        // trace quotes for this document; concatenate progressively so text
        // appears as the batch advances.
        if (result.source_text) {
          sourcePages.push({ title: shortDocTitle(url), text: result.source_text });
          setText(
            uniqueUrls.length > 1
              ? sourcePages
                  .map((p) => `=== ${p.title} ===\n${p.text}`)
                  .join("\n\n")
              : sourcePages[0].text,
          );
        }
      } catch (err) {
        if (isAbortError(err)) {
          stopped = true;
          break;
        }
        const message =
          err instanceof Error ? err.message : t("error.extractionFailed");
        failedUrls.push(url);
        const rejectedItem: RejectedExtraction = {
          reason: `Shortlist extraction failed: ${message}`,
          chunk_preview: url,
          raw_output: { source_url: url },
        };
        accumulatedRejected = [...accumulatedRejected, rejectedItem];
        setWarning(
          `${failedUrls.length} shortlist URL(s) failed; continuing with the remaining candidates.`,
        );
        setResponse({
          mappings: accumulatedMappings,
          rejected: accumulatedRejected,
          provider: accumulatedProvider,
          source_text: "",
          usage: accumulatedUsage,
        });
      }
    }

    if (extractionAbortRef.current === controller) {
      extractionAbortRef.current = null;
    }
    setIsStopping(false);

    setResponse({
      mappings: accumulatedMappings,
      rejected: accumulatedRejected,
      provider: accumulatedProvider,
      source_text: "",
      usage: accumulatedUsage,
    });

    if (stopped) {
      setWarning(t("status.extractionStopped"));
      setStatus("ready");
    } else if (failedUrls.length === uniqueUrls.length) {
      setError(
        `All shortlist extractions failed (${failedUrls.length}/${uniqueUrls.length}).`,
      );
      setStatus("error");
    } else {
      if (failedUrls.length) {
        setWarning(
          `${failedUrls.length} of ${uniqueUrls.length} shortlist URL(s) failed; extracted the rest.`,
        );
      }
      setStatus("ready");
    }
    setBatchProgress({
      current: uniqueUrls.length,
      total: uniqueUrls.length,
      currentUrl: "",
    });
    setExtractionProgress({ current: 0, total: 0, phase: "" });
  }

  /** Upload one file to the ingest endpoint and return the cleaned response
      (no state changes — callers decide how to apply single/merged results). */
  async function requestFileIngest(file: File): Promise<ExtractionResponse> {
    const form = new FormData();
    form.append("file", file);

    // Unify Vertex AI under Gemini brand in frontend, and handle DeepSeek options
    let actualProvider = selectedProvider;
    let actualModel = "";
    if (selectedProvider === "ollama") {
      actualModel = selectedOllamaModel;
    } else if (selectedProvider === "gemini") {
      if (vertexModels.includes(selectedGeminiModel)) {
        actualProvider = "vertex-ai";
      }
      actualModel = selectedGeminiModel;
    } else if (selectedProvider === "deepseek") {
      actualModel = selectedDeepSeekModel;
    }

    form.append("provider", actualProvider);
    if (actualModel) {
      form.append("model", actualModel);
    }

    const res = await fetch(INGEST_API_URL, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });

    if (!res.ok) {
      throw new Error(
        await readErrorMessage(
          res,
          t("error.ingestFailedStatus", { status: res.status }),
        ),
      );
    }

    const data = (await res.json()) as ExtractionResponse;

    data.mappings = data.mappings.map((m: IndicatorMapping) => {
      const isHallucinatedUrl =
        !m.source_url ||
        m.source_url.toLowerCase().includes("n/a") ||
        m.source_url.toLowerCase().includes("not specified");
      const isHallucinatedDate =
        !m.last_update ||
        m.last_update.toLowerCase().includes("n/a") ||
        m.last_update.toLowerCase().includes("not specified");
      return {
        ...m,
        source_url: isHallucinatedUrl ? "" : m.source_url,
        last_update: isHallucinatedDate
          ? new Date().toISOString().split("T")[0]
          : m.last_update,
      };
    });
    return data;
  }

  async function ingestFile(file: File) {
    setStatus("loading");
    setError("");
    try {
      const data = await requestFileIngest(file);
      if (data.source_text) setText(data.source_text);
      setResponse(data);
      setActiveKey(null);
      setDecisions({});
      setStatus("ready");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("error.fileIngestFailed"),
      );
      setResponse(null);
      setStatus("error");
    }
  }

  /** Extract from several files (e.g. every file node linked to the Source
      panel). Runs sequentially and merges mappings/rejected into one
      response; source texts are joined with per-file headers. */
  async function ingestFiles(files: { file: File; label?: string }[]) {
    if (files.length === 0) return;
    if (files.length === 1) return ingestFile(files[0].file);
    setStatus("loading");
    setError("");
    try {
      let merged: ExtractionResponse | null = null;
      const texts: string[] = [];
      for (const { file, label } of files) {
        const data = await requestFileIngest(file);
        if (data.source_text) {
          texts.push(`=== ${label ?? file.name} ===\n${data.source_text}`);
        }
        merged = merged
          ? {
              ...data,
              mappings: [...merged.mappings, ...data.mappings],
              rejected: [...(merged.rejected ?? []), ...(data.rejected ?? [])],
            }
          : data;
      }
      if (!merged) return;
      if (texts.length) setText(texts.join("\n\n"));
      setResponse({ ...merged, source_text: texts.join("\n\n") });
      setActiveKey(null);
      setDecisions({});
      setStatus("ready");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("error.fileIngestFailed"),
      );
      setResponse(null);
      setStatus("error");
    }
  }

  function onTextChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    triggerCountryDetect(sourceUrl, e.target.value);
    if (response) {
      setResponse(null);
      setActiveKey(null);
      setStatus("idle");
    }
  }

  function handleSetSourceUrl(v: string) {
    setSourceUrl(v);
    triggerCountryDetect(v, text);
    // If the user points to a new URL, clear any previously crawled text so the
    // backend's "crawl if text is empty" path triggers correctly on the next run.
    if (v.trim()) {
      setText("");
      if (response) {
        setResponse(null);
        setActiveKey(null);
        setStatus("idle");
      }
    }
  }

  function selectMapping(key: string) {
    setActiveKey((prev) => (prev === key ? null : key));
  }

  function loadDemoAuditData() {
    const nextResponse = {
      ...demoAuditExtraction,
      mappings: demoAuditExtraction.mappings.map((mapping) => ({ ...mapping })),
      rejected: demoAuditExtraction.rejected.map((item) => ({ ...item })),
    };
    setCountry("SGP");
    setSourceUrl("https://sso.agc.gov.sg/Act/PDPA2012");
    setText(demoAuditExtraction.source_text ?? "");
    setResponse(nextResponse);
    setActiveKey(null);
    setDecisions({});
    setWarning("");
    setError("");
    setStatus("ready");
    setPillarFilter("all");
    setShowRejected(false);
  }

  async function setDecision(key: string, d: ReviewDecision) {
    const mapping = mappings.find((m) => mappingKey(m) === key);
    if (!mapping) return;

    setDecisions((prev) => ({ ...prev, [key]: d }));

    if (d === "pending") return;

    try {
      const res = await fetch(REVIEW_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ decision: d, country_code: country, mapping }),
      });

      if (!res.ok) {
        throw new Error(
          await readErrorMessage(res, t("error.reviewSaveFailed")),
        );
      }
    } catch (err) {
      console.error("Database sync error:", err);
      setError(err instanceof Error ? err.message : t("error.syncDbFailed"));
    }
  }

  return {
    country,
    setCountry,
    detectedCountry,
    warning,
    pillarFilter,
    setPillarFilter,
    sourceUrl,
    setSourceUrl: handleSetSourceUrl,
    text,
    onTextChange,
    status,
    error,
    provider,
    usage,
    isStopping,
    mappings,
    visibleMappings,
    rejected,
    activeKey,
    setActiveKey,
    activeMapping,
    decisions,
    pendingCount,
    showRejected,
    setShowRejected,
    availableProviders,
    selectedProvider,
    setSelectedProvider,
    ollamaModels,
    selectedOllamaModel,
    setSelectedOllamaModel,
    vertexModels,
    selectedGeminiModel,
    setSelectedGeminiModel,
    selectedDeepSeekModel,
    setSelectedDeepSeekModel,
    foundPdfs,
    extractionProgress,
    batchProgress,
    extract,
    stopExtraction,
    extractShortlist,
    ingestFile,
    ingestFiles,
    loadDemoAuditData,
    selectMapping,
    setDecision,
  };
}

/** Back-compat: the single default extraction thread (pre-multi-thread API). */
export function useExtraction() {
  return useExtractionThread(DEFAULT_THREAD_ID);
}
