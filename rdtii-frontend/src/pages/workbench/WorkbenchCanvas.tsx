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
} from "../../components/Canvas";
import { AIChatInput } from "../../components/Workbench/ChatInput";

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

export function WorkbenchCanvas({
  panels,
  onExit,
}: {
  panels: CanvasPanel[];
  onExit: () => void;
}) {
  const [positions, setPositions] = useState<Record<string, XYPosition>>(DEFAULT_POSITIONS);
  const [removed, setRemoved] = useState<Record<string, boolean>>({});
  const [edges, setEdges] = useState<Edge[]>(INITIAL_EDGES);
  const [customNotes, setCustomNotes] = useState<{ id: string; title: string; text: string }[]>([]);
  const [spawned, setSpawned] = useState<{ id: string; panelId: string }[]>([]);
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [mode, setMode] = useState<CanvasMode>("select");
  const noteCounter = useRef(0);
  const spawnCounter = useRef(0);
  const chatCounter = useRef(0);

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

  const spawnPanel = useCallback((panelId: string, position: XYPosition) => {
    const n = (spawnCounter.current += 1);
    const id = `${panelId}-copy-${n}`;
    const offset = (n % 6) * 26;
    setSpawned((prev) => [...prev, { id, panelId }]);
    setPositions((p) => ({ ...p, [id]: { x: position.x + offset, y: position.y + offset } }));
  }, []);

  const updateNote = useCallback(
    (id: string, patch: Partial<{ title: string; text: string }>) =>
      setCustomNotes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n))),
    [],
  );

  const addNote = useCallback((position: XYPosition) => {
    const id = `note-${(noteCounter.current += 1)}`;
    setCustomNotes((prev) => [...prev, { id, title: "", text: "" }]);
    setPositions((p) => ({ ...p, [id]: position }));
  }, []);

  const spawnChat = useCallback((position: XYPosition) => {
    const id = `chat-${(chatCounter.current += 1)}`;
    setChatIds((prev) => [...prev, id]);
    setPositions((p) => ({ ...p, [id]: position }));
  }, []);

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
              onDelete: () => setRemoved((r) => ({ ...r, [p.id]: true })),
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
                onDelete: () => setRemoved((r) => ({ ...r, [s.id]: true })),
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
              onDelete: () => setRemoved((r) => ({ ...r, [n.id]: true })),
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
              onDelete: () => setRemoved((r) => ({ ...r, [id]: true })),
            } satisfies PanelNodeData,
          })),
      ].map((n) => ({ ...n, selected: !!selectedIds[n.id] })),
    [panels, spawned, panelById, customNotes, chatIds, positions, removed, updateNote, selectedIds],
  );

  const onNodesChange = useCallback((changes: NodeChange[]) => {
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
      if (c.type === "remove") {
        setRemoved((r) => ({ ...r, [c.id]: true }));
      }
    }
  }, []);

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((es) => applyEdgeChanges(changes, es)),
    [],
  );

  const onConnect = useCallback(
    (c: Connection) => setEdges((es) => addEdge(c, es)),
    [],
  );

  const handleReset = useCallback(() => {
    setPositions(DEFAULT_POSITIONS);
    setRemoved({});
    setEdges(INITIAL_EDGES);
    setCustomNotes([]);
    setSpawned([]);
    setChatIds([]);
  }, []);

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
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        deleteKeyCode={["Delete", "Backspace"]}
        minZoom={0.2}
        fitView
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
