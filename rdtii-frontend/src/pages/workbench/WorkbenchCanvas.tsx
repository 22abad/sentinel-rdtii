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
  CanvasToolbar,
  type CanvasMode,
  type CanvasPanel,
  type SpawnType,
  type PanelNodeData,
  type NoteNodeData,
  type WorkbenchCanvasEdge,
  type WorkbenchCanvasLayout,
  type WorkbenchCanvasNode,
  type WorkbenchCanvasNodeKind,
  type WorkbenchCanvasViewport,
} from "../../components/Canvas";
import { AIChatInput } from "../../components/Workbench/ChatInput";
import {
  loadWorkbenchCanvasLayout,
  readLocalWorkbenchCanvasLayout,
  saveLocalWorkbenchCanvasLayout,
  syncWorkbenchCanvasLayout,
} from "../../services/workbenchCanvasStorage";

export type { CanvasPanel } from "../../components/Canvas";

const nodeTypes = { panel: PanelNode, note: NoteNode };

/** Panel types offered in the toolbar palette. */
const SPAWN_TYPES: SpawnType[] = [
  { id: "discovery", label: "Discovery" },
  { id: "source", label: "Source" },
  { id: "audit", label: "Audit" },
];

/** Default landing positions; anything not listed falls back to a cascade. */
const DEFAULT_POSITIONS: Record<string, XYPosition> = {
  discovery: { x: 40, y: 40 },
  source: { x: 40, y: 360 },
  foundPdfs: { x: 540, y: 560 },
  audit: { x: 560, y: 40 },
};

/** Example flow wiring the panels together — endpoints that don't exist are ignored. */
const INITIAL_EDGES: Edge[] = [
  { id: "e-discovery-source", source: "discovery", target: "source", animated: true },
  { id: "e-source-audit", source: "source", target: "audit", animated: true },
  { id: "e-source-foundPdfs", source: "source", target: "foundPdfs" },
];

const CANVAS_NODE_KINDS = new Set<WorkbenchCanvasNodeKind>(["panel", "note", "rag", "material"]);
const PANEL_FALLBACKS: Record<string, { id: string; title: string; width?: number }> = {
  discovery: { id: "discovery", title: "Discovery", width: 800 },
  source: { id: "source", title: "Source", width: 460 },
  foundPdfs: { id: "foundPdfs", title: "Found PDFs", width: 420 },
  audit: { id: "audit", title: "Audit", width: 520 },
};

type CanvasNote = { id: string; title: string; text: string };
type SpawnedPanel = { id: string; panelId: string };
type PanelMeta = { id: string; title: string; width?: number };

type RestoredCanvasState = {
  positions: Record<string, XYPosition>;
  removed: Record<string, boolean>;
  edges: Edge[];
  customNotes: CanvasNote[];
  spawned: SpawnedPanel[];
  chatIds: string[];
  viewport?: Viewport;
  noteCounter: number;
  spawnCounter: number;
  chatCounter: number;
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
      removed: {},
      edges: INITIAL_EDGES,
      customNotes: [],
      spawned: [],
      chatIds: [],
      noteCounter: 0,
      spawnCounter: 0,
      chatCounter: 0,
    };
  }

  const positions: Record<string, XYPosition> = { ...DEFAULT_POSITIONS };
  const removed: Record<string, boolean> = {};
  const customNotes: CanvasNote[] = [];
  const spawned: SpawnedPanel[] = [];
  const chatIds: string[] = [];
  let noteCounter = 0;
  let spawnCounter = 0;
  let chatCounter = 0;

  for (const node of layout.nodes) {
    positions[node.id] = node.position;
    if (node.removed) removed[node.id] = true;

    if (node.kind === "note") {
      customNotes.push({ id: node.id, title: node.title ?? "", text: node.text ?? "" });
      noteCounter = Math.max(noteCounter, numericSuffix(node.id, "note-"));
    } else if (node.kind === "rag") {
      chatIds.push(node.id);
      chatCounter = Math.max(chatCounter, numericSuffix(node.id, "chat-"));
    } else if (node.kind === "panel" && node.panelId && node.id !== node.panelId) {
      spawned.push({ id: node.id, panelId: node.panelId });
      spawnCounter = Math.max(spawnCounter, numericSuffix(node.id, `${node.panelId}-copy-`));
    }
  }

  return {
    positions,
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
    viewport: layout.viewport,
    noteCounter,
    spawnCounter,
    chatCounter,
  };
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
  removed,
  edges,
  customNotes,
  spawned,
  chatIds,
  viewport,
}: {
  panelMeta: Record<string, PanelMeta>;
  positions: Record<string, XYPosition>;
  removed: Record<string, boolean>;
  edges: Edge[];
  customNotes: CanvasNote[];
  spawned: SpawnedPanel[];
  chatIds: string[];
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
      width: panel.width,
      removed: !!removed[id],
    });
  }

  for (const item of spawned.filter((entry) => !removed[entry.id])) {
    const source = panelMeta[item.panelId] ?? PANEL_FALLBACKS[item.panelId];
    nodes.push({
      id: item.id,
      kind: "panel",
      panelId: item.panelId,
      title: source?.title,
      position: positions[item.id] ?? { x: 160, y: 160 },
      width: source?.width,
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
      width: 240,
      removed: !!removed[note.id],
    });
  }

  for (const id of chatIds.filter((entry) => !removed[entry])) {
    nodes.push({
      id,
      kind: "rag",
      title: "RAG Chat",
      position: positions[id] ?? { x: 200, y: 200 },
      width: 460,
      removed: !!removed[id],
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

export function WorkbenchCanvas({
  panels,
  onExit,
}: {
  panels: CanvasPanel[];
  onExit: () => void;
}) {
  const restoredState = useMemo(() => restoreCanvasState(readSavedCanvasLayout()), []);
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const [positions, setPositions] = useState<Record<string, XYPosition>>(restoredState.positions);
  const [removed, setRemoved] = useState<Record<string, boolean>>(restoredState.removed);
  const [edges, setEdges] = useState<Edge[]>(restoredState.edges);
  const [customNotes, setCustomNotes] = useState<CanvasNote[]>(restoredState.customNotes);
  const [spawned, setSpawned] = useState<SpawnedPanel[]>(restoredState.spawned);
  const [chatIds, setChatIds] = useState<string[]>(restoredState.chatIds);
  const [viewport, setViewport] = useState<Viewport | undefined>(restoredState.viewport);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [mode, setMode] = useState<CanvasMode>("select");
  const backendDirtyRef = useRef(false);
  const noteCounter = useRef(restoredState.noteCounter);
  const spawnCounter = useRef(restoredState.spawnCounter);
  const chatCounter = useRef(restoredState.chatCounter);

  const markCanvasDirty = useCallback(() => {
    backendDirtyRef.current = true;
  }, []);

  const applyCanvasState = useCallback((state: RestoredCanvasState) => {
    setPositions(state.positions);
    setRemoved(state.removed);
    setEdges(state.edges);
    setCustomNotes(state.customNotes);
    setSpawned(state.spawned);
    setChatIds(state.chatIds);
    setViewport(state.viewport);
    noteCounter.current = state.noteCounter;
    spawnCounter.current = state.spawnCounter;
    chatCounter.current = state.chatCounter;
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
      saveLocalWorkbenchCanvasLayout(
        toCanvasLayout({
          panelMeta: panelMetaRef.current,
          positions,
          removed,
          edges,
          customNotes,
          spawned,
          chatIds,
          viewport,
        }),
      );
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [positions, removed, edges, customNotes, spawned, chatIds, viewport]);

  useEffect(() => {
    if (!backendDirtyRef.current) return;
    const timeout = window.setTimeout(() => {
      backendDirtyRef.current = false;
      void syncWorkbenchCanvasLayout(
        toCanvasLayout({
          panelMeta: panelMetaRef.current,
          positions,
          removed,
          edges,
          customNotes,
          spawned,
          chatIds,
          viewport,
        }),
      );
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [positions, removed, edges, customNotes, spawned, chatIds, viewport]);

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
    setPositions((prev) => {
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
            position: positions[p.id] ?? { x: 40 + i * 48, y: 40 + i * 48 },
            data: {
              title: p.title,
              element: p.element,
              width: p.width,
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
              position: positions[s.id] ?? { x: 160, y: 160 },
              data: {
                title: src.title,
                element: src.element,
                width: src.width,
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
              element: <AIChatInput />,
              width: 460,
              transparent: true,
              onDelete: () => removeNode(id),
            } satisfies PanelNodeData,
          })),
      ].map((n) => ({ ...n, selected: !!selectedIds[n.id] })),
    [panels, spawned, panelById, customNotes, chatIds, positions, removed, updateNote, removeNode, selectedIds],
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
    },
    [markCanvasDirty],
  );

  const handleReset = useCallback(() => {
    markCanvasDirty();
    setPositions(DEFAULT_POSITIONS);
    setRemoved({});
    setEdges(INITIAL_EDGES);
    setCustomNotes([]);
    setSpawned([]);
    setChatIds([]);
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
    <div className={`fixed inset-0 z-30 wb-canvas ${handMode ? "wb-hand" : "wb-select"}`} style={{ height: "100dvh" }}>
      {/* Cursor feedback for the active tool, scoped to this canvas */}
      <style>{`
        .wb-hand .react-flow__pane { cursor: grab; }
        .wb-hand .react-flow__pane.dragging { cursor: grabbing; }
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
        minZoom={0.2}
        fitView={!restoredState.viewport}
        defaultViewport={restoredState.viewport}
        fitViewOptions={{ maxZoom: 1, padding: 0.2 }}
        style={{ background: "#ffffff" }}
        nodesDraggable={!handMode}
        nodesConnectable={!handMode}
        elementsSelectable={!handMode}
      >
        <Background variant={BackgroundVariant.Dots} gap={28} size={3} color="#c2c8d0" />
        <MiniMap pannable zoomable maskColor="rgba(0,0,0,0.4)" />
        <CanvasToolbar
          mode={mode}
          onSetMode={setMode}
          spawnTypes={SPAWN_TYPES}
          onSpawnPanel={spawnPanel}
          onAddPanel={addNote}
          onAddChat={spawnChat}
          onReset={handleReset}
          onExit={onExit}
        />
      </ReactFlow>
    </div>
  );
}
