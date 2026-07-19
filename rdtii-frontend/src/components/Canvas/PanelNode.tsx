import React from "react";
import { Handle, NodeResizer, Position } from "@xyflow/react";
import { Trash2 } from "lucide-react";
import { PANEL_MIN_SIZE, RESIZER_HANDLE_STYLE, RESIZER_LINE_STYLE } from "./resize";
import type { WorkbenchCanvasSize } from "./types";

export type PanelNodeData = {
  title: string;
  element: React.ReactNode;
  width?: number;
  height?: number;
  transparent?: boolean;
  /** Swiss/flat variant: square card, no drop shadow. */
  flat?: boolean;
  onResize?: (size: WorkbenchCanvasSize) => void;
  onDelete: () => void;
};

/**
 * A draggable card wrapping an existing workbench panel. The owning React
 * Flow node may restrict dragging to the panel header so form controls and
 * selectable text in the body keep their native pointer behavior.
 * The body carries `nowheel` so scrolling the panel doesn't zoom the canvas.
 */
export function PanelNode({ id, data, selected }: { id: string; data: PanelNodeData; selected?: boolean }) {
  const bare = !!data.transparent;
  const flat = !!data.flat;
  const nodeWidth = data.width ?? 460;
  // Flat (swiss) panels stick to their content's minimum height — a stored
  // resize height would pin the frame open; width still resizes normally.
  const nodeHeight = flat ? undefined : data.height;
  return (
    // Wrapper is overflow-visible so the floating Delete button (above the card) isn't clipped.
    <div style={{ position: "relative", width: nodeWidth, height: nodeHeight }}>
      <NodeResizer
        nodeId={id}
        isVisible={selected}
        minWidth={PANEL_MIN_SIZE.width}
        minHeight={PANEL_MIN_SIZE.height}
        color={flat ? "#111827" : "#10B981"}
        handleStyle={RESIZER_HANDLE_STYLE}
        lineStyle={RESIZER_LINE_STYLE}
        onResize={(_event, params) => data.onResize?.({ width: params.width, height: params.height })}
      />

      {selected && (
        <button
          className="nodrag"
          title="Delete panel"
          onClick={(e) => {
            e.stopPropagation();
            data.onDelete();
          }}
          style={{
            position: "absolute",
            bottom: "100%",            // sit above the card…
            left: "50%",
            transform: "translateX(-50%)",
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
            height: 24,
            minHeight: 0, // global `button { min-height: 40px }` would inflate the pill
            padding: "0 10px",
            borderRadius: flat ? 0 : 9999,
            border: "none",
            background: "#b91c1c",
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

      {/* Inner card keeps overflow:hidden to clip content to the rounded corners */}
      <div
        style={{
          height: nodeHeight ? "100%" : undefined,
          display: "flex",
          flexDirection: "column",
          borderRadius: flat ? 0 : 36,
          overflow: bare ? "visible" : "hidden",
          // Flat (swiss) panels paint their own cream ground — a white card
          // behind them bled through at the frame edges.
          background: bare || flat ? "transparent" : "#ffffff",
          boxShadow: bare || flat ? "none" : selected ? "0 18px 50px rgba(0,0,0,0.3)" : "0 18px 50px rgba(0,0,0,0.25)",
          transition: "box-shadow 0.12s ease",
        }}
      >
        <Handle type="target" position={Position.Top} style={{ background: flat ? "#111827" : "#10B981" }} />

        {/* Always-grabbable drag strip: sits ABOVE the scroll container, so
            the node can be dragged from its top edge no matter how far the
            panel body is scrolled (the .panel-header handle scrolls away). */}
        <div
          className="wb-drag-strip"
          title="Drag to move"
          style={{
            flex: "0 0 auto",
            height: 18,
            cursor: "grab",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
            background: flat ? "#111827" : "#f3f4f6",
            borderBottom: flat ? "none" : "1px solid #e5e7eb",
          }}
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              style={{ width: 14, height: 2, borderRadius: 1, background: flat ? "#f3f1ea" : "#9ca3af" }}
            />
          ))}
        </div>

        <div
          className="nowheel"
          style={
            bare
              ? { flex: "1 1 auto", minHeight: 0, overflow: "visible" }
              : { flex: "1 1 auto", minHeight: 0, maxHeight: nodeHeight ? undefined : "72vh", overflow: "auto" }
          }
        >
          {data.element}
        </div>

        <Handle type="source" position={Position.Bottom} style={{ background: flat ? "#111827" : "#10B981" }} />
      </div>
    </div>
  );
}
