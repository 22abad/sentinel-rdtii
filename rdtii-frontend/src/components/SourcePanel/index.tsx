import type React from "react";
import { useCallback, useState, useEffect } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { IndicatorMapping, RunUsageSummary, Status } from "../../types";
import { SourceView } from "./SourceView";
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel,
  SelectTrigger, SelectValue, SelectSeparator,
} from "../ui/Select";
import { t } from "../../lib/i18n";
import { UsageSummary } from "../UsageSummary";

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  claude: "Claude",
  openai: "OpenAI",
  deepseek: "DeepSeek",
  groq: "Groq",
  mistral: "Mistral",
  together: "Together AI",
  openrouter: "OpenRouter",
  "llama-3-local": "Llama 3 (Local)",
};

type SourcePanelProps = {
  sourceRef: React.RefObject<HTMLDivElement>;
  country: string;
  setCountry: (v: string) => void;
  detectedCountry?: { code: string; name: string; detected: boolean } | null;
  pillarFilter: string;
  setPillarFilter: (v: string) => void;
  sourceUrl: string;
  setSourceUrl: (v: string) => void;
  text: string;
  onTextChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  activeMapping: IndicatorMapping | null;
  setActiveKey: (key: string | null) => void;
  extract: () => void;
  status: Status;
  error: string;
  warning?: string;
  extractionProgress?: { current: number; total: number; phase: string };
  availableProviders: string[];
  selectedProvider: string;
  setSelectedProvider: (v: string) => void;
  stopExtraction: () => void;
  isStopping?: boolean;
  usage?: RunUsageSummary | null;
};

function isValidUrl(v: string): boolean {
  try { return ["http:", "https:"].includes(new URL(v).protocol); } catch { return false; }
}

export function SourcePanel({
  sourceRef,
  country,
  setCountry,
  detectedCountry,
  pillarFilter,
  setPillarFilter,
  sourceUrl,
  setSourceUrl,
  text,
  onTextChange,
  activeMapping,
  setActiveKey,
  extract,
  status,
  error,
  warning,
  extractionProgress,
  availableProviders,
  selectedProvider,
  setSelectedProvider,
  stopExtraction,
  isStopping = false,
  usage,
}: SourcePanelProps) {
  const URL_PLACEHOLDERS = [
    "https://www.pdpc.gov.sg/Overview-of-PDPA/The-Legislation/Personal-Data-Protection-Act",
    "https://www.legislation.gov.au/Details/C2022A00010",
    "https://www.pip.org.ph/data-privacy-act/",
    "https://www.moj.gov.cn/pub/sfbcn/publicationData/dataPrivacy.html",
    "https://meity.gov.in/digital-personal-data-protection-act",
  ];

  const [urlPlaceholderIndex, setUrlPlaceholderIndex] = useState(0);
  const [showUrlPlaceholder, setShowUrlPlaceholder] = useState(true);
  const [urlFocused, setUrlFocused] = useState(false);

  useEffect(() => {
    if (urlFocused || sourceUrl) return;
    const interval = setInterval(() => {
      setShowUrlPlaceholder(false);
      setTimeout(() => {
        setUrlPlaceholderIndex((prev) => (prev + 1) % URL_PLACEHOLDERS.length);
        setShowUrlPlaceholder(true);
      }, 400);
    }, 3500);
    return () => clearInterval(interval);
  }, [urlFocused, sourceUrl]);

  const letterVariants = {
    initial: { opacity: 0, filter: "blur(8px)", y: 6 },
    animate: {
      opacity: 1, filter: "blur(0px)", y: 0,
      transition: { opacity: { duration: 0.2 }, filter: { duration: 0.3 }, y: { type: "spring" as const, stiffness: 80, damping: 20 } },
    },
    exit: {
      opacity: 0, filter: "blur(8px)", y: -6,
      transition: { opacity: { duration: 0.15 }, filter: { duration: 0.2 } },
    },
  };

  const textareaRef = useCallback((el: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);
  const extractionLabel =
    status === "loading" && extractionProgress?.total
      ? `${t("status.extracting")} ${extractionProgress.current}/${extractionProgress.total}`
      : status === "loading"
        ? sourceUrl && !text.trim() ? t("status.crawling") : t("status.extracting")
        : t("source.run");
  const stopLabel = extractionProgress?.total
    ? `${t("status.stop")} · ${extractionProgress.current}/${extractionProgress.total}`
    : t("status.stop");

  return (
    <section className="input-panel" aria-label={t("source.aria")}>
      <div className="panel-header">
        <div>
          <h2>{t("source.title")}</h2>
          <p>{t("source.description")}</p>
        </div>
        <button
          onClick={() => {
            if (status === "loading") {
              stopExtraction();
              return;
            }
            if (sourceUrl.trim() && !text.trim() && !isValidUrl(sourceUrl.trim())) return;
            extract();
          }}
          disabled={isStopping || (status !== "loading" && ((!text.trim() && !sourceUrl.trim()) || (!!sourceUrl.trim() && !text.trim() && !isValidUrl(sourceUrl.trim()))))}
          className={`nodrag group flex items-center justify-center rounded-full text-md h-10 px-6 cursor-pointer transition-all duration-300 text-white ${status === "loading" ? "bg-rose-500 hover:bg-rose-600" : "bg-[#10B981]"}`}
          style={{ minHeight: 0, border: "none" }}
        >
          <span>
            {status === "loading"
              ? isStopping ? t("status.stopping") : stopLabel
              : extractionLabel}
          </span>
          {status === "loading" ? (
            <span className="ml-2 inline-block h-2.5 w-2.5 rounded-[2px] bg-white" aria-hidden="true" />
          ) : (
            <span className="overflow-hidden w-0 group-hover:w-4 transition-all duration-300 flex items-center justify-center">
              <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 17L17 7M17 7H7M17 7V17" />
              </svg>
            </span>
          )}
        </button>
      </div>

      {status === "loading" && (
        <div className="border-b border-gray-100 px-6 py-2.5 bg-gray-50/70">
          {usage ? (
            <UsageSummary usage={usage} />
          ) : (
            <p className="text-[11px] text-gray-400">
              {t("status.usagePending")}
            </p>
          )}
        </div>
      )}

      <div className="control-grid">
        <label>
          {t("source.country")}
          {detectedCountry?.detected ? (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1 text-sm font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                {detectedCountry.name}
                <span className="text-emerald-400 text-xs">({detectedCountry.code})</span>
              </span>
              <small
                className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 underline underline-offset-2"
                onClick={() => setCountry("")}
              >
                {t("source.change")}
              </small>
            </div>
          ) : (
            <Select value={country} onValueChange={setCountry}>
              <SelectTrigger><SelectValue placeholder={t("source.autoDetect")} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="CHN">{t("country.chn")}</SelectItem>
                <SelectItem value="SGP">{t("country.sgp")}</SelectItem>
                <SelectItem value="MYS">{t("country.mys")}</SelectItem>
                <SelectItem value="THA">{t("country.tha")}</SelectItem>
              </SelectContent>
            </Select>
          )}
        </label>
        <label>
          {t("source.filter")}
          <Select value={pillarFilter} onValueChange={setPillarFilter}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("taxonomy.allPillars")}</SelectItem>
              <SelectSeparator />
              <SelectGroup>
                <SelectLabel>{t("taxonomy.pillar")}</SelectLabel>
                <SelectItem value="1">{t("taxonomy.p1")}</SelectItem>
                <SelectItem value="2">{t("taxonomy.p2")}</SelectItem>
                <SelectItem value="3">{t("taxonomy.p3")}</SelectItem>
                <SelectItem value="4">{t("taxonomy.p4")}</SelectItem>
                <SelectItem value="5">{t("taxonomy.p5")}</SelectItem>
                <SelectItem value="6">{t("taxonomy.p6")}</SelectItem>
                <SelectItem value="7">{t("taxonomy.p7")}</SelectItem>
                <SelectItem value="8">{t("taxonomy.p8")}</SelectItem>
                <SelectItem value="9">{t("taxonomy.p9")}</SelectItem>
                <SelectItem value="10">{t("taxonomy.p10")}</SelectItem>
                <SelectItem value="11">{t("taxonomy.p11")}</SelectItem>
                <SelectItem value="12">{t("taxonomy.p12")}</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </label>
      </div>

      {availableProviders.length > 0 && (
        <div className="stacked">
          <label style={{ display: "block" }}>
            {t("source.aiProvider")}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
              {availableProviders.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setSelectedProvider(p)}
                  className={selectedProvider === p ? "" : "secondary"}
                  style={{ minHeight: 32, padding: "0 14px", fontSize: "0.82rem", borderRadius: 9999 }}
                >
                  {PROVIDER_LABELS[p] ?? p}
                </button>
              ))}
            </div>
          </label>
        </div>
      )}

      <label className="stacked">
        {t("source.sourceUrl")}
        <div style={{ position: "relative" }}>
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            onFocus={() => setUrlFocused(true)}
            onBlur={() => setUrlFocused(false)}
            style={{ position: "relative", zIndex: 1, background: "transparent", fontWeight: "normal" }}
          />
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", padding: "0 12px", pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
            <AnimatePresence mode="wait">
              {showUrlPlaceholder && !urlFocused && !sourceUrl && (
                <motion.span
                  key={urlPlaceholderIndex}
                  style={{ position: "absolute", whiteSpace: "nowrap", color: "#9ca3af", fontSize: "0.92rem", display: "flex", fontWeight: "normal" }}
                  initial={{}}
                  animate={{ transition: { staggerChildren: 0.018 } }}
                  exit={{ transition: { staggerChildren: 0.01, staggerDirection: -1 } }}
                >
                  {URL_PLACEHOLDERS[urlPlaceholderIndex].split("").map((char, i) => (
                    <motion.span key={i} variants={letterVariants} initial="initial" animate="animate" exit="exit" style={{ display: "inline-block" }}>
                      {char === " " ? "\u00A0" : char}
                    </motion.span>
                  ))}
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>
      </label>

      <div className="stacked text-area-label">
        <div className="source-bar">
          <span>
            {activeMapping
              ? t("source.auditHighlight")
              : t("source.sourceText")}
          </span>
        </div>

        {activeMapping ? (
          <SourceView
            text={text}
            activeMapping={activeMapping}
            sourceRef={sourceRef}
            onClick={() => setActiveKey(null)}
          />
        ) : (
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              e.target.style.height = "auto";
              e.target.style.height = `${e.target.scrollHeight}px`;
              onTextChange(e);
            }}
            placeholder={t("source.placeholder")}
          />
        )}
      </div>

      {warning && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
          ⚠ {warning}
        </p>
      )}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
