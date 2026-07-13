from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import main as main_module
from auth import get_current_user


def _override_user():
    return {"user_id": "11111111-1111-1111-1111-111111111111", "role": "viewer", "username": "tester"}


class _FakeCursor:
    def __init__(self, row=None):
        self.row = row
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def test_workbench_canvas_get_returns_empty_layout(monkeypatch):
    from api import workbench_canvas

    monkeypatch.setattr(workbench_canvas.persistence, "get_canvas_layout", lambda _user_id, _scope_key: None)
    main_module.app.dependency_overrides[get_current_user] = _override_user
    try:
        client = TestClient(main_module.app)
        response = client.get("/api/workbench-canvas")
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == {
        "scope_key": "default",
        "layout": None,
        "updated_at": None,
    }


def test_workbench_canvas_put_persists_user_layout(monkeypatch):
    from api import workbench_canvas

    calls = {}

    def fake_save(user_id, layout, scope_key):
        calls["user_id"] = user_id
        calls["layout"] = layout
        calls["scope_key"] = scope_key
        return {"layout": layout, "updated_at": "2026-06-29T12:00:00+00:00"}

    monkeypatch.setattr(workbench_canvas.persistence, "save_canvas_layout", fake_save)
    main_module.app.dependency_overrides[get_current_user] = _override_user
    try:
        client = TestClient(main_module.app)
        response = client.put(
            "/api/workbench-canvas",
            json={
                "scope_key": "default",
                "layout": {
                    "version": 1,
                    "nodes": [{"id": "discovery", "kind": "panel", "position": {"x": 1, "y": 2}}],
                    "edges": [],
                },
            },
        )
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["updated_at"] == "2026-06-29T12:00:00+00:00"
    assert body["layout"]["version"] == 1
    assert calls["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert calls["scope_key"] == "default"


def test_workbench_canvas_get_returns_saved_layout(monkeypatch):
    from api import workbench_canvas

    def fake_get(_user_id, scope_key):
        return {
            "layout": {"version": 1, "nodes": [], "edges": []},
            "updated_at": "2026-06-29T12:01:00+00:00",
        }

    monkeypatch.setattr(workbench_canvas.persistence, "get_canvas_layout", fake_get)
    main_module.app.dependency_overrides[get_current_user] = _override_user
    try:
        client = TestClient(main_module.app)
        response = client.get("/api/workbench-canvas?scope_key=default")
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == {
        "scope_key": "default",
        "layout": {"version": 1, "nodes": [], "edges": []},
        "updated_at": "2026-06-29T12:01:00+00:00",
    }


def test_workbench_canvas_put_normalizes_scope_key(monkeypatch):
    from api import workbench_canvas

    calls = {}

    def fake_save(_user_id, layout, scope_key):
        calls["scope_key"] = scope_key
        return {"layout": layout, "updated_at": None}

    monkeypatch.setattr(workbench_canvas.persistence, "save_canvas_layout", fake_save)
    main_module.app.dependency_overrides[get_current_user] = _override_user
    try:
        client = TestClient(main_module.app)
        response = client.put(
            "/api/workbench-canvas",
            json={
                "scope_key": " research ",
                "layout": {"version": 1, "nodes": [], "edges": []},
            },
        )
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["scope_key"] == "research"
    assert calls["scope_key"] == "research"


def test_workbench_canvas_put_rejects_invalid_layout(monkeypatch):
    from api import workbench_canvas

    main_module.app.dependency_overrides[get_current_user] = _override_user
    try:
        client = TestClient(main_module.app)
        response = client.put(
            "/api/workbench-canvas",
            json={"scope_key": "default", "layout": {"version": 2, "nodes": []}},
        )
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


def test_workbench_canvas_persistence_upserts_layout(monkeypatch):
    from services import workbench_canvas_persistence as persistence

    cursor = _FakeCursor(row=(datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc),))
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(persistence, "_db_connect", lambda: connection)

    result = persistence.save_canvas_layout("user-1", {"version": 1, "nodes": [], "edges": []}, " ")

    assert "ON CONFLICT (owner_id, scope_key)" in cursor.query
    assert cursor.params == ("user-1", "default", '{"version": 1, "nodes": [], "edges": []}')
    assert connection.committed is True
    assert result == {
        "layout": {"version": 1, "nodes": [], "edges": []},
        "updated_at": "2026-06-29T12:00:00+00:00",
    }


def test_workbench_canvas_persistence_reads_json_string(monkeypatch):
    from services import workbench_canvas_persistence as persistence

    cursor = _FakeCursor(row=('{"version": 1, "nodes": [], "edges": []}', "2026-06-29T12:00:00+00:00"))
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(persistence, "_db_connect", lambda: connection)

    result = persistence.get_canvas_layout("user-1", "research")

    assert "FROM workbench_canvases" in cursor.query
    assert cursor.params == ("user-1", "research")
    assert result == {
        "layout": {"version": 1, "nodes": [], "edges": []},
        "updated_at": "2026-06-29T12:00:00+00:00",
    }
