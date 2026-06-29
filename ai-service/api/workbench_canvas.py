from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from services import workbench_canvas_persistence as persistence

router = APIRouter(prefix="/api/workbench-canvas")
MAX_LAYOUT_BYTES = 512_000


class CanvasLayoutResponse(BaseModel):
    scope_key: str = persistence.DEFAULT_SCOPE_KEY
    layout: dict[str, Any] | None = None
    updated_at: str | None = None


class CanvasLayoutSaveRequest(BaseModel):
    scope_key: str = Field(default=persistence.DEFAULT_SCOPE_KEY)
    layout: dict[str, Any]


@router.get("", response_model=CanvasLayoutResponse)
def get_workbench_canvas_layout(
    scope_key: str = Query(default=persistence.DEFAULT_SCOPE_KEY),
    current_user: dict = Depends(get_current_user),
) -> CanvasLayoutResponse:
    normalized_scope_key = persistence.normalize_scope_key(scope_key)
    try:
        saved = persistence.get_canvas_layout(current_user["user_id"], normalized_scope_key)
    except persistence.CanvasPersistenceError as exc:
        raise _storage_error(exc)
    if not saved:
        return CanvasLayoutResponse(scope_key=normalized_scope_key)
    return CanvasLayoutResponse(
        scope_key=normalized_scope_key,
        layout=saved["layout"],
        updated_at=saved.get("updated_at"),
    )


@router.put("", response_model=CanvasLayoutResponse)
def put_workbench_canvas_layout(
    req: CanvasLayoutSaveRequest,
    current_user: dict = Depends(get_current_user),
) -> CanvasLayoutResponse:
    normalized_scope_key = persistence.normalize_scope_key(req.scope_key)
    _validate_layout(req.layout)
    try:
        saved = persistence.save_canvas_layout(current_user["user_id"], req.layout, normalized_scope_key)
    except persistence.CanvasPersistenceError as exc:
        raise _storage_error(exc)
    return CanvasLayoutResponse(
        scope_key=normalized_scope_key,
        layout=saved["layout"],
        updated_at=saved.get("updated_at"),
    )


def _validate_layout(layout: dict[str, Any]) -> None:
    if layout.get("version") != 1 or not isinstance(layout.get("nodes"), list) or not isinstance(layout.get("edges"), list):
        raise HTTPException(
            status_code=422,
            detail="Canvas layout must include version=1, nodes[], and edges[].",
        )
    if len(json.dumps(layout).encode("utf-8")) > MAX_LAYOUT_BYTES:
        raise HTTPException(status_code=413, detail="Canvas layout is too large.")


def _storage_error(exc: persistence.CanvasPersistenceError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Workbench canvas persistence is unavailable. "
            "Ensure the workbench_canvases table exists. "
            f"Original error: {exc}"
        ),
    )
