import { useEffect, useRef, useState } from "react";
import { Handle, NodeResizer, Position } from "@xyflow/react";
import { motion } from "motion/react";
import { Trash2, MessagesSquare, ChevronDown, Send, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { RESIZER_HANDLE_STYLE, RESIZER_LINE_STYLE } from "./resize";
import type { ChatMessage, WorkbenchCanvasSize } from "./types";
import { FileCardStack } from "../Workbench/FileCardStack";

export type SessionNodeData = {
  title?: string;
  messages: ChatMessage[];
  /** True while the linked RAG chat awaits an answer for this session. */
  pending?: boolean;
  /** Continue this session directly from the node's own input. */
  onSend?: (question: string) => void;
  /** Documents attached to this session — answers are scoped to them. */
  files?: { documentId: string; fileName: string }[];
  onRemoveFile?: (documentId: string) => void;
  /** Permanently delete the ingested document from the knowledge base. */
  onDeleteFile?: (documentId: string, fileName: string) => void;
  width?: number;
  height?: number;
  onResize?: (size: WorkbenchCanvasSize) => void;
  onDelete: () => void;
};

const SESSION_MIN_SIZE = { width: 300, height: 200 };

/**
 * A chat session thread on the canvas — Discord-thread style. Spawned by a
 * RAG chat node on its first message; holds the conversation history
 * (persisted in the canvas layout) and renders replies as markdown.
 */
export function SessionNode({ id, data, selected }: { id: string; data: SessionNodeData; selected?: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [minimized, setMinimized] = useState(false);
  const [dataOpen, setDataOpen] = useState(false);
  const [draft, setDraft] = useState("");

  const submitDraft = () => {
    const question = draft.trim();
    if (!question || data.pending || !data.onSend) return;
    data.onSend(question);
    setDraft("");
  };
  const nodeWidth = data.width ?? 380;
  const nodeHeight = minimized ? undefined : data.height ?? 340;

  // Pin the thread to the latest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [data.messages, data.pending]);

  return (
    <div style={{ position: "relative", width: nodeWidth, height: nodeHeight ?? "auto" }}>
      <NodeResizer
        nodeId={id}
        isVisible={selected && !minimized}
        minWidth={SESSION_MIN_SIZE.width}
        minHeight={SESSION_MIN_SIZE.height}
        color="#10B981"
        handleStyle={RESIZER_HANDLE_STYLE}
        lineStyle={RESIZER_LINE_STYLE}
        onResize={(_event, params) => data.onResize?.({ width: params.width, height: params.height })}
      />

      {selected && (
        <button
          className="nodrag"
          title="Delete session"
          onClick={(e) => {
            e.stopPropagation();
            data.onDelete();
          }}
          style={{
            position: "absolute",
            bottom: "100%",
            left: "50%",
            transform: "translateX(-50%)",
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
            height: 24,
            minHeight: 0,
            padding: "0 10px",
            borderRadius: 0,
            border: "none",
            background: "#9f2d20",
            color: "white",
            fontSize: "0.7rem",
            fontWeight: 600,
            cursor: "pointer",
            whiteSpace: "nowrap",
            boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
          }}
        >
          <Trash2 size={12} /> Delete
        </button>
      )}

      <div
        style={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          borderRadius: 0,
          overflow: "hidden",
          background: "#f3f1ea",
          border: "1.5px solid #111827",
          boxShadow: "none",
        }}
      >
        <Handle type="target" position={Position.Left} style={{ background: "#111827" }} />

        {/* Header */}
        <div
          className="panel-header"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            background: "transparent",
            borderBottom: "1.5px solid #111827",
            flexShrink: 0,
          }}
        >
          <MessagesSquare size={14} color="#111827" />
          <span style={{ flex: 1, fontSize: "0.82rem", fontWeight: 800, color: "#111827", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {data.title ?? "Session"}
          </span>
          <span style={{ fontSize: "0.68rem", color: "#8a94a3" }}>
            {data.messages.length} message{data.messages.length !== 1 ? "s" : ""}
          </span>
          <button
            className="nodrag"
            title={minimized ? "Expand session" : "Minimize session"}
            aria-expanded={!minimized}
            onClick={(e) => {
              e.stopPropagation();
              setMinimized((v) => !v);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 20,
              height: 20,
              minHeight: 0,
              padding: 0,
              borderRadius: 9999,
              border: "none",
              background: "transparent",
              color: "#5a6573",
              cursor: "pointer",
            }}
          >
            <motion.span
              animate={{ rotate: minimized ? 180 : 0 }}
              transition={{ duration: 0.2 }}
              style={{ display: "flex" }}
            >
              <ChevronDown size={14} />
            </motion.span>
          </button>
        </div>

        {/* Session data bar — expands a management tray hanging below the node */}
        {!minimized && (data.files?.length ?? 0) > 0 && (
          <button
            type="button"
            className="nodrag"
            aria-expanded={dataOpen}
            title="Documents attached to this session — answers are scoped to them."
            onClick={(e) => {
              e.stopPropagation();
              setDataOpen((v) => !v);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              padding: "7px 12px",
              minHeight: 0,
              border: "none",
              borderBottom: "1.5px solid #111827",
              borderRadius: 0,
              background: "transparent",
              color: "#111827",
              fontSize: "0.72rem",
              fontWeight: 750,
              cursor: "pointer",
              flexShrink: 0,
              textAlign: "left",
            }}
          >
            <FileText size={12} />
            {data.files?.length} document{(data.files?.length ?? 0) !== 1 ? "s" : ""} in this session
            <motion.span
              animate={{ rotate: dataOpen ? 180 : 0 }}
              transition={{ duration: 0.2 }}
              style={{ display: "flex", marginLeft: "auto" }}
            >
              <ChevronDown size={13} />
            </motion.span>
          </button>
        )}

        {/* Thread — hidden while minimized (header keeps title + count) */}
        {!minimized && (
        <div
          ref={scrollRef}
          className="nodrag nowheel chat-md-session"
          onMouseDown={(e) => e.stopPropagation()}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            userSelect: "text",
          }}
        >
          {data.messages.length === 0 && (
            <p style={{ margin: "auto", fontSize: "0.75rem", color: "#8a94a3", textAlign: "center" }}>
              Messages from the linked RAG chat will appear here.
            </p>
          )}
          {data.messages.map((m, i) => (
            <div
              key={i}
              className={m.role === "assistant" ? "chat-md" : undefined}
              style={{
                maxWidth: "85%",
                alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                borderRadius: 0,
                padding: "8px 12px",
                fontSize: "0.8rem",
                lineHeight: 1.5,
                whiteSpace: m.role === "user" ? "pre-wrap" : undefined,
                ...(m.role === "user"
                  ? { background: "#111827", color: "#f3f1ea" }
                  : { background: "#ffffff", color: "#1f2933", border: "1px solid #111827" }),
              }}
            >
              {m.role === "assistant" ? (
                <>
                  {m.reasoning ? (
                    <details className="chat-reasoning" style={{ marginBottom: 8 }}>
                      <summary
                        style={{
                          cursor: "pointer",
                          fontSize: "0.7rem",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                          color: "#6b7280",
                          userSelect: "none",
                        }}
                      >
                        Thinking
                      </summary>
                      <div
                        style={{
                          marginTop: 6,
                          paddingLeft: 8,
                          borderLeft: "2px solid #d1d5db",
                          color: "#6b7280",
                          fontStyle: "italic",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {m.reasoning}
                      </div>
                    </details>
                  ) : null}
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                </>
              ) : (
                m.text
              )}
            </div>
          ))}
          {data.pending && (
            <div
              style={{
                alignSelf: "flex-start",
                borderRadius: 0,
                padding: "8px 12px",
                fontSize: "0.8rem",
                background: "#ffffff",
                border: "1px solid #111827",
                color: "#6b675c",
              }}
            >
              <span style={{ display: "inline-flex", gap: 3 }}>
                <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0 }}>●</motion.span>
                <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}>●</motion.span>
                <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}>●</motion.span>
              </span>
            </div>
          )}
        </div>
        )}

        {/* Session-local input — continue this thread without the chat node */}
        {!minimized && data.onSend && (
          <div
            className="nodrag"
            style={{
              display: "flex",
              gap: 8,
              padding: "8px 10px",
              borderTop: "1.5px solid #111827",
              background: "transparent",
              flexShrink: 0,
            }}
          >
            <input
              type="text"
              value={draft}
              placeholder="Reply in this session…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  submitDraft();
                }
              }}
              onMouseDown={(e) => e.stopPropagation()}
              style={{
                flex: 1,
                minWidth: 0,
                border: "none",
                borderRadius: 0,
                padding: "6px 4px",
                fontSize: "0.8rem",
                background: "transparent",
                outline: "none",
              }}
            />
            <button
              type="button"
              title="Send"
              onClick={(e) => {
                e.stopPropagation();
                submitDraft();
              }}
              disabled={!draft.trim() || data.pending}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 32,
                height: 32,
                minHeight: 0,
                padding: 0,
                borderRadius: 0,
                border: "none",
                background: "#111827",
                color: "#f3f1ea",
                cursor: "pointer",
              }}
            >
              <Send size={14} className={data.pending ? "animate-pulse" : undefined} />
            </button>
          </div>
        )}
      </div>

      {/* Data tray — hangs below the node when expanded */}
      {!minimized && dataOpen && (data.files?.length ?? 0) > 0 && (
        <div
          className="nodrag nowheel"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 10,
            zIndex: 20,
            background: "transparent",
          }}
        >
          <FileCardStack
            items={(data.files ?? []).map((f) => ({
              id: f.documentId,
              name: f.fileName,
              subtitle: "in knowledge base",
              actions: (
                <span style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  {data.onRemoveFile && (
                    <button
                      type="button"
                      title="Remove from this session (keeps the document in the knowledge base)"
                      onClick={(e) => {
                        e.stopPropagation();
                        data.onRemoveFile?.(f.documentId);
                      }}
                      style={{
                        minHeight: 0,
                        padding: "3px 9px",
                        borderRadius: 0,
                        border: "1.5px solid #111827",
                        background: "#f3f1ea",
                        color: "#111827",
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      Unlink
                    </button>
                  )}
                  {data.onDeleteFile && (
                    <button
                      type="button"
                      title="Delete the ingested data from the knowledge base (permanent)"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (window.confirm(`Delete “${f.fileName}” from the knowledge base? This removes its ingested data for everyone.`)) {
                          data.onDeleteFile?.(f.documentId, f.fileName);
                        }
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        minHeight: 0,
                        padding: "3px 9px",
                        borderRadius: 0,
                        border: "1.5px solid #9f2d20",
                        background: "#f3f1ea",
                        color: "#9f2d20",
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      <Trash2 size={11} /> Delete
                    </button>
                  )}
                </span>
              ),
            }))}
          />
        </div>
      )}
    </div>
  );
}
