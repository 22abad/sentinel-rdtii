from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from auth import _db_connect


DEFAULT_SCOPE_KEY = "default"


class CanvasPersistenceError(RuntimeError):
    pass


def get_canvas_layout(user_id: str, scope_key: str = DEFAULT_SCOPE_KEY) -> dict[str, Any] | None:
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT layout, updated_at "
                    "FROM workbench_canvases "
                    "WHERE owner_id = %s AND scope_key = %s",
                    (user_id, normalize_scope_key(scope_key)),
                )
                row = cur.fetchone()
    except Exception as exc:
        raise CanvasPersistenceError(str(exc)) from exc
    if not row:
        return None
    layout, updated_at = row
    return {
        "layout": _json_value(layout),
        "updated_at": _isoformat(updated_at),
    }


def save_canvas_layout(user_id: str, layout: dict[str, Any], scope_key: str = DEFAULT_SCOPE_KEY) -> dict[str, Any]:
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workbench_canvases (owner_id, scope_key, layout) "
                    "VALUES (%s, %s, %s::jsonb) "
                    "ON CONFLICT (owner_id, scope_key) DO UPDATE SET "
                    "layout = EXCLUDED.layout, "
                    "updated_at = NOW() "
                    "RETURNING updated_at",
                    (user_id, normalize_scope_key(scope_key), json.dumps(layout)),
                )
                row = cur.fetchone()
                conn.commit()
    except Exception as exc:
        raise CanvasPersistenceError(str(exc)) from exc
    return {
        "layout": layout,
        "updated_at": _isoformat(row[0] if row else None),
    }


def normalize_scope_key(scope_key: str | None) -> str:
    value = (scope_key or DEFAULT_SCOPE_KEY).strip()
    return value or DEFAULT_SCOPE_KEY


def _json_value(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)
