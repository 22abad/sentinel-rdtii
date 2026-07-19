import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Trash2, FileText, LogIn } from "lucide-react";
import { listCanvasFiles, deleteCanvasFile, type CanvasFileInfo } from "../../services/canvasFiles";
import { useAuth } from "../../hooks/useAuth";

/**
 * Knowledge-base browser — every ingested document (uploads from either
 * page, linked file nodes), with permanent delete. Backs the canvas
 * "Documents" panel.
 */
export function DocumentsPanel() {
  const [docs, setDocs] = useState<CanvasFileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { user, token, login, isLoading: authLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");

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
    // Re-fetch when the auth token changes (e.g. inline sign-in below).
  }, [refresh, token]);

  const needsLogin = !user && /401|not authenticated|log in/i.test(error);

  const handleInlineLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    try {
      await login(email.trim(), password);
      // token change triggers the refresh effect above
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Login failed.");
    }
  };

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

      <div className="nodrag nowheel" style={{ padding: 0, maxHeight: 420, overflowY: "auto" }}>
        {needsLogin ? (
          <form
            onSubmit={handleInlineLogin}
            className="nodrag"
            style={{ display: "flex", flexDirection: "column", gap: 8, padding: "14px 18px", borderTop: "1.5px solid #111827" }}
          >
            <p style={{ margin: 0, fontSize: "0.78rem", color: "#1f2933", fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' }}>
              Sign in to view the knowledge base.
            </p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              autoComplete="email"
              required
              style={{ minHeight: 34, padding: "6px 10px", border: "1.5px solid #111827", borderRadius: 0, fontSize: "0.8rem" }}
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
              style={{ minHeight: 34, padding: "6px 10px", border: "1.5px solid #111827", borderRadius: 0, fontSize: "0.8rem" }}
            />
            {loginError && (
              <p style={{ margin: 0, fontSize: "0.72rem", color: "#9f2d20", fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' }}>
                {loginError}
              </p>
            )}
            <button
              type="submit"
              disabled={authLoading}
              style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 34, padding: "6px 12px", border: "1.5px solid #111827", borderRadius: 0, background: "#111827", color: "#fff", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", cursor: "pointer" }}
            >
              <LogIn size={13} />
              {authLoading ? "Signing in…" : "Sign in"}
            </button>
            <p style={{ margin: 0, fontSize: "0.68rem", color: "#6b675c" }}>
              No account? <a href="/register" style={{ color: "#1f2933", textDecoration: "underline" }}>Register</a>
            </p>
          </form>
        ) : error ? (
          <p style={{ margin: 0, padding: "12px 18px", borderTop: "1.5px solid #9f2d20", fontSize: "0.78rem", color: "#9f2d20", fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' }}>
            {error}
          </p>
        ) : null}
        {!error && !loading && docs.length === 0 && (
          <p style={{ margin: 0, padding: "12px 18px", borderTop: "1.5px solid #111827", fontSize: "0.78rem", color: "#6b675c", fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' }}>
            No documents ingested yet — attach a file in a RAG chat or link a file node.
          </p>
        )}
        {docs.map((doc) => (
          <div
            key={doc.document_id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "10px 18px",
              borderTop: "1.5px solid #111827",
            }}
          >
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
                justifyContent: "center",
                width: 28,
                height: 28,
                minHeight: 0,
                padding: 0,
                borderRadius: 0,
                border: "1.5px solid #9f2d20",
                background: "transparent",
                color: "#9f2d20",
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
