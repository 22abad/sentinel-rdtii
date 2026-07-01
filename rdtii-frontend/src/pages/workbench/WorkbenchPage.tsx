import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuditPanel } from "../../components/AuditPanel";
import { DiscoveryPanel } from "../../components/Discovery/DiscoveryPanel";
import { DiscoverySourceManager } from "../../components/Discovery/DiscoverySourceManager";
import { SourcePanel } from "../../components/SourcePanel";
import { FoundPdfsPanel } from "../../components/SourcePanel/FoundPdfsPanel";
import { SideBar } from "../../components/SideBar";
import { useExtraction } from "../../hooks/useExtraction";
import { motion, AnimatePresence } from "motion/react";
import { Plus, Menu, X, Home, Map, User } from "lucide-react";
import { GooeyFilter } from "../../components/ui/gooey-filter";
import { t } from "../../lib/i18n";
import { WorkbenchCanvas, type CanvasPanel } from "./WorkbenchCanvas";
import { fetchSourceTextNode } from "../../services/workflowNodes";

export function WorkbenchPage() {
  const navigate = useNavigate();
  const sourceRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [fetchingPdf, setFetchingPdf] = useState(false);
  const [fetchPdfError, setFetchPdfError] = useState("");
  const {
    country, setCountry,
    detectedCountry,
    pillarFilter, setPillarFilter,
    sourceUrl, setSourceUrl,
    text, onTextChange,
    status,
    error,
    warning,
    provider,
    mappings,
    visibleMappings,
    rejected,
    activeKey, setActiveKey,
    activeMapping,
    decisions,
    pendingCount,
    showRejected, setShowRejected,
    availableProviders,
    selectedProvider, setSelectedProvider,
    ollamaModels, selectedOllamaModel, setSelectedOllamaModel,
    vertexModels,
    selectedGeminiModel, setSelectedGeminiModel,
    selectedDeepSeekModel, setSelectedDeepSeekModel,
    foundPdfs,
    extractionProgress,
    batchProgress,
    extract,
    extractShortlist,
    selectMapping,
    setDecision,
  } = useExtraction();

  useEffect(() => {
    if (!activeMapping || !sourceRef.current) return;
    const mark = sourceRef.current.querySelector("mark");
    if (mark) mark.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeKey, activeMapping]);

  const discoveryPanel = (
    <DiscoveryPanel
      country={country}
      pillarFilter={pillarFilter}
      extracting={status === "loading"}
      batchProgress={batchProgress}
      onUseCandidate={(candidate) => setSourceUrl(candidate.url)}
      onExtractCandidate={(candidate) => extract(candidate.url)}
      onExtractShortlist={(candidates) => extractShortlist(candidates.map((candidate) => candidate.url))}
    />
  );

  const sourceManagerPanel = <DiscoverySourceManager />;

  const sourcePanel = (
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
      extract={extract}
      status={status}
      error={error}
      warning={warning}
      extractionProgress={extractionProgress}
      availableProviders={availableProviders}
      selectedProvider={selectedProvider}
      setSelectedProvider={setSelectedProvider}
    />
  );

  const foundPdfsPanel =
    foundPdfs.length > 0 ? (
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
            }
          } catch (err) {
            setFetchPdfError(err instanceof Error ? err.message : "Failed to fetch PDF text.");
          } finally {
            setFetchingPdf(false);
          }
        }}
      />
    ) : null;

  const auditPanel = (
    <AuditPanel
      status={status}
      mappings={visibleMappings}
      totalMappings={mappings.length}
      activeKey={activeKey}
      decisions={decisions}
      selectMapping={selectMapping}
      setDecision={setDecision}
      rejected={rejected}
      showRejected={showRejected}
      setShowRejected={setShowRejected}
      country={country}
    />
  );

  const canvasPanels: CanvasPanel[] = [
    { id: "discovery", title: "Discovery", element: discoveryPanel, width: 800},
    { id: "sourceManager", title: "Source Manager", element: sourceManagerPanel, width: 760 },
    { id: "source", title: "Source", element: sourcePanel, width: 460 },
    ...(foundPdfsPanel ? [{ id: "foundPdfs", title: "Found PDFs", element: foundPdfsPanel, width: 420 }] : []),
    { id: "audit", title: "Audit", element: auditPanel, width: 520 },
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

      {/* The workbench is now the free-canvas — the classic stacked layout is retired */}
      <WorkbenchCanvas panels={canvasPanels} onExit={() => navigate("/")} />

    </div>
  );
}
