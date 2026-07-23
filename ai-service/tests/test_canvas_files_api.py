"""Canvas-file upload endpoint — sync vs background ingest (no live DB)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from auth import get_current_user


def _client(monkeypatch, *, register_result=None, save_result=None, save_error=None,
            status: str | None = "processing"):
    """A TestClient with auth stubbed and the ingest layer monkeypatched.

    Records whether _save_to_db ran during the request (sync) so the test can
    tell the inline path from the background-task path.
    """
    import services.canvas_file_ingest as ingest

    calls: dict = {"save_called": False}

    if register_result is not None:
        monkeypatch.setattr(ingest, "register_upload", lambda *a, **k: register_result)
    monkeypatch.setattr(ingest, "get_status", lambda document_id: status)

    def fake_save(document_id):
        calls["save_called"] = True
        if save_error:
            raise ingest.CanvasIngestError(save_error)
        return save_result or {"document_id": document_id, "status": "processed", "chunks": 7}

    monkeypatch.setattr(ingest, "_save_to_db", fake_save)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
    return TestClient(app), calls


def _upload(client, **params):
    return client.post(
        "/api/canvas-files",
        params=params,
        files={"file": ("pdpa.txt", b"An organisation must appoint a data protection officer.", "text/plain")},
    )


def test_sync_ingest_runs_save_inline_and_returns_chunks(monkeypatch):
    client, calls = _client(
        monkeypatch,
        register_result={"document_id": "d1", "status": "processing", "deduplicated": False},
    )
    r = _upload(client, sync="true")
    assert r.status_code == 200
    body = r.json()
    assert calls["save_called"] is True            # fired directly to _save_to_db
    assert body["status"] == "processed"           # final state, not "processing"
    assert body["chunks"] == 7                      # chunk count surfaced to the caller


def test_default_upload_defers_save_to_the_background(monkeypatch):
    client, calls = _client(
        monkeypatch,
        register_result={"document_id": "d1", "status": "processing", "deduplicated": False},
    )
    r = _upload(client)  # no sync param
    assert r.status_code == 200
    # The response is built from register_upload's result BEFORE the background
    # task runs — so it reflects the pre-processing state, not the final one.
    # (TestClient does drain background tasks, so save_called ends up True; the
    # meaningful contract is that the response did not wait for it.)
    assert r.json()["status"] == "processing"
    assert r.json()["chunks"] is None


def test_dedup_skips_processing_entirely(monkeypatch):
    client, calls = _client(
        monkeypatch,
        register_result={"document_id": "d1", "status": "processed", "deduplicated": True},
    )
    r = _upload(client, sync="true")
    assert r.status_code == 200
    assert calls["save_called"] is False           # nothing to (re)ingest
    assert r.json()["deduplicated"] is True


def test_sync_ingest_surfaces_a_processing_error_as_422(monkeypatch):
    client, _ = _client(
        monkeypatch,
        register_result={"document_id": "d1", "status": "processing", "deduplicated": False},
        save_error="no extractable text",
    )
    r = _upload(client, sync="true")
    assert r.status_code == 422
    assert "no extractable text" in r.json()["detail"]


# ── POST /{id}/process — reprocess an existing document ────────────────────


def test_process_reruns_save_for_an_existing_document(monkeypatch):
    client, calls = _client(monkeypatch, status="processing")
    r = client.post("/api/canvas-files/d1/process")
    assert r.status_code == 200
    assert calls["save_called"] is True
    assert r.json()["status"] == "processed"
    assert r.json()["chunks"] == 7


def test_process_unknown_document_is_404(monkeypatch):
    client, calls = _client(monkeypatch, status=None)  # get_status -> None
    r = client.post("/api/canvas-files/nope/process")
    assert r.status_code == 404
    assert calls["save_called"] is False


def test_process_error_is_422(monkeypatch):
    client, _ = _client(monkeypatch, status="processing", save_error="no extractable text")
    r = client.post("/api/canvas-files/d1/process")
    assert r.status_code == 422
    assert "no extractable text" in r.json()["detail"]
