import { useState } from "react"
import { Handle, NodeResizer, Position } from "@xyflow/react";
import { motion, AnimatePresence } from "motion/react"
import { Trash2, FileText, ChevronDown } from "lucide-react";
import { FILE_MIN_SIZE, RESIZER_HANDLE_STYLE, RESIZER_LINE_STYLE } from "./resize";
import type { WorkbenchCanvasSize } from "./types";

export type FileNodeData = {
  fileName?: string;
  fileSize?: number;
  previewUrl?: string,
  fileType?: string,
  /** Pipeline state — set when the file node is linked to the chat node (RAG)
      or to a workbench panel (extraction). */
  ingestStatus?: "uploading" | "ingested" | "failed" | "extracting" | "extracted";
  width?: number;
  height?: number;
  onResize?: (size: WorkbenchCanvasSize) => void;
  onResetSize?: () => void;
  onDelete: () => void;
};

const INGEST_BADGE: Record<
  NonNullable<FileNodeData["ingestStatus"]>,
  { label: string; color: string; bg: string }
> = {
  uploading:  { label: "Ingesting…", color: "#92400e", bg: "#fef3c7" },
  ingested:   { label: "In RAG", color: "#065f46", bg: "#d1fae5" },
  extracting: { label: "Extracting…", color: "#92400e", bg: "#fef3c7" },
  extracted:  { label: "In Source", color: "#1e40af", bg: "#dbeafe" },
  failed:     { label: "Ingest failed", color: "#991b1b", bg: "#fee2e2" },
};

function Preview({ url, type, name }: { url?: string; type?: string; name?: string }) {
  if(!url) {
    return (
    <div style ={{
        padding: 16,
        fontSize: "0.72rem",
        color:"#8a94a3",
        textAlign:"center"
    }}>
      Preview unavailable - re-drop the file to view it.
    </div>
    );
  }

  if(type?.startsWith("image/")) {
    return <img src={url} alt={name ?? "preview"} style={{
      width:"100%",
      display:"block",
      borderRadius:8,
    }}/>
  }

  // pdf, text/* natively rendered by iframe
  return (
    <iframe
      title={name??"document-preview"}
      src={url}
      style={{
        width:"100%",
        height:1280,
        border:"none",
        borderRadius:8,
        background:"#fff",
      }}
    />
  )
}

export function FileNode({ id, data, selected }: { id: string; data: FileNodeData; selected?: boolean }) {
  const [open, setOpen] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const nodeWidth = data.width ?? (open ? 1080 : 260);
  const nodeHeight = data.height ?? (open ? 1280 : 120);
  
  return (
    <div
      style= {{ 
        position: "relative",
        width: nodeWidth,
        height: nodeHeight,
        borderRadius: 13,
        overflow: selected ? "visible" : "hidden",
        background: "#ffffff",
        border: "1px solid #d8dee6",
        boxShadow: selected ? "0 10px 30px rgba(0,0,0,0.22)" : "0 10px 30px rgba(0,0,0,0.12)",
        transition: isResizing ? "none" : "width 0.28s cubic-bezier(0.4, 0, 0.2, 1), height 0.28s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <NodeResizer
        nodeId={id}
        isVisible={selected}
        minWidth={FILE_MIN_SIZE.width}
        minHeight={FILE_MIN_SIZE.height}
        color="#10B981"
        handleStyle={RESIZER_HANDLE_STYLE}
        lineStyle={RESIZER_LINE_STYLE}
        onResizeStart={() => setIsResizing(true)}
        onResize={(_event, params) => data.onResize?.({ width: params.width, height: params.height })}
        onResizeEnd={(_event, params) => {
          setIsResizing(false);
          data.onResize?.({ width: params.width, height: params.height });
        }}
      />

      {/* Floating Delete — matches PanelNode: red pill above the card when selected */}
      {selected && (
        <button
          className="nodrag"
          title="Delete file node"
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

      <Handle type="source" position={Position.Right} style = {{ background: "#10B981" }} />
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 8px 6px 12px",
        background: "#f5f7fa",
        borderBottom: "1px solid rgba(0,0,0,0.08)" 
      }}>
        <FileText size={14} />
        <span style={{
        flex: 1,
        fontSize: "0.82rem",
        fontWeight: 700,
        color: "#26303d"
        }}>
          File
        </span>
        {data.ingestStatus && (
          <span
            title={data.ingestStatus === "failed" ? "Re-link the node to the RAG chat to retry." : undefined}
            style={{
              fontSize: "0.65rem",
              fontWeight: 700,
              padding: "2px 8px",
              borderRadius: 9999,
              whiteSpace: "nowrap",
              color: INGEST_BADGE[data.ingestStatus].color,
              background: INGEST_BADGE[data.ingestStatus].bg,
            }}
          >
            {INGEST_BADGE[data.ingestStatus].label}
          </span>
        )}
        <button
          className="nodrag"
          title={open? "Collapse preview" : "Expand preview"}
          onClick={(e) => {
            e.stopPropagation();
            data.onResetSize?.();
            setOpen((o) => !o); 
          }}
          style={{
            display:"flex",
            alignItems:"center",
            justifyContent:"center",
            height: 18,
            width:18,
            borderRadius: 9999,
            border: "none",
            background: "transparent",
            color: "#5a6573",
            cursor: "pointer",
          }}
        >
          <motion.span 
            animate={{
              rotate:open? 180:0,
            }}
            transition={{
              duration:0.2,
            }}
            style={{
              display:"flex"
            }}
          >
            <ChevronDown size={14}/>
          </motion.span>
        </button>
      </div>
      <div style={{
      padding: 14,
      fontSize: "0.78rem",
      color: "#26303d",
      wordBreak: "break-all"
      }}>
        {data.fileName ?? "-"}
        {data.fileSize != null && (
        <div style={{
            fontSize: "0.7rem",
            color: "#5a6573",
            marginTop: 2
          }}>
            {(data.fileSize / 1024).toFixed(0)} KB
          </div>
        )}
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="preview"
            initial={{
              height:0,
              opacity:0
            }}
            animate={{
              height:"auto",
              opacity:1 
            }}
            exit={{
              height:0,
              opacity:0 
            }}
            transition={{
              duration:0.28,
              ease:[0.4,0,0.2,1]
            }}
            style={{
              overflow:"hidden"
            }}
          >
            <div className="nodrag nowheel"
              style={{
                padding: 10,
                borderTop: "1px solid rgba(0,0,0,0.06)",
              }}
            >
              <Preview url={data.previewUrl}
              type={data.fileType}
              name={ data.fileName } />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
