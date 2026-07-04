import React from "react";
import { Handle, Position } from "@xyflow/react";
import { Trash2 } from "lucide-react";

export type PanelNodeData = {
  title: string;
  element: React.ReactNode;
  width?: number;
  transparent?: boolean;
  onDelete: () => void;
};

/**
 * A draggable card wrapping an existing workbench panel.
 * The body carries `nowheel` so scrolling the panel doesn't zoom the canvas.
 */
export function PanelNode({ data, selected }: { data: PanelNodeData; selected?: boolean }) {
  const bare = !!data.transparent;
  return (
    // Wrapper is overflow-visible so the floating Delete button (above the card) isn't clipped.
    <div style={{ position: "relative", width: data.width ?? 460 }}>
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
            marginBottom: 12,          // …clearing the outlineOffset (6px) selection ring
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
            height: 24,
            padding: "0 10px",
            borderRadius: 9999,
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
          borderRadius: 36,
          overflow: bare ? "visible" : "hidden",
          background: bare ? "transparent" : "#ffffff",
          boxShadow: bare ? "none" : selected ? "0 18px 50px rgba(0,0,0,0.3)" : "0 18px 50px rgba(0,0,0,0.25)",
          outline: selected ? "2px solid #10B981" : "none",
          outlineOffset: 6, // Margin on selection
          transition: "box-shadow 0.12s ease, outline-offset 0.12s ease",
        }}
      >
        <Handle type="target" position={Position.Top} style={{ background: "#10B981" }} />

        <div className="nowheel" style={bare ? { overflow: "visible" } : { maxHeight: "72vh", overflow: "auto" }}>
          {data.element}
        </div>

        <Handle type="source" position={Position.Bottom} style={{ background: "#10B981" }} />
      </div>
    </div>
  );
}
