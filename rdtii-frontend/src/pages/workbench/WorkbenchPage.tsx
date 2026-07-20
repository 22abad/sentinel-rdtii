import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuditPanel } from "../../components/AuditPanel";
import { DiscoveryPanel } from "../../components/Discovery/DiscoveryPanel";
import { SourcePanel } from "../../components/SourcePanel";
import { FoundPdfsPanel } from "../../components/SourcePanel/FoundPdfsPanel";
import { SideBar } from "../../components/SideBar";
import { useExtractionThread } from "../../hooks/useExtraction";
import { PanelLinkGuard } from "../../components/Canvas/PanelLinkGuard";
import { motion, AnimatePresence } from "motion/react";
import { Plus, Menu, X, Home, Map, User, LayoutDashboard } from "lucide-react";
import { GooeyFilter } from "../../components/ui/gooey-filter";
import { t } from "../../lib/i18n";
import { WorkbenchCanvas, type CanvasPanel, type CanvasGraph, type LinkedFile, type WorkbenchCanvasApi } from "./WorkbenchCanvas";
import { fetchSourceTextNode } from "../../services/workflowNodes";
import { parseFile, uploadCanvasFile } from "../../services/canvasFiles";
import { DocumentsPanel } from "../../components/Workbench/DocumentsPanel";
import { useAuth } from "../../hooks/useAuth";

/** The original Source panel's node id doubles as the "main" thread id —
    Discovery, Found PDFs, and the SideBar pin to it. Source copies get their
    own thread keyed by their node id. */
const MAIN_THREAD_ID = "source";

/** One Source panel instance bound to its own extraction thread. */
function SourceThreadPanel({ threadId, linkedFiles, autoRunToken }: { threadId: string; linkedFiles: LinkedFile[]; autoRunToken?: number }) {
  const {
    country, setCountry,
    detectedCountry,
    pillarFilter, setPillarFilter,
    sourceUrl, setSourceUrl,
    text, onTextChange,
    activeKey, activeMapping, setActiveKey,
    status, error, warning,
    extractionProgress,
    availableProviders,
    selectedProvider, setSelectedProvider,
    stopExtraction, isStopping, usage,
    extract,
  } = useExtractionThread(threadId);
  const sourceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!activeMapping || !sourceRef.current) return;
    // rAF: let the highlight <mark> paint before we scroll to it. Instant
    // (not smooth): on a long statute the quote can be thousands of px down,
    // and a smooth animation over that distance reads as "nothing happened".
    const container = sourceRef.current;
    const raf = requestAnimationFrame(() => {
      const mark = container.querySelector("mark");
      mark?.scrollIntoView({ block: "center", behavior: "auto" });
    });
    return () => cancelAnimationFrame(raf);
  }, [activeKey, activeMapping]);

  // Run: prefer explicit text/URL; otherwise parse every linked file node to
  // text and feed it through the normal streaming extraction.
  const runExtraction = useCallback(() => {
    if (text.trim() || sourceUrl.trim() || linkedFiles.length === 0) {
      extract();
      return;
    }
    void (async () => {
      try {
        const parts = await Promise.all(
          linkedFiles
            .filter((l) => l.previewUrl)
            .map(async (l) => {
              const blob = await fetch(l.previewUrl as string).then((r) => r.blob());
              const file = new File([blob], l.fileName ?? "upload", { type: blob.type });
              const { text: parsed } = await parseFile(file);
              return linkedFiles.length > 1 ? `=== ${l.fileName ?? "file"} ===\n${parsed}` : parsed;
            }),
        );
        await extract(undefined, parts.join("\n\n"));
      } catch (err) {
        console.error("Linked-file extraction failed:", err);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, sourceUrl, linkedFiles, extract]);

  // One-click file pipeline: PREPARE, don't run — extraction bills, so it
  // must never start silently. EXTRACT = parse the file(s) into the thread
  // text + detect the jurisdiction explicitly (auto-applied; correct it if
  // wrong) + ingest into the knowledge base so Documents/RAG see the file.
  // The analyst reviews country/filter, then presses Run.
  const consumedAutoRun = useRef(0);
  useEffect(() => {
    if (!autoRunToken || autoRunToken === consumedAutoRun.current) return;
    if (linkedFiles.length === 0) return;
    consumedAutoRun.current = autoRunToken;
    void (async () => {
      try {
        const fileObjs = await Promise.all(
          linkedFiles
            .filter((l) => l.previewUrl)
            .map(async (l) => {
              const blob = await fetch(l.previewUrl as string).then((r) => r.blob());
              return new File([blob], l.fileName ?? "upload", { type: blob.type });
            }),
        );
        // One file failing to parse (oversized upload, image-only scan, …)
        // must not kill the whole prepare — detection can still work from
        // the filename, and extraction can OCR server-side.
        const parts = await Promise.all(
          fileObjs.map(async (file) => {
            try {
              const { text: parsed } = await parseFile(file);
              return fileObjs.length > 1 ? `=== ${file.name} ===\n${parsed}` : parsed;
            } catch (err) {
              console.warn(`Parse failed for ${file.name}; continuing with filename-only detection:`, err);
              return "";
            }
          }),
        );
        const combined = parts.join("\n\n");
        onTextChange({
          target: { value: combined },
        } as React.ChangeEvent<HTMLTextAreaElement>);

        // Deterministic detection on the parsed text — no debounce races.
        // The filename rides along so image-only scans (which parse to no
        // text until server-side OCR) still detect from names like "MYS_….pdf".
        let detectedCode = "";
        try {
          const res = await fetch("/api/detect/country", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: combined.slice(0, 3000),
              filename: fileObjs.map((f) => f.name).join(" "),
            }),
          });
          if (res.ok) {
            const data = await res.json();
            if (data.detected && data.code) {
              detectedCode = data.code;
              setCountry(data.code);
            }
          }
        } catch { /* detection is best-effort */ }

        // Best-effort knowledge-base ingest (Documents refreshes live via the
        // documents-changed event; 401 just means not signed in — skip).
        for (const file of fileObjs) {
          uploadCanvasFile(file, detectedCode || undefined).catch((err) =>
            console.warn("Knowledge-base ingest skipped:", err),
          );
        }
      } catch (err) {
        console.error("Linked-file prepare failed:", err);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRunToken, linkedFiles.length]);

  return (
    <SourcePanel
      sourceRef={sourceRef}
      country={country}
      setCountry={setCountry}
      detectedCountry={detectedCountry}
      pillarFilter={pillarFilter}
      setPillarFilter={setPillarFilter}
      sourceUrl={sourceUrl}
      setSourceUrl={setSourceUrl}
      text={text}
      onTextChange={onTextChange}
      activeMapping={activeMapping}
      setActiveKey={setActiveKey}
      extract={runExtraction}
      linkedSourceCount={linkedFiles.length}
      status={status}
      error={error}
      warning={warning}
      extractionProgress={extractionProgress}
      availableProviders={availableProviders}
      selectedProvider={selectedProvider}
      setSelectedProvider={setSelectedProvider}
      stopExtraction={stopExtraction}
      isStopping={isStopping}
      usage={usage}
    />
  );
}

/** One Audit panel instance showing the thread of the Source it is
    edge-bound to; unwired instances render the disconnected guard. */
function AuditThreadPanel({ threadId }: { threadId: string | null }) {
  // Hooks must run unconditionally — unbound panels read a placeholder
  // thread (always empty) underneath the guard.
  const {
    status,
    mappings, visibleMappings, rejected,
    activeKey, decisions,
    selectMapping, setDecision,
    showRejected, setShowRejected,
    country, loadDemoAuditData, usage,
  } = useExtractionThread(threadId ?? "__unbound__");

  const panel = (
    <AuditPanel
      status={status}
      mappings={visibleMappings}
      exportMappings={mappings}
      totalMappings={mappings.length}
      activeKey={activeKey}
      decisions={decisions}
      selectMapping={selectMapping}
      setDecision={setDecision}
      rejected={rejected}
      showRejected={showRejected}
      setShowRejected={setShowRejected}
      country={country}
      onLoadDemoData={loadDemoAuditData}
      usage={usage}
    />
  );
  if (threadId) return panel;
  return (
    <PanelLinkGuard connected={false} upstreamLabel="Source" panelLabel="Audit">
      {panel}
    </PanelLinkGuard>
  );
}

/** Discovery drives the main thread (candidate URLs → main Source). */
function DiscoveryThreadPanel({ onExtractIntent }: { onExtractIntent?: () => void }) {
  const { country, pillarFilter, status, batchProgress, setSourceUrl, extract, extractShortlist } =
    useExtractionThread(MAIN_THREAD_ID);
  return (
    <DiscoveryPanel
      country={country}
      pillarFilter={pillarFilter}
      extracting={status === "loading"}
      batchProgress={batchProgress}
      onUseCandidate={(candidate) => {
        onExtractIntent?.();
        setSourceUrl(candidate.url);
      }}
      onExtractCandidate={(candidate) => {
        onExtractIntent?.();
        extract(candidate.url);
      }}
      onExtractShortlist={(candidates) => {
        onExtractIntent?.();
        extractShortlist(candidates.map((candidate) => candidate.url));
      }}
    />
  );
}

/** Found PDFs feed the main thread's source text. */
function FoundPdfsThreadPanel() {
  const { foundPdfs, setSourceUrl, onTextChange } = useExtractionThread(MAIN_THREAD_ID);
  const [fetchingPdf, setFetchingPdf] = useState(false);
  const [fetchPdfError, setFetchPdfError] = useState("");
  return (
    <FoundPdfsPanel
      urls={foundPdfs}
      loading={fetchingPdf}
      error={fetchPdfError}
      onSelect={async (url) => {
        setFetchingPdf(true);
        setFetchPdfError("");
        try {
          const fetchedDocument = await fetchSourceTextNode(url);
          if (fetchedDocument.text) {
            setSourceUrl(url);
            onTextChange({ target: { value: fetchedDocument.text } } as React.ChangeEvent<HTMLTextAreaElement>);
            if (fetchedDocument.quality && !fetchedDocument.quality.should_extract) {
              setFetchPdfError(
                [
                  `Crawl quality: ${fetchedDocument.quality.status}`,
                  ...fetchedDocument.quality.warnings,
                ].join(" · "),
              );
            }
          }
        } catch (err) {
          setFetchPdfError(err instanceof Error ? err.message : "Failed to fetch PDF text.");
        } finally {
          setFetchingPdf(false);
        }
      }}
    />
  );
}

export function WorkbenchPage() {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { user } = useAuth();
  const [shareHint, setShareHint] = useState(false);

  // Canvas (multi-thread, free layout) vs classic (traditional stacked view
  // of the main thread). Both render the same thread components against the
  // shared store, so switching preserves all state — even mid-extraction.
  // Classic is ALWAYS the landing view; canvas is a per-visit mode
  // (deliberately not persisted — leaving and returning resets to classic).
  const [viewMode, setViewMode] = useState<"canvas" | "classic">("classic");
  const switchView = setViewMode;

  // Main-thread view for the page furniture (SideBar, Found PDFs presence).
  const {
    country,
    provider,
    status,
    mappings,
    pendingCount,
    sourceUrl,
    availableProviders,
    selectedProvider, setSelectedProvider,
    ollamaModels, selectedOllamaModel, setSelectedOllamaModel,
    vertexModels,
    selectedGeminiModel, setSelectedGeminiModel,
    selectedDeepSeekModel, setSelectedDeepSeekModel,
    foundPdfs,
  } = useExtractionThread(MAIN_THREAD_ID);

  // Data-wire graph from the canvas: file nodes per panel instance + which
  // Source instance each Audit instance is bound to.
  const [graph, setGraph] = useState<CanvasGraph>({ filesByInstance: {}, bindings: {} });
  const handleGraphChange = useCallback((next: CanvasGraph) => {
    // Content-compare so unchanged reports don't re-render (and re-trigger
    // the canvas effect) forever.
    setGraph((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
  }, []);

  // Canvas imperative handle: Discovery's Extract auto-reveals + wires the
  // Extract → Audit pipeline so streamed results always land somewhere visible.
  const canvasApiRef = useRef<WorkbenchCanvasApi | null>(null);

  // File-node Extract buttons: instance id -> monotonically increasing token;
  // the matching SourceThreadPanel auto-runs when its wire lands.
  const [autoRunTokens, setAutoRunTokens] = useState<Record<string, number>>({});
  const handleFileExtract = useCallback((_fileId: string, instanceId: string) => {
    setAutoRunTokens((prev) => ({ ...prev, [instanceId]: (prev[instanceId] ?? 0) + 1 }));
  }, []);

  const canvasPanels: CanvasPanel[] = [
    {
      id: "discovery",
      title: "Discovery",
      element: (
        <DiscoveryThreadPanel
          onExtractIntent={() => canvasApiRef.current?.revealExtractPipeline()}
        />
      ),
      width: 800,
      dragHandle: ".wb-drag-strip, .panel-header",
      flat: true,
    },
    {
      id: "source",
      title: "Extract",
      renderElement: (instanceId) => (
        <SourceThreadPanel
          key={instanceId}
          threadId={instanceId}
          linkedFiles={graph.filesByInstance[instanceId] ?? []}
          autoRunToken={autoRunTokens[instanceId]}
        />
      ),
      width: 460,
      dragHandle: ".wb-drag-strip, .panel-header",
      flat: true,
    },
    ...(foundPdfs.length > 0
      ? [{ id: "foundPdfs", title: "Found PDFs", element: <FoundPdfsThreadPanel />, width: 420 }]
      : []),
    {
      id: "audit",
      title: "Audit",
      renderElement: (instanceId) => (
        <AuditThreadPanel key={instanceId} threadId={graph.bindings[instanceId] ?? null} />
      ),
      width: 520,
      dragHandle: ".wb-drag-strip, .panel-header",
      upstreamId: "source",
      flat: true,
    },
    { id: "documents", title: "Documents", element: <DocumentsPanel />, width: 420, dragHandle: ".wb-drag-strip, .panel-header", flat: true },
  ];

  return (
    <div className="flex overflow-hidden" style={{ height: "100dvh" }}>

      <div
        className="fixed inset-0 -z-10"
        style={{ height: "100dvh", background: "linear-gradient(160deg, #0d3326, #072418)" }}
      />
      <div className="fixed inset-0 -z-10 bg-black/20" style={{ height: "100dvh" }} />

      {/* Left sidebar — overlay drawer */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              key="sidebar-backdrop"
              className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              onClick={() => setSidebarOpen(false)}
            />
            <motion.div
              key="sidebar"
              className="fixed left-0 top-0 bottom-0 z-50"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 32 }}
              style={{ overflow: "hidden" }}
            >
              <SideBar
                country={country}
                provider={provider}
                status={status}
                mappingsCount={mappings.length}
                pendingCount={pendingCount}
                sourceUrl={sourceUrl}
                availableProviders={availableProviders}
                selectedProvider={selectedProvider}
                setSelectedProvider={setSelectedProvider}
                ollamaModels={ollamaModels}
                selectedOllamaModel={selectedOllamaModel}
                setSelectedOllamaModel={setSelectedOllamaModel}
                vertexModels={vertexModels}
                selectedGeminiModel={selectedGeminiModel}
                setSelectedGeminiModel={setSelectedGeminiModel}
                selectedDeepSeekModel={selectedDeepSeekModel}
                setSelectedDeepSeekModel={setSelectedDeepSeekModel}
                onClose={() => setSidebarOpen(false)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Sidebar toggle button */}
      {!sidebarOpen && (
        <div className="fixed left-4 top-4 w-12 h-12 z-50 group">
          <button
            onClick={() => setSidebarOpen(true)}
            title={t("nav.openSidebar")}
            className="hidden md:flex opacity-60 hover:opacity-100 hover:scale-105 transition-all duration-200 shadow-md hover:shadow-lg"
            style={{ width: 48, height: 48, minHeight: 0, borderRadius: "50%", background: "#0c1210", border: "1px solid rgba(255,255,255,0.15)", color: "white", cursor: "pointer", alignItems: "center", justifyContent: "center", padding: 0 }}
          >
            <Plus size={20} color="white" />
          </button>
          <button
            onClick={() => setSidebarOpen(true)}
            title={t("nav.openSidebar")}
            className="flex md:hidden"
            style={{ width: 48, height: 48, minHeight: 0, background: "transparent", border: "none", color: "white", cursor: "pointer", alignItems: "center", justifyContent: "center", padding: 0 }}
          >
            <Plus size={22} color="white" strokeWidth={1.5} />
          </button>
        </div>
      )}

      {/* Gooey Nav Menu */}
      <GooeyFilter id="gooey-nav-menu" strength={5} />
      <div
        className="fixed top-4 right-4 z-50"
        style={{ filter: "url(#gooey-nav-menu)" }}
      >
        <AnimatePresence>
          {menuOpen && [
            { icon: Home, key: "home", onClick: () => { setMenuOpen(false); navigate("/"); } },
            { icon: Map, key: "workbench", onClick: () => { setMenuOpen(false); navigate("/mapsearch"); } },
            { icon: User, key: "profile", onClick: () => {} },
          ].map((item, i) => {
            const Icon = item.icon;
            return (
              <motion.button
                key={item.key}
                className="absolute w-12 h-12 rounded-full flex items-center justify-center"
                style={{ right: 0, top: 0 }}
                initial={{ x: 0, opacity: 0 }}
                animate={{ y: (i + 1) * 46, opacity: 1 }}
                exit={{ y: 0, opacity: 0, transition: { delay: (3 - i) * 0.04, duration: 0.3, type: "spring", bounce: 0 } }}
                transition={{ delay: i * 0.04, duration: 0.35, type: "spring", bounce: 0 }}
                onClick={item.onClick}
              >
                <div className="absolute inset-0 rounded-full" style={{ background: "#1a2e26" }} />
                <motion.div
                  className="relative z-10"
                  key={item.key}
                  initial={{ opacity: 0, filter: "blur(10px)" }}
                  animate={{ opacity: 0.7, filter: "blur(0px)" }}
                  whileHover={{ opacity: 1 }}
                  exit={{ opacity: 0, filter: "blur(10px)" }}
                  transition={{ delay: i * 0.04, duration: 0.15 }}
                >
                  <Icon size={18} color="white" />
                </motion.div>
              </motion.button>
            );
          })}
        </AnimatePresence>

        <motion.button
          className="relative w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: "#1a2e26" }}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <AnimatePresence mode="wait">
            {menuOpen ? (
              <motion.div
                key="close"
                initial={{ opacity: 0, filter: "blur(10px)" }}
                animate={{ opacity: 0.7, filter: "blur(0px)" }}
                whileHover={{ opacity: 1 }}
                exit={{ opacity: 0, filter: "blur(10px)" }}
                transition={{ duration: 0.15 }}
              >
                <X size={18} className="text-white" />
              </motion.div>
            ) : (
              <motion.div
                key="menu"
                initial={{ opacity: 0, filter: "blur(10px)" }}
                animate={{ opacity: 0.7, filter: "blur(0px)" }}
                whileHover={{ opacity: 1 }}
                exit={{ opacity: 0, filter: "blur(10px)" }}
                transition={{ duration: 0.15 }}
              >
                <Menu size={18} className="text-white" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>
      </div>

      {/* Figma-style collaboration bar (dummy) — avatar + Share, left of the nav circle */}
      {viewMode === "canvas" && (
        <div
          className="fixed z-50 flex items-center gap-2"
          style={{ top: 22, right: 76 }}
        >
          <div
            title={user?.username ?? "Not signed in"}
            style={{
              width: 34,
              height: 34,
              borderRadius: 0,
              background: "#f3f1ea",
              color: "#111827",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "0.8rem",
              fontWeight: 800,
              border: "1.5px solid #111827",
              boxShadow: "none",
              textTransform: "uppercase",
              fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
            }}
          >
            {(user?.username ?? "?").slice(0, 1)}
          </div>
          <div style={{ position: "relative" }}>
            <motion.button
              type="button"
              onClick={() => {
                setShareHint(true);
                window.setTimeout(() => setShareHint(false), 2000);
              }}
              whileHover={{ scale: 1.04, y: -1 }}
              whileTap={{ scale: 0.96 }}
              transition={{ type: "spring", stiffness: 320, damping: 22 }}
              style={{
                minHeight: 0,
                padding: "8px 18px",
                borderRadius: 0,
                border: "1.5px solid #111827",
                background: "#111827",
                color: "#f3f1ea",
                fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
                fontSize: "0.7rem",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                cursor: "pointer",
                boxShadow: "none",
              }}
            >
              Share
            </motion.button>
            <AnimatePresence>
              {shareHint && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  style={{
                    position: "absolute",
                    top: "calc(100% + 8px)",
                    right: 0,
                    padding: "6px 12px",
                    borderRadius: 0,
                    background: "#111827",
                    color: "#f3f1ea",
                    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
                    fontSize: "0.68rem",
                    whiteSpace: "nowrap",
                    boxShadow: "none",
                  }}
                >
                  Canvas sharing is coming soon ✨
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Canvas (multi-thread) or classic stacked view — user's choice */}
      {viewMode === "canvas" ? (
        <WorkbenchCanvas
          panels={canvasPanels}
          onExit={() => navigate("/")}
          onSwitchView={() => switchView("classic")}
          onGraphChange={handleGraphChange}
          apiRef={canvasApiRef}
          onFileExtract={handleFileExtract}
        />
      ) : (
        <>
          {/* White dot-grid backdrop — matches the canvas page's background */}
          <div
            className="fixed inset-0"
            style={{
              zIndex: 0,
              background: "#ffffff",
              backgroundImage: "radial-gradient(#c2c8d0 1.5px, transparent 1.5px)",
              backgroundSize: "28px 28px",
            }}
          />
        <main className="workbench-classic flex-1 overflow-auto" style={{ position: "relative", zIndex: 1 }}>
          <section className="workspace">
            <div className="flex flex-col gap-4 min-w-0 self-start">
              <DiscoveryThreadPanel />
              <SourceThreadPanel threadId={MAIN_THREAD_ID} linkedFiles={[]} />
              {foundPdfs.length > 0 && <FoundPdfsThreadPanel />}
            </div>
            <div className="workspace-audit-side flex flex-col gap-4 min-w-0">
              <AuditThreadPanel threadId={MAIN_THREAD_ID} />
            </div>
          </section>

          {/* Switch back to the canvas — mirrors the canvas toolbar position */}
          <div className="fixed bottom-6 left-0 right-0 z-40 flex justify-center pointer-events-none">
            <motion.button
              onClick={() => switchView("canvas")}
              className="pointer-events-auto flex items-center gap-2"
              title="Switch to the canvas layout"
              whileHover={{ scale: 1.04, y: -1 }}
              whileTap={{ scale: 0.96, y: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 22 }}
              style={{
                minHeight: 0,
                padding: "8px 16px",
                borderRadius: 0,
                border: "2px solid #111827",
                background: "#f3f1ea",
                color: "#111827",
                fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
                fontSize: "0.7rem",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                cursor: "pointer",
                boxShadow: "none",
              }}
            >
              <LayoutDashboard size={15} /> Canvas
            </motion.button>
          </div>
        </main>
        </>
      )}

    </div>
  );
}
