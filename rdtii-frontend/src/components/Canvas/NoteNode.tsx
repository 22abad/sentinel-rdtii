import React from "react";
import { Handle, NodeResizer, Position } from "@xyflow/react";
import { Trash2 } from "lucide-react";
import { NOTE_MIN_SIZE, RESIZER_HANDLE_STYLE, RESIZER_LINE_STYLE } from "./resize";
import type { WorkbenchCanvasSize } from "./types";

export type NoteNodeData = {
  title: string;
  text: string;
  onChange: (patch: Partial<{ title: string; text: string }>) => void;
  width?: number;
  height?: number;
  onResize?: (size: WorkbenchCanvasSize) => void;
  onDelete: () => void;
};

/** A blank, user-created panel (sticky-note style) that can be edited inline. */
export function NoteNode({ id, data, selected }: { id: string; data: NoteNodeData; selected?: boolean }) {
  const nodeWidth = data.width ?? 240;
  const nodeHeight = data.height;
  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        width: nodeWidth,
        height: nodeHeight,
        borderRadius: 0, // Swiss note: square, specimen yellow, black frame
        overflow: selected ? "visible" : "hidden",
        background: "#f7d445",
        border: "1.5px solid #111827",
        boxShadow: "none",
      }}
    >
      <NodeResizer
        nodeId={id}
        isVisible={selected}
        minWidth={NOTE_MIN_SIZE.width}
        minHeight={NOTE_MIN_SIZE.height}
        color="#111827"
        handleStyle={RESIZER_HANDLE_STYLE}
        lineStyle={RESIZER_LINE_STYLE}
        onResize={(_event, params) => data.onResize?.({ width: params.width, height: params.height })}
      />

      <Handle type="target" position={Position.Top} style={{ background: "#111827" }} />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 8px 6px 12px",
          background: "transparent",
          borderBottom: "1.5px solid #111827",
        }}
      >
        <input
          className="nodrag"
          value={data.title}
          placeholder="Title"
          onChange={(e) => data.onChange({ title: e.target.value })}
          style={{
            flex: 1,
            minWidth: 0,
            border: "none",
            background: "transparent",
            outline: "none",
            fontSize: "0.8rem",
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            color: "#111827",
          }}
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
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
              height: 18,
              minHeight: 0, // global `button { min-height: 40px }` would inflate it
              padding: "0 8px",
              borderRadius: 0,
              border: "none",
              background: "#9f2d20",
              color: "white",
              fontSize: "0.66rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <Trash2 size={11} /> Delete
          </button>
        )}
      </div>

      <textarea
        className="nodrag nowheel"
        value={data.text}
        placeholder="Write something…"
        onChange={(e) => data.onChange({ text: e.target.value })}
        style={{
          display: "block",
          width: "100%",
          flex: nodeHeight ? 1 : undefined,
          minHeight: 120,
          border: "none",
          resize: "none",
          background: "transparent",
          outline: "none",
          padding: "10px 12px",
          fontSize: "0.85rem",
          color: "#111827",
          fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
        }}
      />

      <Handle type="source" position={Position.Bottom} style={{ background: "#111827" }} />
    </div>
  );
}
