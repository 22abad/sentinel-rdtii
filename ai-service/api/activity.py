"""Activity-log API — the queryable timeline of every step taken.

Powers a frontend "activity / history" panel: what was done, when, by whom,
and with what result. Read-only; rows are written by the services that do the
work (ingest, extract, discover, review, export) via services.activity_log.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/api/activity")
async def get_activity(
    user_id: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return recent activity rows (newest first), optionally filtered."""
    from services.activity_log import list_activity

    items = list_activity(
        user_id=user_id, target_type=target_type, target_id=target_id,
        action=action, limit=limit, offset=offset,
    )
    return {"items": items, "count": len(items)}
