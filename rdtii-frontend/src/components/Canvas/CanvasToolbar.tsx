import React from "react";
import { Panel, useReactFlow, type XYPosition } from "@xyflow/react";
import { X, StickyNote, Plus, MousePointer2, Lock, RotateCcw, MessageSquare } from "lucide-react";
import type { CanvasMode, SpawnType } from "./types";

/**
 * Reusable FigJam-style floating dock, anchored to the bottom-center of a canvas.
 * Must be rendered as a child of <ReactFlow> so it can use `useReactFlow()`.
 *
 * Every action section is optional — pass only the props for the controls you
 * want, and they render conditionally:
 *  - mode + onSetMode → Select/Hand tool toggle
 *  - spawnTypes + onSpawnPanel → one "+ <label>" button per type
 *  - onAddPanel → blank "Note" button
 *  - onReset → "Reset" button
 *  - onExit (required) → "Exit" button
 */
export function CanvasToolbar({
  mode,
  onSetMode,
  spawnTypes = [],
  onSpawnPanel,
  onAddPanel,
  onAddChat,
  onReset,
  onExit,
}: {
  mode?: CanvasMode;
  onSetMode?: (mode: CanvasMode) => void;
  spawnTypes?: SpawnType[];
  onSpawnPanel?: (panelId: string, position: XYPosition) => void;
  onAddPanel?: (position: XYPosition) => void;
  onAddChat?: (position: XYPosition) => void;
  onReset?: () => void;
  onExit: () => void;
}) {
  const { screenToFlowPosition } = useReactFlow();
  const centerOfView = () =>
    screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 });

  const iconBtn: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: 36,
    height: 36,
    borderRadius: 10,
    border: "none",
    background: "transparent",
    color: "#374151",
    cursor: "pointer",
  };
  const modeBtn = (active: boolean): React.CSSProperties => ({
    ...iconBtn,
    background: active ? "#e6f4f1" : "transparent",
    color: active ? "#0f766e" : "#374151",
  });
  const textBtn = (color: string): React.CSSProperties => ({
    ...iconBtn,
    width: "auto",
    padding: "0 10px",
    gap: 5,
    color,
    fontSize: "0.82rem",
    fontWeight: 600,
  });
  const divider = <div style={{ width: 1, height: 22, background: "#e5e7eb", margin: "0 4px" }} />;

  return (
    <Panel position="bottom-center">
      <div
        className="nodrag nowheel"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          padding: 6,
          marginBottom: 12,
          borderRadius: 14,
          background: "#ffffff",
          border: "1px solid #e5e7eb",
          boxShadow: "0 8px 30px rgba(0,0,0,0.18)",
        }}
      >
        {mode && onSetMode && (
          <>
            <button
              style={modeBtn(mode === "select")}
              title="Interact — V"
              aria-pressed={mode === "select"}
              onClick={() => onSetMode("select")}
            >
              <MousePointer2 size={18} />
            </button>
            <button
              style={modeBtn(mode === "hand")}
              title="Lock canvas — pan only (H)"
              aria-pressed={mode === "hand"}
              onClick={() => onSetMode("hand")}
            >
              <Lock size={18} />
            </button>
            {divider}
          </>
        )}

        {spawnTypes.length > 0 && onSpawnPanel && (
          <>
            {spawnTypes.map((s) => (
              <button
                key={s.id}
                style={textBtn("#0f766e")}
                title={`Add ${s.label} panel`}
                onClick={() => onSpawnPanel(s.id, centerOfView())}
              >
                <Plus size={15} /> {s.label}
              </button>
            ))}
            {divider}
          </>
        )}

        {onAddPanel && (
          <>
            <button style={textBtn("#6b7280")} title="Add blank note" onClick={() => onAddPanel(centerOfView())}>
              <StickyNote size={16} /> Note
            </button>
            {divider}
          </>
        )}

        {onAddChat && (
          <>
            <button style={textBtn("#7c3aed")} title="Add RAG chat" onClick={() => onAddChat(centerOfView())}>
              <MessageSquare size={16} /> RAG
            </button>
            {divider}
          </>
        )}

        {onReset && (
          <>
            <button style={textBtn("#6b7280")} title="Reset layout" onClick={onReset}>
              <RotateCcw size={15} /> Reset
            </button>
            {divider}
          </>
        )}

        <button style={textBtn("#b91c1c")} title="Exit canvas" onClick={onExit}>
          <X size={16} /> Exit
        </button>
      </div>
    </Panel>
  );
}
