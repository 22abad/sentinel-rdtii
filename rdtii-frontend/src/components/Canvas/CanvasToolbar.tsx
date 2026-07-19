import React from "react";
import { Panel, useReactFlow, type XYPosition } from "@xyflow/react";
import { X, StickyNote, Plus, MousePointer2, Lock, RotateCcw, MessageSquare, LayoutList, LayoutGrid } from "lucide-react";
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
  onTidy,
  onSwitchView,
  onExit,
}: {
  mode?: CanvasMode;
  onSetMode?: (mode: CanvasMode) => void;
  spawnTypes?: SpawnType[];
  onSpawnPanel?: (panelId: string, position: XYPosition) => void;
  onAddPanel?: (position: XYPosition) => void;
  onAddChat?: (position: XYPosition) => void;
  onReset?: () => void;
  onTidy?: () => void;
  /** Switch to the traditional (stacked) workbench layout. */
  onSwitchView?: () => void;
  onExit: () => void;
}) {
  const { screenToFlowPosition } = useReactFlow();
  const centerOfView = () =>
    screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 });

  // Swiss dock: square, cream, black hairlines; mono uppercase labels.
  const iconBtn: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: 36,
    height: 36,
    minHeight: 0,   // global `button` rule sets min-height 40 + padding 0 16px —
    padding: 0,     // reset both, or the icon gets squeezed into a 4px content box
    borderRadius: 0,
    border: "none",
    background: "transparent",
    color: "#111827",
    cursor: "pointer",
  };
  const modeBtn = (active: boolean): React.CSSProperties => ({
    ...iconBtn,
    background: active ? "#111827" : "transparent",
    color: active ? "#f3f1ea" : "#111827",
  });
  const textBtn = (color: string): React.CSSProperties => ({
    ...iconBtn,
    width: "auto",
    padding: "0 10px",
    gap: 5,
    color,
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
    fontSize: "0.66rem",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  });
  const divider = <div style={{ width: 1.5, height: 22, background: "#111827", margin: "0 4px" }} />;

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
          borderRadius: 0,
          background: "#f3f1ea",
          border: "2px solid #111827",
          boxShadow: "none",
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
              <MousePointer2 size={15} />
            </button>
            <button
              style={modeBtn(mode === "hand")}
              title="Lock canvas — pan only (H)"
              aria-pressed={mode === "hand"}
              onClick={() => onSetMode("hand")}
            >
              <Lock size={15} />
            </button>
            {divider}
          </>
        )}

        {spawnTypes.length > 0 && onSpawnPanel && (
          <>
            {spawnTypes.map((s) => (
              <button
                key={s.id}
                style={textBtn("#111827")}
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
            <button style={textBtn("#111827")} title="Add blank note" onClick={() => onAddPanel(centerOfView())}>
              <StickyNote size={16} /> Note
            </button>
            {divider}
          </>
        )}

        {onAddChat && (
          <>
            <button style={textBtn("#111827")} title="Add RAG chat" onClick={() => onAddChat(centerOfView())}>
              <MessageSquare size={16} /> RAG
            </button>
            {divider}
          </>
        )}

        {onTidy && (
          <>
            <button style={textBtn("#111827")} title="Tidy: auto-arrange all cards on a clean grid" onClick={onTidy}>
              <LayoutGrid size={15} /> Tidy
            </button>
          </>
        )}
        {onReset && (
          <>
            <button style={textBtn("#111827")} title="Reset layout" onClick={onReset}>
              <RotateCcw size={15} /> Reset
            </button>
            {divider}
          </>
        )}

        {onSwitchView && (
          <>
            <button style={textBtn("#111827")} title="Switch to the traditional layout" onClick={onSwitchView}>
              <LayoutList size={15} /> Classic
            </button>
            {divider}
          </>
        )}

        <button style={textBtn("#9f2d20")} title="Exit canvas" onClick={onExit}>
          <X size={16} /> Exit
        </button>
      </div>
    </Panel>
  );
}
