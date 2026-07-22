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
        from rag.tables import append_tables

        text = "\n".join(read_pdf(file_path).pages)
        # Append reconstructed tables so schedules become clean, retrievable
        # chunks instead of the cell-by-cell jumble in the flat text layer.
        return append_tables(text, file_path)
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

                # Country verification — never trust the uploader's preset
                # blindly (the Source panel defaults to CHN and that default
                # was historically stamped onto every ingest).
                detected, confidence = _detect_country(text)
                if detected and confidence >= 0.7:
                    if not country_code and detected in _registered_country_codes(cur):
                        # FK guard: only registered (ESCAP) codes are storable.
                        country_code = detected
                        cur.execute(
                            "UPDATE documents SET country_code = %s WHERE id = %s",
                            (country_code, document_id),
                        )
                    elif country_code != detected:
                        # Keep the preset (it may be deliberate) but leave an
                        # audit trail — `stn audit-countries` surfaces these.
                        print(
                            f"[canvas-ingest] country mismatch for {filename}: "
                            f"stored={country_code} detected={detected} ({confidence:.2f})"
                        )

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


# ── Country verification ─────────────────────────────────────────────────


def _detect_country(text: str, source_url: str = "") -> tuple[str | None, float]:
    """Detect the document's country (ISO-3, confidence) — URL first, then text."""
    try:
        from country_detector import detect_country

        result = detect_country(text=text[:8000], source_url=source_url)
        return result.get("code"), float(result.get("confidence") or 0.0)
    except Exception:  # noqa: BLE001 — detection must never break ingest
        return None, 0.0


def _registered_country_codes(cur) -> set[str]:
    cur.execute("SELECT code FROM countries")
    return {r[0] for r in cur.fetchall()}


def audit_country_codes(fix: bool = False, confidence_threshold: float = 0.7) -> dict:
    """Compare every document's stored country_code against text detection.

    The Source panel's CHN default was historically stamped onto ingests
    unchecked; this measures (and with fix=True repairs) the damage. Fixes
    propagate to chunk_embeddings.country_code, which retrieval filters on.
    Detected codes outside the `countries` registry (e.g. NGA) are reported
    but never written — the FK would reject them.
    """
    report: list[dict] = []
    with _db_connect() as conn:
        with conn.cursor() as cur:
            valid_codes = _registered_country_codes(cur)
            cur.execute(
                """
                SELECT d.id, d.filename, d.country_code, d.source_url,
                       COALESCE(
                         (SELECT ds.raw_text FROM document_sections ds
                          WHERE ds.document_id = d.id LIMIT 1), ''
                       )
                FROM documents d
                ORDER BY d.created_at DESC
                """
            )
            rows = cur.fetchall()
            for doc_id, filename, stored, source_url, text in rows:
                url = source_url if source_url and not source_url.startswith("canvas://") else ""
                detected, confidence = _detect_country(text or "", url)
                entry = {
                    "document_id": str(doc_id),
                    "filename": filename,
                    "stored": stored,
                    "detected": detected,
                    "confidence": round(confidence, 2),
                    "verdict": "",
                    "fixed": False,
                }
                confident = bool(detected) and confidence >= confidence_threshold
                if not confident:
                    entry["verdict"] = "undetected"
                elif detected == stored:
                    entry["verdict"] = "match"
                elif detected not in valid_codes:
                    entry["verdict"] = "detected-not-in-registry"
                elif not stored:
                    entry["verdict"] = "missing-stored"
                else:
                    entry["verdict"] = "MISMATCH"
                if fix and entry["verdict"] in ("MISMATCH", "missing-stored"):
                    cur.execute(
                        "UPDATE documents SET country_code = %s WHERE id = %s",
                        (detected, doc_id),
                    )
                    cur.execute(
                        "UPDATE chunk_embeddings SET country_code = %s WHERE document_id = %s",
                        (detected, doc_id),
                    )
                    entry["fixed"] = True
                report.append(entry)
        if fix:
            conn.commit()
    summary = {
        "documents": len(report),
        "match": sum(1 for e in report if e["verdict"] == "match"),
        "mismatch": sum(1 for e in report if e["verdict"] == "MISMATCH"),
        "missing_stored": sum(1 for e in report if e["verdict"] == "missing-stored"),
        "undetected": sum(1 for e in report if e["verdict"] == "undetected"),
        "not_in_registry": sum(1 for e in report if e["verdict"] == "detected-not-in-registry"),
        "fixed": sum(1 for e in report if e["fixed"]),
    }
    return {"summary": summary, "report": report}
