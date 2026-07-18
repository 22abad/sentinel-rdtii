import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  MiniMap,
  addEdge,
  applyEdgeChanges,
  type Node,
  type Edge,
  type NodeChange,
  type EdgeChange,
  type Connection,
  type XYPosition,
  type ReactFlowInstance,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  PanelNode,
  NoteNode,
  FileNode,
  SessionNode,
  CanvasToolbar,
  type CanvasMode,
  type CanvasPanel,
  type ChatMessage,
  type SessionNodeData,
  type SpawnType,
  type PanelNodeData,
  type NoteNodeData,
  type FileNodeData,
  type WorkbenchCanvasEdge,
  type WorkbenchCanvasLayout,
  type WorkbenchCanvasNode,
  type WorkbenchCanvasNodeKind,
  type WorkbenchCanvasSize,
  type WorkbenchCanvasViewport,
} from "../../components/Canvas";
import { AIChatInput } from "../../components/Workbench/ChatInput";
import { uploadCanvasFile } from "../../services/canvasFiles";
import {
  loadWorkbenchCanvasLayout,
  readLocalWorkbenchCanvasLayout,
  saveLocalWorkbenchCanvasLayout,
  syncWorkbenchCanvasLayout,
} from "../../services/workbenchCanvasStorage";
import { clampSize, hasCustomSize, minSizeForNode } from "../../components/Canvas/resize";

export type { CanvasPanel } from "../../components/Canvas";

const nodeTypes = { panel: PanelNode, note: NoteNode, file: FileNode, session: SessionNode };

/** Panel types offered in the toolbar palette. */
const SPAWN_TYPES: SpawnType[] = [
  { id: "discovery", label: "Discovery" },
  { id: "source", label: "Source" },
  { id: "audit", label: "Audit" },
  { id: "documents", label: "Documents" },
];

/** Default landing positions; anything not listed falls back to a cascade. */
const DEFAULT_POSITIONS: Record<string, XYPosition> = {
  discovery: { x: 40, y: 40 },
  source: { x: 40, y: 360 },
  foundPdfs: { x: 540, y: 560 },
  audit: { x: 560, y: 40 },
  documents: { x: 360, y: 40 },
};

/** Example flow wiring the panels together — endpoints that don't exist are ignored. */
const INITIAL_EDGES: Edge[] = [
  { id: "e-discovery-source", source: "discovery", target: "source", animated: true },
  { id: "e-source-audit", source: "source", target: "audit", animated: true },
  { id: "e-source-foundPdfs", source: "source", target: "foundPdfs" },
];

const CANVAS_NODE_KINDS = new Set<WorkbenchCanvasNodeKind>(["panel", "note", "rag", "material", "session"]);
const PANEL_FALLBACKS: Record<string, { id: string; title: string; width?: number }> = {
  discovery: { id: "discovery", title: "Discovery", width: 800 },
  source: { id: "source", title: "Source", width: 460 },
  foundPdfs: { id: "foundPdfs", title: "Found PDFs", width: 420 },
  audit: { id: "audit", title: "Audit", width: 520 },
  documents: { id: "documents", title: "Documents", width: 420 },
};

type CanvasNote = { id: string; title: string; text: string };
type SpawnedPanel = { id: string; panelId: string };
type PanelMeta = { id: string; title: string; width?: number };
/** A RAG chat's conversation thread — Discord-thread style node, spawned by
    the chat's first message and persisted in the canvas layout. */
type SessionFile = { documentId: string; fileName: string };
type CanvasSession = { id: string; chatId: string; messages: ChatMessage[]; files: SessionFile[] };

type RestoredCanvasState = {
  positions: Record<string, XYPosition>;
  sizes: Record<string, WorkbenchCanvasSize>;
  removed: Record<string, boolean>;
  edges: Edge[];
  customNotes: CanvasNote[];
  spawned: SpawnedPanel[];
  chatIds: string[];
  sessions: CanvasSession[];
  viewport?: Viewport;
  noteCounter: number;
  spawnCounter: number;
  chatCounter: number;
  sessionCounter: number;
};

function readSavedCanvasLayout(): WorkbenchCanvasLayout | null {
  return normalizeCanvasLayout(readLocalWorkbenchCanvasLayout());
}

function normalizeCanvasLayout(layout: Partial<WorkbenchCanvasLayout> | null): WorkbenchCanvasLayout | null {
  if (!layout) return null;
  if (layout.version !== 1 || !Array.isArray(layout.nodes) || !Array.isArray(layout.edges)) {
    return null;
  }
  return {
    version: 1,
    nodes: layout.nodes.map(normalizeSavedNode).filter((node): node is WorkbenchCanvasNode => !!node),
    edges: layout.edges.map(normalizeSavedEdge).filter((edge): edge is WorkbenchCanvasEdge => !!edge),
    viewport: normalizeSavedViewport(layout.viewport),
    updatedAt: typeof layout.updatedAt === "string" ? layout.updatedAt : undefined,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isCanvasPosition(value: unknown): value is XYPosition {
  return isRecord(value) && isFiniteNumber(value.x) && isFiniteNumber(value.y);
}

function isCanvasNodeKind(value: unknown): value is WorkbenchCanvasNodeKind {
  return typeof value === "string" && CANVAS_NODE_KINDS.has(value as WorkbenchCanvasNodeKind);
}

function normalizeSavedNode(value: unknown): WorkbenchCanvasNode | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || !value.id || !isCanvasNodeKind(value.kind) || !isCanvasPosition(value.position)) {
    return null;
  }
  const node: WorkbenchCanvasNode = {
    id: value.id,
    kind: value.kind,
    position: { x: value.position.x, y: value.position.y },
  };
  if (typeof value.panelId === "string") node.panelId = value.panelId;
  if (typeof value.title === "string") node.title = value.title;
  if (typeof value.text === "string") node.text = value.text;
  if (isFiniteNumber(value.width)) node.width = value.width;
  if (isFiniteNumber(value.height)) node.height = value.height;
  if (typeof value.removed === "boolean") node.removed = value.removed;
  if (isRecord(value.config)) node.config = value.config;
  return node;
}

function normalizeSavedEdge(value: unknown): WorkbenchCanvasEdge | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || !value.id) return null;
  if (typeof value.source !== "string" || !value.source) return null;
  if (typeof value.target !== "string" || !value.target) return null;
  return {
    id: value.id,
    source: value.source,
    target: value.target,
    kind: "visual",
    label: typeof value.label === "string" ? value.label : undefined,
    animated: typeof value.animated === "boolean" ? value.animated : undefined,
  };
}

function normalizeSavedViewport(value: unknown): WorkbenchCanvasViewport | undefined {
  if (!isRecord(value) || !isFiniteNumber(value.x) || !isFiniteNumber(value.y) || !isFiniteNumber(value.zoom)) {
    return undefined;
  }
  return { x: value.x, y: value.y, zoom: value.zoom };
}

function restoreCanvasState(layout: WorkbenchCanvasLayout | null): RestoredCanvasState {
  if (!layout) {
    return {
      positions: DEFAULT_POSITIONS,
      sizes: {},
      removed: {},
      edges: INITIAL_EDGES,
      customNotes: [],
      spawned: [],
      chatIds: [],
      sessions: [],
      noteCounter: 0,
      spawnCounter: 0,
      chatCounter: 0,
      sessionCounter: 0,
    };
  }

  const positions: Record<string, XYPosition> = { ...DEFAULT_POSITIONS };
  const sizes: Record<string, WorkbenchCanvasSize> = {};
  const removed: Record<string, boolean> = {};
  const customNotes: CanvasNote[] = [];
  const spawned: SpawnedPanel[] = [];
  const chatIds: string[] = [];
  let noteCounter = 0;
  let spawnCounter = 0;
  let chatCounter = 0;
  const sessions: CanvasSession[] = [];
  let sessionCounter = 0;

  for (const node of layout.nodes) {
    positions[node.id] = node.position;
    const savedSize = normalizeRestoredSize(node);
    if (savedSize) {
      sizes[node.id] = savedSize;
    }
    if (node.removed) removed[node.id] = true;

    if (node.kind === "note") {
      customNotes.push({ id: node.id, title: node.title ?? "", text: node.text ?? "" });
      noteCounter = Math.max(noteCounter, numericSuffix(node.id, "note-"));
    } else if (node.kind === "rag") {
      chatIds.push(node.id);
      chatCounter = Math.max(chatCounter, numericSuffix(node.id, "chat-"));
    } else if (node.kind === "session") {
      sessions.push({
        id: node.id,
        chatId: typeof node.config?.chatId === "string" ? node.config.chatId : "",
        messages: restoreSessionMessages(node.config?.messages),
        files: restoreSessionFiles(node.config?.files),
      });
      sessionCounter = Math.max(sessionCounter, numericSuffix(node.id, "session-"));
    } else if (node.kind === "panel" && node.panelId && node.id !== node.panelId) {
      spawned.push({ id: node.id, panelId: node.panelId });
      spawnCounter = Math.max(spawnCounter, numericSuffix(node.id, `${node.panelId}-copy-`));
    }
  }

  return {
    positions,
    sizes,
    removed,
    edges: layout.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      animated: edge.animated,
      label: edge.label,
    })),
    customNotes,
    spawned,
    chatIds,
    sessions,
    viewport: layout.viewport,
    noteCounter,
    spawnCounter,
    chatCounter,
    sessionCounter,
  };
}

function restoreSessionFiles(value: unknown): SessionFile[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (f): f is SessionFile =>
      isRecord(f) && typeof f.documentId === "string" && typeof f.fileName === "string",
  );
}

function restoreSessionMessages(value: unknown): ChatMessage[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (m): m is ChatMessage =>
      isRecord(m) && (m.role === "user" || m.role === "assistant") && typeof m.text === "string",
  );
}

function normalizeRestoredSize(node: WorkbenchCanvasNode): WorkbenchCanvasSize | undefined {
  const size = { width: node.width, height: node.height };
  if (!hasCustomSize(size)) return undefined;

  const defaultWidth =
    node.kind === "panel"
      ? PANEL_FALLBACKS[node.id]?.width ?? (node.panelId ? PANEL_FALLBACKS[node.panelId]?.width : undefined)
      : node.kind === "note"
        ? 240
        : node.kind === "rag"
          ? 460
          : undefined;

  if (size.height == null && size.width === defaultWidth) {
    return undefined;
  }

  const clamped = clampSize(size, minSizeForNode(node.kind));
  return hasCustomSize(clamped) ? clamped : undefined;
}

function numericSuffix(id: string, prefix: string): number {
  if (!id.startsWith(prefix)) return 0;
  const suffix = id.slice(prefix.length);
  if (!/^\d+$/.test(suffix)) return 0;
  return Number(suffix);
}

function toCanvasLayout({
  panelMeta,
  positions,
  sizes,
  removed,
  edges,
  customNotes,
  spawned,
  chatIds,
  sessions,
  viewport,
}: {
  panelMeta: Record<string, PanelMeta>;
  positions: Record<string, XYPosition>;
  sizes: Record<string, WorkbenchCanvasSize>;
  removed: Record<string, boolean>;
  edges: Edge[];
  customNotes: CanvasNote[];
  spawned: SpawnedPanel[];
  chatIds: string[];
  sessions: CanvasSession[];
  viewport?: Viewport;
}): WorkbenchCanvasLayout {
  const nodes: WorkbenchCanvasNode[] = [];
  const panelIds = new Set<string>([...Object.keys(PANEL_FALLBACKS), ...Object.keys(panelMeta)]);

  for (const id of [...Object.keys(positions), ...Object.keys(removed)]) {
    if (PANEL_FALLBACKS[id] || panelMeta[id]) panelIds.add(id);
  }

  for (const id of panelIds) {
    const panel = panelMeta[id] ?? PANEL_FALLBACKS[id];
    if (!panel) continue;
    nodes.push({
      id,
      kind: "panel",
      panelId: id,
      title: panel.title,
      position: positions[id] ?? DEFAULT_POSITIONS[id] ?? { x: 40, y: 40 },
      width: sizes[id]?.width,
      height: sizes[id]?.height,
      removed: !!removed[id],
    });
  }

  for (const item of spawned.filter((entry) => !removed[entry.id])) {
    const source = panelMeta[item.panelId] ?? PANEL_FALLBACKS[item.panelId];
    if (!source) continue;
    nodes.push({
      id: item.id,
      kind: "panel",
      panelId: item.panelId,
      title: source?.title,
      position: positions[item.id] ?? { x: 160, y: 160 },
      width: sizes[item.id]?.width,
      height: sizes[item.id]?.height,
      removed: !!removed[item.id],
    });
  }

  for (const note of customNotes.filter((entry) => !removed[entry.id])) {
    nodes.push({
      id: note.id,
      kind: "note",
      title: note.title,
      text: note.text,
      position: positions[note.id] ?? { x: 120, y: 120 },
      width: sizes[note.id]?.width,
      height: sizes[note.id]?.height,
      removed: !!removed[note.id],
    });
  }

  for (const id of chatIds.filter((entry) => !removed[entry])) {
    nodes.push({
      id,
      kind: "rag",
      title: "RAG Chat",
      position: positions[id] ?? { x: 200, y: 200 },
      width: sizes[id]?.width,
      height: sizes[id]?.height,
      removed: !!removed[id],
    });
  }

  for (const session of sessions.filter((entry) => !removed[entry.id])) {
    nodes.push({
      id: session.id,
      kind: "session",
      title: "Session",
      position: positions[session.id] ?? { x: 260, y: 260 },
      width: sizes[session.id]?.width,
      height: sizes[session.id]?.height,
      removed: !!removed[session.id],
      // Conversation history rides in the layout — sessions survive refresh.
      config: { chatId: session.chatId, messages: session.messages, files: session.files },
    });
  }

  const activeNodeIds = new Set(nodes.filter((node) => !node.removed).map((node) => node.id));

  return {
    version: 1,
    nodes,
    edges: edges
      .filter((edge) => activeNodeIds.has(edge.source) && activeNodeIds.has(edge.target))
      .map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        kind: "visual",
        label: typeof edge.label === "string" ? edge.label : undefined,
        animated: edge.animated,
      })),
    viewport: viewport ? toCanvasViewport(viewport) : undefined,
    updatedAt: new Date().toISOString(),
  };
}

function toCanvasViewport(viewport: Viewport): WorkbenchCanvasViewport {
  return { x: viewport.x, y: viewport.y, zoom: viewport.zoom };
}

export type LinkedFile = { id: string; fileName?: string; previewUrl?: string };

export type CanvasGraph = {
  /** Live file nodes edge-linked to each panel INSTANCE (original or copy). */
  filesByInstance: Record<string, LinkedFile[]>;
  /** For panels declaring `upstreamId`: instance id → the upstream panel
      instance it is edge-bound to (null when unwired). */
  bindings: Record<string, string | null>;
};

export function WorkbenchCanvas({
  panels,
  onExit,
  onSwitchView,
  onGraphChange,
}: {
  panels: CanvasPanel[];
  onExit: () => void;
  /** Switch to the traditional (stacked) workbench layout. */
  onSwitchView?: () => void;
  /** Reports the data-wire graph: which live file nodes feed which panel
      instance, and which audit-style instances bind to which upstream
      instance. Linking registers availability; panels consume on demand. */
  onGraphChange?: (graph: CanvasGraph) => void;
}) {
  const restoredState = useMemo(() => restoreCanvasState(readSavedCanvasLayout()), []);
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const [positions, setPositions] = useState<Record<string, XYPosition>>(restoredState.positions);
  const [sizes, setSizes] = useState<Record<string, WorkbenchCanvasSize>>(restoredState.sizes);
  const [removed, setRemoved] = useState<Record<string, boolean>>(restoredState.removed);
  const [edges, setEdges] = useState<Edge[]>(restoredState.edges);
  const [customNotes, setCustomNotes] = useState<CanvasNote[]>(restoredState.customNotes);
  const [spawned, setSpawned] = useState<SpawnedPanel[]>(restoredState.spawned);
  const [chatIds, setChatIds] = useState<string[]>(restoredState.chatIds);
  const [sessions, setSessions] = useState<CanvasSession[]>(restoredState.sessions);
  // Typing indicator per session — transient, deliberately not persisted.
  const [pendingSessions, setPendingSessions] = useState<Record<string, boolean>>({});
  const [viewport, setViewport] = useState<Viewport | undefined>(restoredState.viewport);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [mode, setMode] = useState<CanvasMode>("select");
  const backendDirtyRef = useRef(false);
  const noteCounter = useRef(restoredState.noteCounter);
  const spawnCounter = useRef(restoredState.spawnCounter);
  const chatCounter = useRef(restoredState.chatCounter);
  const sessionCounter = useRef(restoredState.sessionCounter);
  const [files, setFiles] = useState<{ id: string; fileName?: string; fileSize?: number; previewUrl?: string; fileType?: string; ingestStatus?: "uploading" | "ingested" | "failed" | "extracting" | "extracted" | "stale" }[]>([]);
  const fileCounter = useRef(0);
  const markCanvasDirty = useCallback(() => {
    backendDirtyRef.current = true;
  }, []);

  // Files live in the browser (blob URLs) until a file node is linked to the
  // RAG chat node — that connection triggers the upload/ingest to the backend.
  const filesRef = useRef(files);
  filesRef.current = files;

  const markFileStale = useCallback((fileId: string) => {
    // The node survived a refresh but its blob URL didn't — there are no
    // bytes to send. Surface it instead of silently doing nothing.
    setFiles((prev) => prev.map((f) => (f.id === fileId ? { ...f, ingestStatus: "stale" as const } : f)));
  }, []);

  const ingestFileToRag = useCallback(async (fileId: string) => {
    const entry = filesRef.current.find((f) => f.id === fileId);
    if (entry && !entry.previewUrl) return markFileStale(fileId);
    if (!entry?.previewUrl || entry.ingestStatus === "uploading" || entry.ingestStatus === "ingested") return;
    const setStatus = (ingestStatus: "uploading" | "ingested" | "failed") =>
      setFiles((prev) => prev.map((f) => (f.id === fileId ? { ...f, ingestStatus } : f)));
    setStatus("uploading");
    try {
      // Recover the original bytes from the browser-held blob URL.
      const blob = await fetch(entry.previewUrl).then((r) => r.blob());
      const file = new File([blob], entry.fileName ?? "upload", { type: entry.fileType || blob.type });
      await uploadCanvasFile(file);
      setStatus("ingested");
    } catch (err) {
      console.error("Canvas file ingest failed:", err);
      setStatus("failed");
    }
  }, [markFileStale]);

  // ── RAG chat sessions — Discord-thread style ────────────────────────────
  // The first message on a chat node spawns its session node (beside it,
  // edge-wired); later messages append. Users never create sessions manually.
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const latestSessionFor = (chatId: string) =>
    [...sessionsRef.current].reverse().find((s) => s.chatId === chatId)?.id;

  const ensureSessionForChat = useCallback(
    (chatId: string, forceNew = false): string => {
      if (!forceNew) {
        const existing = [...sessionsRef.current]
          .reverse()
          .find((s) => s.chatId === chatId && !removed[s.id]);
        if (existing) return existing.id;
      }
      const id = `session-${(sessionCounter.current += 1)}`;
      const base = positions[chatId] ?? { x: 200, y: 200 };
      // Cascade siblings so a chat's sessions don't stack on one spot.
      const siblings = sessionsRef.current.filter((s) => s.chatId === chatId && !removed[s.id]).length;
      setSessions((prev) => [...prev, { id, chatId, messages: [], files: [] }]);
      setPositions((prev) => ({
        ...prev,
        [id]: { x: base.x + 520 + siblings * 32, y: base.y - 60 + siblings * 44 },
      }));
      setEdges((es) => [
        ...es,
        { id: `e-${chatId}-${id}`, source: chatId, target: id, animated: true },
      ]);
      markCanvasDirty();
      return id;
    },
    [positions, removed, markCanvasDirty],
  );

  const appendToSession = useCallback(
    (sessionId: string, message: ChatMessage) => {
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, messages: [...s.messages, message] } : s)),
      );
      markCanvasDirty();
    },
    [markCanvasDirty],
  );

  const attachFileToSession = useCallback(
    (sessionId: string, file: SessionFile) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId && !s.files.some((f) => f.documentId === file.documentId)
            ? { ...s, files: [...s.files, file] }
            : s,
        ),
      );
      markCanvasDirty();
    },
    [markCanvasDirty],
  );

  // Permanently delete an ingested document from the knowledge base, then
  // drop it from the session's scope and narrate the outcome.
  const deleteIngestedFile = useCallback(
    async (sessionId: string, documentId: string, fileName: string) => {
      try {
        const { deleteCanvasFile } = await import("../../services/canvasFiles");
        await deleteCanvasFile(documentId);
        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? { ...s, files: s.files.filter((f) => f.documentId !== documentId) }
              : s,
          ),
        );
        appendToSession(sessionId, {
          role: "assistant",
          text: `🗑 **${fileName}** has been deleted from the knowledge base.`,
        });
      } catch (err) {
        appendToSession(sessionId, {
          role: "assistant",
          text: `❌ Could not delete **${fileName}**: ${err instanceof Error ? err.message : "delete failed"}`,
        });
      }
    },
    [appendToSession],
  );

  const removeFileFromSession = useCallback(
    (sessionId: string, documentId: string) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? { ...s, files: s.files.filter((f) => f.documentId !== documentId) }
            : s,
        ),
      );
      markCanvasDirty();
    },
    [markCanvasDirty],
  );

  const handleChatSend = useCallback(
    (chatId: string, question: string, opts?: { newSession?: boolean }) => {
      const sessionId = ensureSessionForChat(chatId, opts?.newSession);
      appendToSession(sessionId, { role: "user", text: question });
      setPendingSessions((prev) => ({ ...prev, [sessionId]: true }));
    },
    [ensureSessionForChat, appendToSession],
  );

  // Paperclip uploads on a chat node: ingest into the RAG store and narrate
  // progress inside the chat's session thread.
  const [chatIngesting, setChatIngesting] = useState<Record<string, boolean>>({});
  const handleChatFileUpload = useCallback(
    async (chatId: string, file: File, opts?: { newSession?: boolean }) => {
      const sessionId = ensureSessionForChat(chatId, opts?.newSession);
      const say = (text: string) => appendToSession(sessionId, { role: "assistant", text });
      setChatIngesting((prev) => ({ ...prev, [chatId]: true }));
      say(`📎 Adding **${file.name}** to the knowledge base…`);
      try {
        const { uploadCanvasFile, getCanvasFileStatus } = await import("../../services/canvasFiles");
        const result = await uploadCanvasFile(file);
        if (result.deduplicated && result.status === "processed") {
          attachFileToSession(sessionId, { documentId: result.document_id, fileName: file.name });
          say(`✅ **${file.name}** is already in the knowledge base — ask me about it.`);
          return;
        }
        for (let i = 0; i < 20; i++) {
          await new Promise((resolve) => setTimeout(resolve, 1500));
          const status = await getCanvasFileStatus(result.document_id);
          if (status === "processed") {
            attachFileToSession(sessionId, { documentId: result.document_id, fileName: file.name });
            say(`✅ **${file.name}** is in the knowledge base — ask me about it.`);
            return;
          }
          if (status === "failed") {
            say(`❌ Ingestion of **${file.name}** failed on the server.`);
            return;
          }
        }
        say(`⏳ **${file.name}** is still processing — it should become searchable shortly.`);
      } catch (err) {
        const message = err instanceof Error ? err.message : "upload failed";
        say(
          /401|not authenticated/i.test(message)
            ? "🔒 Please log in to add documents to the knowledge base."
            : `❌ Could not add **${file.name}**: ${message}`,
        );
      } finally {
        setChatIngesting((prev) => ({ ...prev, [chatId]: false }));
      }
    },
    [ensureSessionForChat, appendToSession, attachFileToSession],
  );

  // Continue a specific session from its own input (bypasses the chat node).
  const sendToSession = useCallback(
    (sessionId: string, question: string) => {
      appendToSession(sessionId, { role: "user", text: question });
      setPendingSessions((prev) => ({ ...prev, [sessionId]: true }));
      void (async () => {
        try {
          const { runRagQueryNode } = await import("../../services/workflowNodes");
          const files = sessionsRef.current.find((s) => s.id === sessionId)?.files ?? [];
          const data = await runRagQueryNode({
            question,
            // Scope answers to this session's documents when it has any.
            document_ids: files.length ? files.map((f) => f.documentId) : undefined,
          });
          appendToSession(sessionId, { role: "assistant", text: data.answer });
        } catch (err) {
          appendToSession(sessionId, {
            role: "assistant",
            text: `❌ ${err instanceof Error ? err.message : "RAG query failed."}`,
          });
        } finally {
          setPendingSessions((prev) => ({ ...prev, [sessionId]: false }));
        }
      })();
    },
    [appendToSession],
  );

  const handleChatResponse = useCallback(
    (chatId: string, answer: string) => {
      const sessionId = latestSessionFor(chatId);
      if (!sessionId) return;
      appendToSession(sessionId, { role: "assistant", text: answer });
      setPendingSessions((prev) => ({ ...prev, [sessionId]: false }));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [appendToSession],
  );

  const handleChatError = useCallback((chatId: string) => {
    const sessionId = latestSessionFor(chatId);
    if (!sessionId) return;
    setPendingSessions((prev) => ({ ...prev, [sessionId]: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Report the data-wire graph. Linking only registers availability — no
  // upload/extraction happens until a panel consumes its wires (e.g. Run).
  // Ghost file nodes (blob lost after a refresh) are excluded so panels
  // never see sources they can't read.
  const lastGraphRef = useRef("");
  useEffect(() => {
    if (!onGraphChange) return;

    // Every live canvas instance of a base panel: the original + spawned copies.
    const instancesOf = (panelId: string): string[] => [
      ...(!removed[panelId] ? [panelId] : []),
      ...spawned.filter((s) => s.panelId === panelId && !removed[s.id]).map((s) => s.id),
    ];
    const connected = (a: string, b: string) =>
      edges.some((e) => (e.source === a && e.target === b) || (e.source === b && e.target === a));

    const filesByInstance: Record<string, LinkedFile[]> = {};
    const bindings: Record<string, string | null> = {};
    for (const p of panels) {
      for (const instanceId of instancesOf(p.id)) {
        const linked = files.filter(
          (f) => !removed[f.id] && f.previewUrl && connected(f.id, instanceId),
        );
        if (linked.length) {
          filesByInstance[instanceId] = linked.map(({ id, fileName, previewUrl }) => ({
            id,
            fileName,
            previewUrl,
          }));
        }
        if (p.upstreamId) {
          const upstream = instancesOf(p.upstreamId).find((uid) => connected(uid, instanceId));
          bindings[instanceId] = upstream ?? null;
        }
      }
    }

    // Only notify on real changes — `panels` gets a fresh identity every
    // parent render, so without this the effect would ping-pong with the
    // parent's setState forever.
    const serialized = JSON.stringify({ filesByInstance, bindings });
    if (serialized === lastGraphRef.current) return;
    lastGraphRef.current = serialized;
    onGraphChange({ filesByInstance, bindings });
  }, [onGraphChange, panels, spawned, files, edges, removed]);


  const handleFile = useCallback(async (id: string, file: File) => {
    setFiles((prev) => prev.map((f) => f.id === id ? {
      ...f,
      fileName: file.name, fileSize: file.size
    } : f));
    //    const form = new FormData(); form.append("file", file);
    //    await fetch(`${API_BASE}/api/workflows/...`, {
    //    method: "POST", body: form, header: { Authorization: `Bearer ${getStoredToken()}`}});
    // })
  }, []);

  const onCanvasDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const onCanvasDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!flowRef.current) return;
    const position = flowRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    for (const file of Array.from(e.dataTransfer.files)) {
      const id = `file-${(fileCounter.current += 1)}`;
      const previewUrl = URL.createObjectURL(file);
      setFiles((prev) => [...prev, { id, fileName: file.name, fileSize: file.size, previewUrl }]);
      setPositions((p) => ({ ...p, [id]: { x: position.x, y: position.y } }));
      handleFile(id, file);
    }
  }, [handleFile]);



  const applyCanvasState = useCallback((state: RestoredCanvasState) => {
    setPositions(state.positions);
    setSizes(state.sizes);
    setRemoved(state.removed);
    setEdges(state.edges);
    setCustomNotes(state.customNotes);
    setSpawned(state.spawned);
    setChatIds(state.chatIds);
    setSessions(state.sessions);
    setViewport(state.viewport);
    noteCounter.current = state.noteCounter;
    spawnCounter.current = state.spawnCounter;
    chatCounter.current = state.chatCounter;
    sessionCounter.current = state.sessionCounter;
    if (state.viewport) {
      flowRef.current?.setViewport(state.viewport);
    }
  }, []);

  useEffect(() => {
    let active = true;
    loadWorkbenchCanvasLayout()
      .then((layout) => {
        const normalized = normalizeCanvasLayout(layout);
        if (!active || !normalized || backendDirtyRef.current) return;
        applyCanvasState(restoreCanvasState(normalized));
      });
    return () => {
      active = false;
    };
  }, [applyCanvasState]);

  // FigJam-style V / H tool shortcuts (ignored while typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "v" || e.key === "V") setMode("select");
      else if (e.key === "h" || e.key === "H") setMode("hand");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const panelById = useMemo(
    () => Object.fromEntries(panels.map((p) => [p.id, p])),
    [panels],
  );
  const panelMeta = useMemo(
    () => Object.fromEntries(panels.map((p) => [p.id, { id: p.id, title: p.title, width: p.width }])),
    [panels],
  );
  const panelMetaRef = useRef<Record<string, PanelMeta>>(panelMeta);

  useEffect(() => {
    panelMetaRef.current = panelMeta;
  }, [panelMeta]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const layout = toCanvasLayout({
        panelMeta: panelMetaRef.current,
        positions,
        sizes,
        removed,
        edges,
        customNotes,
        spawned,
        chatIds,
        sessions,
        viewport,
      });
      saveLocalWorkbenchCanvasLayout(layout);
      if (backendDirtyRef.current) {
        backendDirtyRef.current = false;
        void syncWorkbenchCanvasLayout(layout);
      }
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [positions, sizes, removed, edges, customNotes, spawned, chatIds, sessions, viewport]);

  const resizeNode = useCallback(
    (id: string, size: WorkbenchCanvasSize) => {
      markCanvasDirty();
      setSizes((prev) => ({ ...prev, [id]: size }));
    },
    [markCanvasDirty],
  );

  const resetNodeSize = useCallback(
    (id: string) => {
      markCanvasDirty();
      setSizes((prev) => {
        if (!prev[id]) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      });
    },
    [markCanvasDirty],
  );

  const spawnPanel = useCallback((panelId: string, position: XYPosition) => {
    markCanvasDirty();
    const n = (spawnCounter.current += 1);
    const id = `${panelId}-copy-${n}`;
    const offset = (n % 6) * 26;
    setSpawned((prev) => [...prev, { id, panelId }]);
    setPositions((p) => ({ ...p, [id]: { x: position.x + offset, y: position.y + offset } }));
  }, [markCanvasDirty]);

  const updateNote = useCallback(
    (id: string, patch: Partial<{ title: string; text: string }>) => {
      markCanvasDirty();
      setCustomNotes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)));
    },
    [markCanvasDirty],
  );

  const addNote = useCallback((position: XYPosition) => {
    markCanvasDirty();
    const id = `note-${(noteCounter.current += 1)}`;
    setCustomNotes((prev) => [...prev, { id, title: "", text: "" }]);
    setPositions((p) => ({ ...p, [id]: position }));
  }, [markCanvasDirty]);

  const spawnChat = useCallback((position: XYPosition) => {
    markCanvasDirty();
    const id = `chat-${(chatCounter.current += 1)}`;
    setChatIds((prev) => [...prev, id]);
    setPositions((p) => ({ ...p, [id]: position }));
  }, [markCanvasDirty]);

  const removeNode = useCallback((id: string) => {
    markCanvasDirty();
    const persistentPanel = !!(PANEL_FALLBACKS[id] || panelMetaRef.current[id]);
    setEdges((prev) => prev.filter((edge) => edge.source !== id && edge.target !== id));
    setSelectedIds((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });

    if (persistentPanel) {
      setRemoved((prev) => ({ ...prev, [id]: true }));
      return;
    }

    setCustomNotes((prev) => prev.filter((note) => note.id !== id));
    setSpawned((prev) => prev.filter((item) => item.id !== id));
    setChatIds((prev) => prev.filter((chatId) => chatId !== id));
    setFiles((prev) => {
      const gone = prev.find((f) => f.id === id);
      if (gone?.previewUrl) URL.revokeObjectURL(gone.previewUrl);
      return prev.filter((f) => f.id !== id);
    });
    setPositions((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setSizes((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setRemoved((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, [markCanvasDirty]);

  const nodes = useMemo<Node[]>(
    () =>
      [
        ...panels
          .filter((p) => !removed[p.id])
          .map((p, i) => ({
            id: p.id,
            type: "panel",
            dragHandle: p.dragHandle,
            position: positions[p.id] ?? { x: 40 + i * 48, y: 40 + i * 48 },
            data: {
              title: p.title,
              // Per-instance element when the panel supports it (extraction
              // threads); unbound/disconnected states are the panel's job.
              element: p.renderElement ? p.renderElement(p.id) : p.element,
              width: sizes[p.id]?.width ?? p.width,
              height: sizes[p.id]?.height,
              flat: p.flat,
              onResize: (size: WorkbenchCanvasSize) => resizeNode(p.id, size),
              onDelete: () => removeNode(p.id),
            } satisfies PanelNodeData,
          })),
        ...spawned
          .filter((s) => !removed[s.id] && panelById[s.panelId])
          .map((s) => {
            const src = panelById[s.panelId];
            return {
              id: s.id,
              type: "panel",
              dragHandle: src.dragHandle,
              position: positions[s.id] ?? { x: 160, y: 160 },
              data: {
                title: src.title,
                // Spawned copies get their OWN element instance — this is
                // what makes copies independent extraction threads instead
                // of mirrors of the original panel.
                element: src.renderElement ? src.renderElement(s.id) : src.element,
                width: sizes[s.id]?.width ?? src.width,
                height: sizes[s.id]?.height,
                flat: src.flat,
                onResize: (size: WorkbenchCanvasSize) => resizeNode(s.id, size),
                onDelete: () => removeNode(s.id),
              } satisfies PanelNodeData,
            };
          }),
        ...customNotes
          .filter((n) => !removed[n.id])
          .map((n) => ({
            id: n.id,
            type: "note",
            position: positions[n.id] ?? { x: 120, y: 120 },
            data: {
              title: n.title,
              text: n.text,
              onChange: (patch: Partial<{ title: string; text: string }>) => updateNote(n.id, patch),
              width: sizes[n.id]?.width,
              height: sizes[n.id]?.height,
              onResize: (size: WorkbenchCanvasSize) => resizeNode(n.id, size),
              onDelete: () => removeNode(n.id),
            } satisfies NoteNodeData,
          })),
        ...chatIds
          .filter((id) => !removed[id])
          .map((id) => ({
            id,
            type: "panel",
            position: positions[id] ?? { x: 200, y: 200 },
            data: {
              title: "RAG Chat",
              element: (
                <AIChatInput
                  enableNewSession
                  onSend={(question, opts) => handleChatSend(id, question, opts)}
                  onResponse={(answer) => handleChatResponse(id, answer)}
                  onError={() => handleChatError(id)}
                  onFileSelect={(file, opts) => handleChatFileUpload(id, file, opts)}
                  isIngesting={!!chatIngesting[id]}
                />
              ),
              width: sizes[id]?.width ?? 460,
              height: sizes[id]?.height,
              transparent: true,
              onResize: (size: WorkbenchCanvasSize) => resizeNode(id, size),
              onDelete: () => removeNode(id),
            } satisfies PanelNodeData,
          })),
        ...sessions
          .filter((s) => !removed[s.id])
          .map((s) => ({
            id: s.id,
            type: "session",
            position: positions[s.id] ?? { x: 260, y: 260 },
            data: {
              title: `Session · ${s.chatId.replace("chat-", "thread #")}`,
              messages: s.messages,
              pending: !!pendingSessions[s.id],
              onSend: (question: string) => sendToSession(s.id, question),
              files: s.files,
              onRemoveFile: (documentId: string) => removeFileFromSession(s.id, documentId),
              onDeleteFile: (documentId: string, fileName: string) =>
                deleteIngestedFile(s.id, documentId, fileName),
              width: sizes[s.id]?.width,
              height: sizes[s.id]?.height,
              onResize: (size: WorkbenchCanvasSize) => resizeNode(s.id, size),
              onDelete: () => removeNode(s.id),
            } satisfies SessionNodeData,
          })),
        ...files
          .filter((f) => !removed[f.id])
          .map((f) => ({
            id: f.id,
            type: "file",
            position: positions[f.id] ?? { x: 240, y: 240 },
            data: {
              fileName: f.fileName,
              fileSize: f.fileSize,
              previewUrl: f.previewUrl,
              fileType: f.fileType,
              ingestStatus: f.ingestStatus,
              width: sizes[f.id]?.width,
              height: sizes[f.id]?.height,
              onResize: (size: WorkbenchCanvasSize) => resizeNode(f.id, size),
              onResetSize: () => resetNodeSize(f.id),
              onDelete: () => removeNode(f.id),
            } satisfies FileNodeData,
          })),
      ].map((n) => ({ ...n, selected: !!selectedIds[n.id] })),
    [panels, spawned, panelById, customNotes, chatIds, sessions, pendingSessions, files, positions, sizes, removed, updateNote, resizeNode, resetNodeSize, removeNode, selectedIds, handleChatSend, handleChatResponse, handleChatError, sendToSession, handleChatFileUpload, chatIngesting, removeFileFromSession, deleteIngestedFile],
  );

  const renderedEdges = useMemo(() => {
    const visibleNodeIds = new Set(nodes.map((node) => node.id));
    return edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));
  }, [edges, nodes]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    if (changes.some((c) => c.type === "position" || c.type === "remove")) {
      markCanvasDirty();
    }
    setPositions((prev) => {
      let next = prev;
      for (const c of changes) {
        if (c.type === "position" && c.position) {
          next = { ...next, [c.id]: c.position };
        }
      }
      return next;
    });
    setSelectedIds((prev) => {
      let next = prev;
      for (const c of changes) {
        if (c.type === "select") {
          next = { ...next, [c.id]: c.selected };
        }
      }
      return next;
    });
    for (const c of changes) {
      if (c.type === "remove") removeNode(c.id);
    }
  }, [markCanvasDirty, removeNode]);

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      if (changes.length > 0) markCanvasDirty();
      setEdges((es) => applyEdgeChanges(changes, es));
    },
    [markCanvasDirty],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      markCanvasDirty();
      setEdges((es) => addEdge(c, es));
      // Edges from a file node act as data wires:
      //   file ↔ chat-N   → RAG ingest fires immediately (extract → chunk → embed)
      //   file ↔ <panel>  → registers the file as an available source; the
      //                     panel consumes it on demand (see onLinkedFilesChange)
      const ids = [c.source, c.target];
      const fileId = ids.find((id) => id?.startsWith("file-"));
      if (!fileId) return;
      const otherId = ids.find((id) => id !== fileId);
      if (!otherId) return;
      const entry = filesRef.current.find((f) => f.id === fileId);
      if (entry && !entry.previewUrl) {
        // Ghost node (blob died on refresh) — flag it instead of silently
        // linking a source that can't be read.
        markFileStale(fileId);
        return;
      }
      if (otherId.startsWith("chat-")) {
        void ingestFileToRag(fileId);
      }
    },
    [markCanvasDirty, ingestFileToRag, markFileStale],
  );

  const handleReset = useCallback(() => {
    markCanvasDirty();
    setPositions(DEFAULT_POSITIONS);
    setSizes({});
    setRemoved({});
    setEdges(INITIAL_EDGES);
    setCustomNotes([]);
    setSpawned([]);
    setChatIds([]);
    setSessions([]);
    setPendingSessions({});
    sessionCounter.current = 0;
    setSelectedIds({});
    setViewport(undefined);
    noteCounter.current = 0;
    spawnCounter.current = 0;
    chatCounter.current = 0;
    window.requestAnimationFrame(() => {
      flowRef.current?.fitView({ maxZoom: 1, padding: 0.2 });
    });
  }, [markCanvasDirty]);

  const handMode = mode === "hand";

  return (
    <div className={`fixed inset-0 z-30 wb-canvas ${handMode ? "wb-hand" : "wb-select"}`}
      style={{
        height: "100dvh"
      }}
      onDragOver={onCanvasDragOver}
      onDrop={onCanvasDrop}
    >
      {/* Cursor feedback for the active tool, scoped to this canvas */}
      <style>{`
        .wb-hand .react-flow__pane { cursor: grab; }
        .wb-hand .react-flow__pane.dragging { cursor: grabbing; }
        .wb-select .react-flow__node .panel-header { cursor: grab; }
        .wb-select .react-flow__node.dragging .panel-header { cursor: grabbing; }
      `}</style>
      <ReactFlow
        nodes={nodes}
        edges={renderedEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={(instance: ReactFlowInstance) => {
          flowRef.current = instance;
          if (viewport) {
            void instance.setViewport(viewport);
          }
        }}
        onMoveEnd={(_event: MouseEvent | TouchEvent | null, nextViewport: Viewport) => setViewport(nextViewport)}
        deleteKeyCode={["Delete", "Backspace"]}
        minZoom={0.8}
        fitView={!restoredState.viewport}
        defaultViewport={restoredState.viewport}
        fitViewOptions={{ maxZoom: 1, padding: 0.2 }}
        style={{ background: "#ffffff" }}
        nodesDraggable={!handMode}
        nodesConnectable={!handMode}
        elementsSelectable={!handMode}
      >
        <Background variant={BackgroundVariant.Dots} gap={28} size={3} color="#c2c8d0" bgColor="#f3f1ea" />
        <MiniMap pannable zoomable maskColor="rgba(0,0,0,0.4)" />
        <CanvasToolbar
          mode={mode}
          onSetMode={setMode}
          spawnTypes={SPAWN_TYPES}
          onSpawnPanel={spawnPanel}
          onAddPanel={addNote}
          onAddChat={spawnChat}
          onReset={handleReset}
          onSwitchView={onSwitchView}
          onExit={onExit}
        />
      </ReactFlow>
    </div>
  );
}
