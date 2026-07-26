import { useState, useEffect, useRef } from "react";
import { MessageSquarePlus, Mic, Globe, Brain, Paperclip, Send, X } from "lucide-react";
import { AnimatePresence, motion, type Variants } from "motion/react";
import { runRagQueryNode } from "../../services/workflowNodes";
import { FileCardStack, CARD_H, CARD_GAP } from "./FileCardStack";

const PLACEHOLDERS = [
  "Summarise the cross-border data flow obligations...",
  "Which clauses relate to Pillar 6 indicators?",
  "Extract consent requirements from this text...",
  "Compare this law against RDTII 2.1 standards...",
  "Find data localisation provisions in the source...",
  "Identify breach notification requirements...",
];

const TEXT_SUB_INPUTS = [
  { key: "role", label: "Role", placeholder: "e.g. Legal analyst, Policy researcher..." },
  { key: "context", label: "Context", placeholder: "e.g. Reviewing Singapore's PDPA amendments..." },
];

interface AIChatInputProps {
  /** opts.newSession: the 'New' toggle was armed — route the FIRST file of
      the batch into a fresh session; the rest follow it. */
  onFileSelect?: (file: File, opts?: { newSession?: boolean }) => void | Promise<void>;
  isIngesting?: boolean;
  expandUp?: boolean;
  countryCode?: string;
  onResponse?: (answer: string, reasoning?: string) => void;
  /** Fired when the chat bar activates/deactivates (click / focus / click-away). */
  onActiveChange?: (active: boolean) => void;
  /** Fired the moment the user submits a question, before the answer arrives.
      opts.newSession is set when the 'New' toggle was active (start a fresh
      session thread instead of appending to the latest). */
  onSend?: (question: string, opts?: { newSession?: boolean }) => void;
  /** Fired when the RAG query fails (lets listeners clear pending state). */
  onError?: (message: string) => void;
  /** Show the 'New' session toggle (canvas chat nodes only — pages with a
      single conversation thread should leave this off). */
  enableNewSession?: boolean;
  provider?: string;
}

const AIChatInput = ({ onFileSelect, isIngesting = false, expandUp = false, countryCode, onResponse, onActiveChange, onSend, onError, enableNewSession = false, provider }: AIChatInputProps) => {
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [showPlaceholder, setShowPlaceholder] = useState(true);
  const [isActive, setIsActive] = useState(false);
  const [newSessionActive, setNewSessionActive] = useState(false);
  const [deepSearchActive, setDeepSearchActive] = useState(false);
  const [deepThinkingActive, setDeepThinkingActive] = useState(false);
  const [outputFormat, setOutputFormat] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [subValues, setSubValues] = useState<Record<string, string>>({ role: "", context: "" });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<{ id: number; file: File }[]>([]);
  const fileIdRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const handleSend = async () => {
    if (isLoading || isIngesting) return;

    // Files take priority — ingest each queued file, then clear the list
    if (uploadedFiles.length > 0 && onFileSelect) {
      for (const [index, { file }] of uploadedFiles.entries()) {
        await onFileSelect(file, { newSession: newSessionActive && index === 0 });
      }
      setNewSessionActive(false); // one-shot, same as text sends
      setUploadedFiles([]);
      return;
    }

    if (!inputValue.trim()) return;
    const question = inputValue.trim();
    onSend?.(question, { newSession: newSessionActive }); // bubble shows immediately
    setNewSessionActive(false); // one-shot: the toggle arms a single send
    setInputValue("");
    setIsLoading(true);
    setError("");
    try {
      const data = await runRagQueryNode({
        question,
        role: subValues.role,
        context: subValues.context,
        country_code: countryCode ?? "",
        provider: provider ?? "",
        deep_thinking: deepThinkingActive,
        output_format: outputFormat,
      });
      if (data.answer) {
        onResponse?.(data.answer, data.reasoning);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "RAG query failed.";
      setError(message);
      onError?.(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isActive || inputValue) return;
    const interval = setInterval(() => {
      setShowPlaceholder(false);
      setTimeout(() => {
        setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDERS.length);
        setShowPlaceholder(true);
      }, 400);
    }, 3000);
    return () => clearInterval(interval);
  }, [isActive, inputValue]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        if (!inputValue) setIsActive(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [inputValue]);

  useEffect(() => {
    onActiveChange?.(isActive);
  }, [isActive, onActiveChange]);

  const handleActivate = () => setIsActive(true);

  const containerVariants: Variants = {
    collapsed: {
      height: 68,
      boxShadow: "0 2px 8px 0 rgba(0,0,0,0.08)",
      transition: { type: "spring", stiffness: 120, damping: 18 },
    },
    expanded: {
      height: 128,
      boxShadow: "0 8px 32px 0 rgba(0,0,0,0.16)",
      transition: { type: "spring", stiffness: 120, damping: 18 },
    },
  };

  const placeholderContainerVariants = {
    initial: {},
    animate: { transition: { staggerChildren: 0.025 } },
    exit: { transition: { staggerChildren: 0.015, staggerDirection: -1 } },
  };

  const letterVariants: Variants = {
    initial: { opacity: 0, filter: "blur(12px)", y: 10 },
    animate: {
      opacity: 1, filter: "blur(0px)", y: 0,
      transition: { opacity: { duration: 0.25 }, filter: { duration: 0.4 }, y: { type: "spring", stiffness: 80, damping: 20 } },
    },
    exit: {
      opacity: 0, filter: "blur(12px)", y: -10,
      transition: { opacity: { duration: 0.2 }, filter: { duration: 0.3 }, y: { type: "spring", stiffness: 80, damping: 20 } },
    },
  };

  const subInputItemVariants: Variants = {
    hidden: { opacity: 0, y: -8, scale: 0.98 },
    visible: (i: number) => ({
      opacity: 1, y: 0, scale: 1,
      transition: { delay: i * 0.07, type: "spring", stiffness: 200, damping: 22 },
    }),
  };

  const subRowStyle = {
    background: "#f3f1ea",
    border: "1.5px solid #111827",
    borderRadius: 0,
    padding: "16px 20px",
    display: "flex",
    alignItems: "center",
    gap: 15,
    boxShadow: "none",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "0.7rem",
    fontWeight: 700,
    color: "#111827",
    textTransform: "uppercase" as const,
    letterSpacing: "0.08em",
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
    minWidth: 80,
    flexShrink: 0,
  };

  const n = uploadedFiles.length;

  return (
    <div ref={wrapperRef} className={`w-full text-black flex gap-2 ${expandUp ? "flex-col-reverse" : "flex-col"}`}>

      {/* Main chat bar */}
      <motion.div
        className="w-full"
        variants={containerVariants}
        animate={isActive || inputValue ? "expanded" : "collapsed"}
        initial="collapsed"
        style={{ overflow: "hidden", borderRadius: 0, background: "#f3f1ea", border: "1.5px solid #111827" }}
        onClick={handleActivate}
      >
        <div className="flex flex-col items-stretch w-full h-full">
          {/* Input Row */}
          <div className="flex items-center gap-2 p-3 w-full">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,.jpg,.jpeg,.png"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setUploadedFiles((prev) => [...prev, { id: fileIdRef.current++, file }]);
                e.target.value = "";
              }}
            />
            <button
              className={`p-3 rounded-none transition ${uploadedFiles.length > 0 || isIngesting ? "bg-[#111827]/10 text-[#111827]" : "hover:bg-[#111827]/5"}`}
              title="Attach file"
              type="button"
              tabIndex={-1}
              onClick={() => fileInputRef.current?.click()}
            >
              <Paperclip size={20} />
            </button>

            <div className="relative flex-1">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="flex-1 py-2 text-base w-full font-normal"
                style={{ position: "relative", zIndex: 1, border: "none", borderRadius: 0, boxShadow: "none", background: "transparent", padding: "8px 0", width: "100%" }}
                onFocus={handleActivate}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <div className="absolute left-0 top-0 w-full h-full pointer-events-none flex items-center px-3 py-2">
                <AnimatePresence mode="wait">
                  {showPlaceholder && !isActive && !inputValue && (
                    <motion.span
                      key={placeholderIndex}
                      className="absolute left-0 right-0 top-1/2 -translate-y-1/2 text-gray-400 select-none pointer-events-none"
                      style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", zIndex: 0 }}
                      variants={placeholderContainerVariants}
                      initial="initial"
                      animate="animate"
                      exit="exit"
                    >
                      {PLACEHOLDERS[placeholderIndex].split("").map((char, i) => (
                        <motion.span key={i} variants={letterVariants} style={{ display: "inline-block" }}>
                          {char === " " ? "\u00A0" : char}
                        </motion.span>
                      ))}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
            </div>

            <button className="p-3 rounded-none hover:bg-[#111827]/5 transition" title="Voice input" type="button" tabIndex={-1}>
              <Mic size={20} />
            </button>
            <button
              className="flex items-center gap-1 bg-[#111827] hover:bg-black disabled:opacity-50 text-[#f3f1ea] p-3 rounded-none font-medium justify-center transition"
              title="Send" type="button" tabIndex={-1}
              onClick={handleSend}
              disabled={isLoading || isIngesting || (uploadedFiles.length === 0 && !inputValue.trim())}
            >
              <Send size={18} className={isLoading ? "animate-pulse" : ""} />
            </button>
          </div>

          {/* Expanded Controls */}
          <motion.div
            className="w-full flex justify-start px-4 items-center text-sm"
            variants={{
              hidden: { opacity: 0, y: 20, pointerEvents: "none" as const, transition: { duration: 0.25 } },
              visible: { opacity: 1, y: 0, pointerEvents: "auto" as const, transition: { duration: 0.35, delay: 0.08 } },
            }}
            initial="hidden"
            animate={isActive || inputValue ? "visible" : "hidden"}
            style={{ marginTop: 8 }}
          >
            <div className="flex gap-3 items-center">
              {enableNewSession && (
              <button
                className={`flex items-center gap-1 px-4 py-2 rounded-none transition-all font-medium group ${newSessionActive ? "bg-[#111827] text-[#f3f1ea]" : "bg-[#111827]/5 text-[#111827] hover:bg-[#111827]/10"}`}
                title="Start a new session thread with the next message" type="button"
                onClick={(e) => { e.stopPropagation(); setNewSessionActive((a) => !a); }}
              >
                <MessageSquarePlus size={18} />
                New
              </button>
              )}

              <motion.button
                className={`flex items-center px-4 gap-1 py-2 rounded-none transition font-medium whitespace-nowrap overflow-hidden justify-start ${deepSearchActive ? "bg-[#111827] text-[#f3f1ea]" : "bg-[#111827]/5 text-[#111827] hover:bg-[#111827]/10"}`}
                title="Deep Search" type="button"
                onClick={(e) => { e.stopPropagation(); setDeepSearchActive((a) => !a); }}
                initial={false}
                animate={{ width: deepSearchActive ? 125 : 36, paddingLeft: deepSearchActive ? 8 : 9 }}
              >
                <div className="flex-1"><Globe size={18} /></div>
                <motion.span className="pb-[2px]" initial={false} animate={{ opacity: deepSearchActive ? 1 : 0 }}>
                  Deep Search
                </motion.span>
              </motion.button>

              <motion.button
                className={`flex items-center px-4 gap-1 py-2 rounded-none transition font-medium whitespace-nowrap overflow-hidden justify-start ${deepThinkingActive ? "bg-[#111827] text-[#f3f1ea]" : "bg-[#111827]/5 text-[#111827] hover:bg-[#111827]/10"}`}
                title="Deep Thinking — show the model's reasoning (reasoning model required)" type="button"
                onClick={(e) => { e.stopPropagation(); setDeepThinkingActive((a) => !a); }}
                initial={false}
                animate={{ width: deepThinkingActive ? 135 : 36, paddingLeft: deepThinkingActive ? 8 : 9 }}
              >
                <div className="flex-1"><Brain size={18} /></div>
                <motion.span className="pb-[2px]" initial={false} animate={{ opacity: deepThinkingActive ? 1 : 0 }}>
                  Deep Thinking
                </motion.span>
              </motion.button>

              <select
                className={`px-3 py-2 rounded-none font-medium text-sm transition cursor-pointer border-0 outline-none ${outputFormat ? "bg-[#111827] text-[#f3f1ea]" : "bg-[#111827]/5 text-[#111827] hover:bg-[#111827]/10"}`}
                title="Response format"
                value={outputFormat}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => { e.stopPropagation(); setOutputFormat(e.target.value); }}
              >
                <option value="">Format: Auto</option>
                <option value="markdown">Markdown</option>
                <option value="plain">Plain text</option>
                <option value="table">Table</option>
                <option value="bullets">Bullet points</option>
                <option value="json">JSON</option>
              </select>
            </div>
          </motion.div>
        </div>
      </motion.div>

      {error && (
        <p className="px-2 text-xs text-red-500">
          {error}
        </p>
      )}

      {/* Sub input fields — appear below the chat bar */}
      <AnimatePresence>
        {isActive && (
          <motion.div
            key="sub-inputs"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden", display: "flex", flexDirection: "column", gap: 8 }}
          >
            {TEXT_SUB_INPUTS.map((field, i) => (
              <motion.div
                key={field.key}
                custom={i}
                variants={subInputItemVariants}
                initial="hidden"
                animate="visible"
                style={subRowStyle}
              >
                <span style={labelStyle}>{field.label}</span>
                <input
                  type="text"
                  value={subValues[field.key]}
                  onChange={(e) => setSubValues((v) => ({ ...v, [field.key]: e.target.value }))}
                  placeholder={field.placeholder}
                  style={{
                    flex: 1, border: "none", boxShadow: "none", outline: "none", background: "transparent",
                    fontSize: "0.875rem", color: "#1f2933", padding: 0, borderRadius: 0, width: "100%",
                  }}
                />
              </motion.div>
            ))}

            {/* Stacked file cards — wrapper always mounted, collapses when empty */}
            <div style={{
              overflow: "hidden",
              // Generous cap so many files (and the toggle's shadow) never clip.
              maxHeight: n > 0 ? `${n * (CARD_H + CARD_GAP) + 140}px` : 0,
              opacity: n > 0 ? 1 : 0,
              transition: "max-height 0.35s cubic-bezier(0.4,0,0.2,1), opacity 0.25s ease",
            }}>
              <motion.div
                custom={TEXT_SUB_INPUTS.length}
                variants={subInputItemVariants}
                initial="hidden"
                animate={n > 0 ? "visible" : "hidden"}
              >
                <FileCardStack
                  items={uploadedFiles.map(({ id, file }) => ({
                    id: String(id),
                    name: file.name,
                    subtitle: `${(file.size / 1024).toFixed(0)} KB`,
                    actions: (
                      <button
                        type="button"
                        onClick={() => setUploadedFiles((prev) => prev.filter((entry) => entry.id !== id))}
                        style={{ flexShrink: 0, padding: 4, minHeight: 0, borderRadius: 0, border: "none", background: "transparent", cursor: "pointer", color: "#6b675c", display: "flex", alignItems: "center", justifyContent: "center" }}
                        className="hover:text-red-400 transition"
                      >
                        <X size={14} />
                      </button>
                    ),
                  }))}
                />
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
};

export { AIChatInput };
