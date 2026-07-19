import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Trash2, FileText } from "lucide-react";
import { listCanvasFiles, deleteCanvasFile, type CanvasFileInfo } from "../../services/canvasFiles";
import { extColor, extLabel } from "./FileCardStack";

/**
 * Knowledge-base browser — every ingested document (uploads from either
 * page, linked file nodes), with permanent delete. Backs the canvas
 * "Documents" panel.
 */
export function DocumentsPanel() {
  const [docs, setDocs] = useState<CanvasFileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setDocs(await listCanvasFiles());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleDelete = async (doc: CanvasFileInfo) => {
    if (!window.confirm(`Delete “${doc.filename}” from the knowledge base? This removes its ingested data for everyone.`)) {
      return;
    }
    try {
      await deleteCanvasFile(doc.document_id);
      setDocs((prev) => prev.filter((d) => d.document_id !== doc.document_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  return (
    <section className="input-panel swiss-form" aria-label="Knowledge base documents">
      <div className="panel-header">
        <div>
          <h2>Documents</h2>
          <p>Everything in the RAG knowledge base.</p>
        </div>
        <button
          type="button"
          className="secondary nodrag"
          onClick={() => void refresh()}
          title="Refresh"
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : undefined} />
          Refresh
        </button>
      </div>

      <div className="nodrag nowheel" style={{ padding: "10px 14px 14px", maxHeight: 420, overflowY: "auto" }}>
        {error && (
          <p style={{ margin: "6px 0", fontSize: "0.8rem", color: "#9f2d20" }}>
            {/401|not authenticated/i.test(error) ? "Please log in to view the knowledge base." : error}
          </p>
        )}
        {!error && !loading && docs.length === 0 && (
          <p style={{ margin: "10px 0", fontSize: "0.78rem", color: "#6b675c", fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' }}>
            No documents ingested yet — attach a file in a RAG chat or link a file node.
          </p>
        )}
        {docs.map((doc) => (
          <div
            key={doc.document_id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 6px",
              borderBottom: "1px solid #111827",
            }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 0,
                background: extColor(doc.filename),
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.55rem",
                fontWeight: 800,
                flexShrink: 0,
              }}
            >
              {extLabel(doc.filename)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{ fontSize: "0.8rem", fontWeight: 600, color: "#1f2933", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={doc.filename}
              >
                {doc.filename || <FileText size={12} />}
              </div>
              <div style={{ fontSize: "0.68rem", color: "#6b675c", marginTop: 1, fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' }}>
                {doc.status}
                {doc.country_code ? ` · ${doc.country_code}` : ""}
                {doc.created_at ? ` · ${new Date(doc.created_at).toLocaleDateString()}` : ""}
              </div>
            </div>
            <button
              type="button"
              title="Delete from the knowledge base (permanent)"
              onClick={() => void handleDelete(doc)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                minHeight: 0,
                padding: "3px 9px",
                borderRadius: 0,
                border: "1.5px solid #9f2d20",
                background: "transparent",
                color: "#9f2d20",
                fontSize: "0.68rem",
                fontWeight: 700,
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              <Trash2 size={11} /> Delete
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
