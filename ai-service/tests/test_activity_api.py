"""Tests for the activity-log service and API (no live DB required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


def test_activity_endpoint_returns_items(monkeypatch):
    import services.activity_log as al

    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        return [
            {"id": "1", "action": "ingest", "target_type": "document",
             "target_id": "doc-1", "summary": "Ingested new document: x.pdf",
             "status": "success", "created_at": "2026-07-15T18:00:00"},
        ]

    monkeypatch.setattr(al, "list_activity", fake_list)
    client = TestClient(create_app())

    resp = client.get("/api/activity?action=ingest&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["action"] == "ingest"
    # Query params are forwarded to the service.
    assert captured["action"] == "ingest"
    assert captured["limit"] == 5


def test_activity_endpoint_validates_limit():
    client = TestClient(create_app())
    # limit above the cap is rejected by the query validator.
    assert client.get("/api/activity?limit=9999").status_code == 422
    assert client.get("/api/activity?limit=0").status_code == 422


def test_record_and_list_degrade_gracefully_without_db(monkeypatch):
    # A logging failure must never raise into the caller doing real work.
    import services.activity_log as al

    class _Boom:
        def __enter__(self):
            raise RuntimeError("no database in this test")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(al, "_db_connect", lambda: _Boom())
    assert al.record_activity("extract", target_id="SGP") is None
    assert al.list_activity(limit=5) == []


def test_record_activity_normalizes_bad_status(monkeypatch):
    import services.activity_log as al

    seen = {}

    class _Cur:
        def execute(self, _sql, params):
            seen["status"] = params[5]  # status is the 6th param

        def fetchone(self):
            return ("row-id",)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(al, "_db_connect", lambda: _Conn())
    al.record_activity("extract", status="not-a-real-status")
    assert seen["status"] == "success"  # invalid status falls back to success
