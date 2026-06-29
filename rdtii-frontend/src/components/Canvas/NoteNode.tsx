import React from "react";
import { Handle, Position } from "@xyflow/react";
import { Trash2 } from "lucide-react";

export type NoteNodeData = {
  title: string;
  text: string;
  onChange: (patch: Partial<{ title: string; text: string }>) => void;
  onDelete: () => void;
};

/** A blank, user-created panel (sticky-note style) that can be edited inline. */
export function NoteNode({ data, selected }: { data: NoteNodeData; selected?: boolean }) {
  return (
    <div
      style={{
        width: 240,
        borderRadius: 14,
        overflow: "hidden",
        background: "#fff7d6",
        border: "1px solid #e6d98a",
        boxShadow: selected ? "0 10px 30px rgba(0,0,0,0.22)" : "0 10px 30px rgba(0,0,0,0.18)",
        // Selection ring sits OFF the content by `outlineOffset` px — change this to tune the margin.
        outline: selected ? "2px solid #10B981" : "none",
        outlineOffset: 6,
        transition: "box-shadow 0.12s ease, outline-offset 0.12s ease",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: "#d4b106" }} />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 8px 6px 12px",
          background: "#f3e7a3",
          borderBottom: "1px solid rgba(0,0,0,0.08)",
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
            fontSize: "0.82rem",
            fontWeight: 700,
            color: "#3f3a1a",
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
              padding: "0 8px",
              borderRadius: 9999,
              border: "none",
              background: "#b91c1c",
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
          minHeight: 120,
          border: "none",
          resize: "none",
          background: "transparent",
          outline: "none",
          padding: "10px 12px",
          fontSize: "0.85rem",
          color: "#403a1a",
          fontFamily: "inherit",
        }}
      />

      <Handle type="source" position={Position.Bottom} style={{ background: "#d4b106" }} />
    </div>
  );
}
