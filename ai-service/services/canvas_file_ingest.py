"""Canvas file ingest — file bytes -> documents/sections/chunks/embeddings.
Sync half (register_upload): hash, dedup, persist bytes, insert a documents row
as 'processing'. Async half (_save_to_db): extract -> chunk -> embed ->
mark 'processed'. Embeds with the SAME model the query path uses (MiniLM-384).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from auth import _db_connect
from chunker import regex_legal_chunker

# MUST match the query-side model in rag/rag.py (EMBED_MODEL) — both sides
# embed into the same vector space or pgvector similarity is meaningless.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
UPLOAD_DIR = Path(os.getenv("CANVAS_UPLOAD_DIR", "downloads/canvas"))

_model = None


class CanvasIngestError(RuntimeError):
    pass


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _to_pgvector(vec) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


# -- Sync half --------------------------------------------------------------

def register_upload(
    filename: str,
    data: bytes,
    *,
    uploaded_by: str | None = None,
    country_code: str | None = None,
) -> dict:
    """Persist bytes + insert a 'processing' documents row."""
    if not data:
        raise CanvasIngestError("empty upload")

    digest = hashlib.sha256(data).hexdigest()
    source_url = f"canvas://{digest}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{digest}{Path(filename).suffix}"
    if not file_path.exists():
        file_path.write_bytes(data)

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO documents "
                    "(filename, file_path, source_url, country_code, status, uploaded_by) "
                    "VALUES (%s, %s, %s, %s, 'processing', %s) "
                    "ON CONFLICT (source_url) DO NOTHING "
                    "RETURNING id",
                    (filename, str(file_path), source_url, country_code, uploaded_by),
                )
                row = cur.fetchone()
                if row:
                    conn.commit()
                    _log_ingest(str(row[0]), filename, country_code, uploaded_by, deduplicated=False)
                    return {"document_id": str(row[0]), "status": "processing", "deduplicated": False}
                cur.execute(
                    "SELECT id, status FROM documents WHERE source_url = %s",
                    (source_url,),
                )
                existing = cur.fetchone()
    except Exception as exc:
        raise CanvasIngestError(str(exc)) from exc

    if not existing:
        raise CanvasIngestError("document vanished after conflict")
    _log_ingest(str(existing[0]), filename, country_code, uploaded_by, deduplicated=True)
    return {"document_id": str(existing[0]), "status": existing[1], "deduplicated": True}


def _log_ingest(document_id, filename, country_code, uploaded_by, *, deduplicated):
    """Record the ingest in the activity log (best-effort)."""
    try:
        from services.activity_log import record_activity

        record_activity(
            "ingest", user_id=uploaded_by, target_type="document",
            target_id=document_id, economy=country_code,
            summary=(f"Reused already-ingested: {filename}" if deduplicated
                     else f"Ingested new document: {filename}"),
            detail={"filename": filename, "deduplicated": deduplicated},
        )
    except Exception:  # noqa: BLE001 — logging must never break ingest
        pass


def _extract_text(file_path: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from pdf_reader import read_pdf
        return "\n".join(read_pdf(file_path).pages)
    return Path(file_path).read_bytes().decode("utf-8", errors="replace")


def _save_to_db(document_id: str) -> dict:
    """Extract -> chunk -> embed -> mark processed. Marks 'failed' on error.
    Safe to call from a FastAPI BackgroundTask / worker thread."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT filename, file_path, country_code "
                    "FROM documents WHERE id = %s",
                    (document_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise CanvasIngestError(f"document {document_id} not found")
                filename, file_path, country_code = row

                text = _extract_text(file_path, filename)
                chunks = regex_legal_chunker(text)
                if not chunks:
                    raise CanvasIngestError("no extractable text")

                cur.execute(
                    "INSERT INTO document_sections "
                    "(document_id, section_number, raw_text) "
                    "VALUES (%s, '1', %s) RETURNING id",
                    (document_id, text),
                )
                section_id = cur.fetchone()[0]

                # Embed through the pluggable backend (EMBEDDING_PROVIDER):
                # default 'local' keeps the current open-weight, offline model;
                # 'gemini' routes to the free-tier cloud embedder. Returns
                # L2-normalised vectors, same as before.
                from services.embeddings import embed as _embed_texts
                vecs = _embed_texts([c.text for c in chunks])

                for idx, (chunk, vec) in enumerate(zip(chunks, vecs)):
                    cur.execute(
                        "INSERT INTO document_chunks "
                        "(section_id, chunk_index, chunk_text, chunk_metadata) "
                        "VALUES (%s, %s, %s, %s::jsonb) RETURNING id",
                        (section_id, idx, chunk.text,
                         f'{{"start": {chunk.start}, "end": {chunk.end}}}'),
                    )
                    chunk_id = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO chunk_embeddings "
                        "(chunk_id, document_id, country_code, embedding) "
                        "VALUES (%s, %s, %s, %s::vector)",
                        (chunk_id, document_id, country_code, _to_pgvector(vec)),
                    )

                cur.execute(
                    "UPDATE documents SET status = 'processed', updated_at = NOW() "
                    "WHERE id = %s",
                    (document_id,),
                )
                conn.commit()
    except Exception as exc:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status = 'failed', updated_at = NOW() "
                    "WHERE id = %s",
                    (document_id,),
                )
                conn.commit()
        raise CanvasIngestError(str(exc)) from exc

    return {"document_id": document_id, "status": "processed", "chunks": len(chunks)}


def get_status(document_id: str) -> str | None:
    """Current ingestion status of a document ('processing'/'processed'/'failed')."""
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
    return row[0] if row else None


def delete_document(document_id: str) -> bool:
    """Remove an ingested document from the knowledge base.

    Sections, chunks, and embeddings cascade via FK; the stored upload file
    is removed best-effort. Returns False when the id is unknown.
    """
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT file_path FROM documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
            if not row:
                return False
            cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        conn.commit()
    try:
        if row[0]:
            Path(row[0]).unlink(missing_ok=True)
    except OSError:
        pass  # DB rows are gone — a stray file on disk is acceptable
    return True


def list_documents(limit: int = 100) -> list[dict]:
    """Recent ingested documents for the knowledge-base browser panel."""
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, status, country_code, created_at
                FROM   documents
                ORDER  BY created_at DESC
                LIMIT  %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [
        {
            "document_id": str(r[0]),
            "filename": r[1],
            "status": r[2],
            "country_code": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]
