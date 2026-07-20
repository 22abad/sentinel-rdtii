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
  ollama: "Ollama (local · no key)",
  "llama-3-local": "Llama 3 (Local)",
};

// Swiss/flat dropdown popup: square cream sheet, black frame, mono items,
// width pinned to the trigger (see .swiss-dropdown in styles.css — the popup
// is portaled to <body>, so it can't inherit from .swiss-form).
const SQUARE_DROPDOWN = "swiss-dropdown";

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
  /** File nodes edge-linked to this panel on the canvas — count as available
      sources, so Run enables even with empty text/URL. */
  linkedSourceCount?: number;
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
  linkedSourceCount = 0,
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
  const [collapsed, setCollapsed] = useState(false);

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

  // Title block doubles as a progress bar during extraction: yellow fills the
  // header from the left up to current/total (full header = done).
  const progressPct =
    status === "loading"
      ? extractionProgress?.total
        ? Math.min(
            100,
            Math.round((extractionProgress.current / extractionProgress.total) * 100),
          )
        : 4 // stream started, total unknown yet — show a starting sliver
      : null;

  return (
    <section className="input-panel swiss-form" aria-label={t("source.aria")}>
      <div className="panel-header">
        <div>
          <h2>{t("source.title")}</h2>
          <p>{t("source.description")}</p>
        </div>
        <button
          type="button"
          className="panel-collapse nodrag"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand panel" : "Collapse panel"}
        >
          {collapsed ? "▸" : "▾"}
        </button>
        {/* Progress sweep: a black fill clipped to current/total; it carries an
            inverted (cream) copy of the title, so letters flip color exactly
            where the black covers them. */}
        {progressPct !== null && (
          <div
            className="panel-progress"
            aria-hidden="true"
            style={{ clipPath: `inset(0 ${100 - progressPct}% 0 0)` }}
          >
            <h2>{t("source.title")}</h2>
          </div>
        )}
      </div>
      {!collapsed && (
        <>

      {status === "loading" && (
        <div className="border-t-[1.5px] border-[#111827] bg-transparent px-[18px] py-2.5">
          {usage ? (
            <UsageSummary usage={usage} />
          ) : (
            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-[#6b675c]">
              {t("status.usagePending")}
            </p>
          )}
        </div>
      )}

      <div className="control-grid">
        <label>
          {t("source.country")}
          {/* Auto-detection simply selects the detected country in the same
              dropdown — no separate tag UI. Picking manually overrides it. */}
          <Select
            value={country || (detectedCountry?.detected ? detectedCountry.code : "")}
            onValueChange={setCountry}
          >
            <SelectTrigger><SelectValue placeholder={t("source.autoDetect")} /></SelectTrigger>
            <SelectContent className={SQUARE_DROPDOWN}>
              <SelectItem value="SGP">{t("country.sgp")}</SelectItem>
              <SelectItem value="MYS">{t("country.mys")}</SelectItem>
              <SelectItem value="AUS">{t("country.aus")}</SelectItem>
              <SelectItem value="CHN">{t("country.chn")}</SelectItem>
              <SelectItem value="THA">{t("country.tha")}</SelectItem>
              {detectedCountry?.detected &&
                !["SGP", "MYS", "AUS", "CHN", "THA"].includes(detectedCountry.code) && (
                  <SelectItem value={detectedCountry.code}>
                    {detectedCountry.name}
                  </SelectItem>
                )}
            </SelectContent>
          </Select>
        </label>
        <label>
          {t("source.filter")}
          <Select value={pillarFilter} onValueChange={setPillarFilter}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent className={SQUARE_DROPDOWN}>
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
        <label className="stacked" style={{ display: "block" }}>
          {t("source.aiProvider")}
          <Select value={selectedProvider} onValueChange={setSelectedProvider}>
            <SelectTrigger>
              <SelectValue placeholder={t("source.aiProvider")} />
            </SelectTrigger>
            <SelectContent className={SQUARE_DROPDOWN}>
              {availableProviders.map((p) => (
                <SelectItem key={p} value={p}>
                  {PROVIDER_LABELS[p] ?? p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
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
        {activeMapping ? (
          <SourceView
            title={t("source.auditHighlight")}
            text={text}
            activeMapping={activeMapping}
            sourceRef={sourceRef}
            onClick={() => setActiveKey(null)}
          />
        ) : (
          <>
            <div className="source-bar">
              <span>{t("source.sourceText")}</span>
            </div>
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
          </>
        )}
      </div>

      {warning && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
          ⚠ {warning}
        </p>
      )}
      {error ? <p className="error">{error}</p> : null}

      <button
        onClick={() => {
          if (status === "loading") {
            stopExtraction();
            return;
          }
          if (sourceUrl.trim() && !text.trim() && !isValidUrl(sourceUrl.trim())) return;
          extract();
        }}
        disabled={isStopping || (status !== "loading" && ((!text.trim() && !sourceUrl.trim() && linkedSourceCount === 0) || (!!sourceUrl.trim() && !text.trim() && !isValidUrl(sourceUrl.trim()))))}
        className={`source-send nodrag group flex w-full items-center justify-center gap-3 h-14 cursor-pointer uppercase tracking-[0.2em] font-bold text-white transition-all duration-300 ${status === "loading" ? "bg-rose-500 hover:bg-rose-600" : "bg-[#111827] hover:bg-black"}`}
        style={{ minHeight: 0, border: "none" }}
      >
        <span>
          {status === "loading"
            ? isStopping ? t("status.stopping") : stopLabel
            : extractionLabel}
        </span>
        {status === "loading" ? (
          <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-white" aria-hidden="true" />
        ) : (
          <svg className="w-5 h-5 shrink-0 transition-transform duration-300 group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        )}
      </button>
        </>
      )}
    </section>
  );
}
