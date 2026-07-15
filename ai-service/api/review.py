from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from schemas import ReviewRequest

router = APIRouter()


@router.post("/api/mappings/review")
def review_mapping(req: ReviewRequest):
    db_config = {
        "dbname": os.getenv("POSTGRES_DB", "rdtii"),
        "user": os.getenv("POSTGRES_USER", "rdtii_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "rdtii_password"),
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
    }

    import psycopg2

    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO countries (code, name) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING",
            (req.country_code, req.country_code),
        )

        filename = req.mapping.source_legislation or "Web Extraction"
        source_url = req.mapping.source_url or "Unknown"

        cur.execute(
            "INSERT INTO documents (filename, source_url, country_code, status, file_path) "
            "VALUES (%s, %s, %s, 'processed', 'N/A') "
            "ON CONFLICT (source_url) DO NOTHING RETURNING id",
            (filename, source_url, req.country_code),
        )
        doc_res = cur.fetchone()
        if not doc_res:
            cur.execute("SELECT id FROM documents WHERE source_url = %s", (source_url,))
            doc_id = cur.fetchone()[0]
        else:
            doc_id = doc_res[0]

        cur.execute(
            "INSERT INTO document_sections (document_id, raw_text) VALUES (%s, %s) RETURNING id",
            (doc_id, req.mapping.verbatim_quote),
        )
        section_id = cur.fetchone()[0]

        cur.execute("SELECT pillar_id FROM rdtii_pillars WHERE indicator_id = %s LIMIT 1", (req.mapping.indicator,))
        pillar_row = cur.fetchone()
        if not pillar_row:
            cur.execute(
                "INSERT INTO rdtii_pillars (pillar_number, pillar_name, indicator_id, criterion_id, criterion_name) "
                "VALUES (%s, %s, %s, 'AUTO', 'Auto-generated') RETURNING pillar_id",
                (req.mapping.pillar, f"Pillar {req.mapping.pillar}", req.mapping.indicator),
            )
            pillar_uuid = cur.fetchone()[0]
        else:
            pillar_uuid = pillar_row[0]

        cur.execute(
            "INSERT INTO extracted_obligations (section_id, extracted_text, status) "
            "VALUES (%s, %s, %s) RETURNING id",
            (section_id, req.mapping.verbatim_quote, "reviewed" if req.decision == "approved" else "rejected"),
        )
        obligation_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO regulation_mappings (obligation_id, pillar_id, compliance_status) "
            "VALUES (%s, %s, %s) RETURNING id",
            (obligation_id, pillar_uuid, "compliant" if req.decision == "approved" else "non-compliant"),
        )
        mapping_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO audit_trail (mapping_id, source_section_id, highlight_start, highlight_end) "
            "VALUES (%s, %s, %s, %s)",
            (mapping_id, section_id, req.mapping.quote_start, req.mapping.quote_end),
        )

        conn.commit()
        cur.close()
        _bank_and_log(req, str(mapping_id))
        return {"status": "success", "mapping_id": str(mapping_id)}
    except Exception as exc:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database transaction failed: {str(exc)}")
    finally:
        if conn:
            conn.close()


def _bank_and_log(req: ReviewRequest, mapping_id: str) -> None:
    """On approval, bank the mapping into the reusable evidence store; always log.

    This is the "review approves -> promote to the reusable baseline" step: an
    approved mapping becomes reusable evidence a later run can serve instead of
    re-extracting. Best-effort — never fails the review.
    """
    m = req.mapping
    try:
        from submission.schema import indicator_to_rdtii_code
        indicator = indicator_to_rdtii_code(str(m.indicator))
    except Exception:  # noqa: BLE001
        indicator = str(getattr(m, "indicator", ""))
    try:
        score = float(getattr(m, "score", None)) if getattr(m, "score", None) is not None else None
    except (TypeError, ValueError):
        score = None

    if req.decision == "approved":
        try:
            from services.evidence_store import save_evidence

            save_evidence(
                req.country_code,
                [{
                    "indicator_id": indicator,
                    "law_name": m.source_legislation or "",
                    "verbatim_quote": m.verbatim_quote or "",
                    "article": getattr(m, "article_clause", None),
                    "source_url": m.source_url or None,
                    "score": score,
                }],
                review_status="approved",
            )
        except Exception:  # noqa: BLE001 — banking must never break the review
            pass
    try:
        from services.activity_log import record_activity

        record_activity(
            "review", target_type="mapping", target_id=mapping_id, economy=req.country_code,
            summary=f"Mapping {req.decision}: {indicator} — {(m.source_legislation or '')[:40]}",
            detail={"decision": req.decision, "indicator": indicator},
        )
    except Exception:  # noqa: BLE001
        pass

