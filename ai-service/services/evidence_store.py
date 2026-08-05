"""Verified-evidence store — bank extraction results so work is done once.

Each verified indicator mapping is stored as one reusable row. The same
(economy, indicator, law, quote) is never stored twice (DB-level UNIQUE), and an
*approved* row can be reused on a later run instead of re-extracting. This is the
backend for the vision's "素材入库、避免重复劳动" at the results layer (the raw
documents are already deduped by canvas_file_ingest).

All functions are best-effort: a DB failure returns a safe default and never
raises into the caller doing real work.
"""

from __future__ import annotations

import logging
from typing import Any

from auth import _db_connect
from submission.novelty import normalize_law_name, normalized_quote_hash

logger = logging.getLogger(__name__)

_VALID_STATUS = {"draft", "approved", "rejected"}


def save_evidence(
    economy: str,
    items: list[dict[str, Any]],
    *,
    review_status: str = "draft",
    created_by: str | None = None,
) -> dict[str, int]:
    """Insert verified mappings, skipping ones already banked (dedup).

    Each item: indicator_id, law_name, verbatim_quote, and optionally article,
    source_url, score, source_sha256. Returns {"saved": n, "deduplicated": m}.
    """

    if review_status not in _VALID_STATUS:
        review_status = "draft"
    saved = deduped = 0
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                for it in items:
                    law = str(it.get("law_name") or "").strip()
                    quote = str(it.get("verbatim_quote") or "").strip()
                    indicator = str(it.get("indicator_id") or "").strip()
                    if not (law and quote and indicator):
                        continue
                    cur.execute(
                        "INSERT INTO verified_evidence "
                        "(economy, indicator_id, law_name, law_name_norm, verbatim_quote, "
                        " quote_hash, article, source_url, source_sha256, score, "
                        " review_status, created_by) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (economy, indicator_id, law_name_norm, quote_hash) "
                        "DO NOTHING RETURNING id",
                        (
                            economy, indicator, law, normalize_law_name(law), quote,
                            normalized_quote_hash(quote), it.get("article"),
                            it.get("source_url"), it.get("source_sha256"),
                            it.get("score"), review_status, created_by,
                        ),
                    )
                    if cur.fetchone():
                        saved += 1
                    else:
                        deduped += 1
                conn.commit()
    except Exception as exc:  # noqa: BLE001 — banking must never break the caller
        logger.warning("evidence save failed for %s: %s", economy, exc)
        return {"saved": saved, "deduplicated": deduped}

    _log(economy, saved, deduped, created_by)
    return {"saved": saved, "deduplicated": deduped}


def find_evidence(
    economy: str,
    *,
    indicator_id: str | None = None,
    review_status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return banked evidence for an economy (optionally filtered) — reuse source."""

    limit = max(1, min(int(limit), 1000))
    where = ["economy = %s"]
    params: list[Any] = [economy]
    if indicator_id:
        where.append("indicator_id = %s")
        params.append(indicator_id)
    if review_status:
        where.append("review_status = %s")
        params.append(review_status)
    else:
        # An UNFILTERED read is the reuse path — it must never serve a mapping a
        # human threw out. Rejections are banked (they are the negative half of
        # the review dataset) but are opt-in: ask for them by name with
        # review_status='rejected'. Without this, banking rejections would
        # silently turn "reuse verified evidence" into "reuse anything reviewed".
        where.append("review_status <> 'rejected'")
    params.append(limit)
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, economy, indicator_id, law_name, verbatim_quote, article, "
                    "source_url, score, review_status, created_at "
                    f"FROM verified_evidence WHERE {' AND '.join(where)} "
                    "ORDER BY created_at DESC LIMIT %s",
                    params,
                )
                cols = [d[0] for d in cur.description]
                out = []
                for r in cur.fetchall():
                    item = dict(zip(cols, r))
                    item["id"] = str(item["id"])
                    if item.get("score") is not None:
                        item["score"] = float(item["score"])
                    if item.get("created_at") is not None:
                        item["created_at"] = item["created_at"].isoformat()
                    out.append(item)
                return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("evidence find failed for %s: %s", economy, exc)
        return []


def set_review_status(evidence_id: str, status: str, *, user_id: str | None = None) -> bool:
    """Promote/reject a banked row (draft -> approved/rejected). Returns success."""

    if status not in _VALID_STATUS:
        return False
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE verified_evidence SET review_status = %s, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = %s RETURNING economy, indicator_id",
                    (status, evidence_id),
                )
                row = cur.fetchone()
                conn.commit()
        if not row:
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("evidence status update failed for %s: %s", evidence_id, exc)
        return False

    try:
        from services.activity_log import record_activity

        record_activity(
            "review", user_id=user_id, target_type="evidence", target_id=evidence_id,
            economy=row[0], summary=f"Evidence {status}: {row[1]}",
            detail={"review_status": status},
        )
    except Exception:  # noqa: BLE001
        pass
    return True


def _log(economy, saved, deduped, user_id):
    try:
        from services.activity_log import record_activity

        record_activity(
            "bank_evidence", user_id=user_id, target_type="economy", target_id=economy,
            economy=economy,
            summary=f"Banked {saved} new evidence row(s), reused {deduped} already-known",
            detail={"saved": saved, "deduplicated": deduped},
        )
    except Exception:  # noqa: BLE001
        pass
