import { useState } from "react"
import { Handle, Position } from "@xyflow/react";
import { motion, AnimatePresence } from "motion/react"
import { Trash2, FileText, ChevronDown } from "lucide-react";

export type FileNodeData = {
  fileName?: string;
  fileSize?: number;
  previewUrl?: string,
  fileType?: string,
  onDelete: () => void;
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

export function FileNode({ data, selected }: { data: FileNodeData; selected?: boolean }) {
  const [open, setOpen] = useState(false);
  
  return (
    <div
      style= {{ 
        width: open ? 1080 : 260,
        height: open ? 1280 : 120, 
        borderRadius: 13,
        overflow:"hidden",
        background: "#ffffff",
        border: "1px solid #d8dee6",
        boxShadow: selected ? "0 10px 30px rgba(0,0,0,0.22)" : "0 10px 30px rgba(0,0,0,0.12)",
        outline: selected ? "2px solid #10B981" : "none", 
        outlineOffset: 6,
        transition: "width 0.28s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
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
        <button
          className="nodrag"
          title={open? "Collapse preview" : "Expand preview"}
          onClick={(e) => {
            e.stopPropagation();
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
        {selected && (
        <button className="nodrag" title="Delete"
          onClick={(e) => {
            e.stopPropagation();
            data.onDelete() 
          }}
          style={{
              display: "flex",
              alignItems: "center",
              height: 18,
              padding: "0 8px",
              borderRadius: 9999,
              border: "none",
              background: "#b91c1c",
              color: "white",
              cursor: "pointer"
          }}>
            <Trash2 size={11} />
          </button>
        )}
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
