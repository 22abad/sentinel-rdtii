"""Activity log — a general, queryable audit trail of every step.

Every meaningful action (ingest, extract, discover, review, export) writes one
row so the frontend can render an activity timeline and a reviewer can retrace
exactly what was done, when, by whom, and with what result. Logging never breaks
the caller: a failed write is swallowed (the work is more important than the log
line), but is surfaced in the return value for tests.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from auth import _db_connect

logger = logging.getLogger(__name__)

_VALID_STATUS = {"success", "failed", "partial"}


def record_activity(
    action: str,
    *,
    user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    economy: str | None = None,
    status: str = "success",
    summary: str | None = None,
    detail: dict[str, Any] | None = None,
) -> str | None:
    """Insert one activity row. Returns the new row id, or None on failure.

    Best-effort: never raises. A logging failure must not abort the real work.
    """

    if status not in _VALID_STATUS:
        status = "success"
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO activity_log "
                    "(user_id, action, target_type, target_id, economy, status, summary, detail) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        user_id, action, target_type, target_id, economy, status,
                        summary, json.dumps(detail) if detail is not None else None,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001 — logging must never break the caller
        logger.warning("activity_log write failed for action=%s: %s", action, exc)
        return None


def list_activity(
    *,
    user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    action: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return recent activity rows (newest first), optionally filtered."""

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    where: list[str] = []
    params: list[Any] = []
    for col, val in (
        ("user_id", user_id), ("target_type", target_type),
        ("target_id", target_id), ("action", action),
    ):
        if val:
            where.append(f"{col} = %s")
            params.append(val)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, user_id, action, target_type, target_id, economy, "
                    "status, summary, detail, created_at "
                    f"FROM activity_log {clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    params,
                )
                cols = [d[0] for d in cur.description]
                rows = []
                for r in cur.fetchall():
                    item = dict(zip(cols, r))
                    for k in ("id", "user_id", "target_id"):
                        if item.get(k) is not None:
                            item[k] = str(item[k])
                    if item.get("created_at") is not None:
                        item["created_at"] = item["created_at"].isoformat()
                    rows.append(item)
                return rows
    except Exception as exc:  # noqa: BLE001
        logger.warning("activity_log read failed: %s", exc)
        return []
