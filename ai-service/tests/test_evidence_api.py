"""Tests for the verified-evidence store and API (no live DB required)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app


def test_bank_and_query_endpoints(monkeypatch):
    import services.evidence_store as store

    captured = {}

    def fake_save(economy, items, *, review_status="draft", created_by=None):
        captured["economy"] = economy
        captured["n"] = len(items)
        return {"saved": len(items), "deduplicated": 0}

    def fake_find(economy, *, indicator_id=None, review_status=None, limit=200):
        captured["find"] = (economy, indicator_id, review_status)
        return [{"id": "1", "economy": economy, "indicator_id": "P6-I4",
                 "law_name": "PDPA 2012", "verbatim_quote": "...", "score": 1.0,
                 "review_status": review_status or "draft"}]

    monkeypatch.setattr(store, "save_evidence", fake_save)
    monkeypatch.setattr(store, "find_evidence", fake_find)
    client = TestClient(create_app())

    r = client.post("/api/evidence", json={
        "economy": "Singapore",
        "items": [{"indicator_id": "P6-I4", "law_name": "PDPA 2012",
                   "verbatim_quote": "An organisation must not transfer personal data outside Singapore."}],
    })
    assert r.status_code == 200
    assert r.json() == {"saved": 1, "deduplicated": 0}
    assert captured["economy"] == "Singapore" and captured["n"] == 1

    g = client.get("/api/evidence?economy=Singapore&indicator_id=P6-I4&review_status=approved")
    assert g.status_code == 200
    assert g.json()["count"] == 1
    assert captured["find"] == ("Singapore", "P6-I4", "approved")


def test_review_endpoint_rejects_bad_id(monkeypatch):
    import services.evidence_store as store

    monkeypatch.setattr(store, "set_review_status", lambda _id, _status, **k: False)
    client = TestClient(create_app())
    r = client.post("/api/evidence/does-not-exist/review", json={"status": "approved"})
    assert r.status_code == 400


def test_save_evidence_dedup_and_skip_incomplete(monkeypatch):
    import services.evidence_store as store

    inserted = []

    class _Cur:
        def execute(self, _sql, params):
            self._last = params

        def fetchone(self):
            # Simulate: first quote is new, an identical one is a dup.
            quote = self._last[4]
            if quote in inserted:
                return None
            inserted.append(quote)
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

    monkeypatch.setattr(store, "_db_connect", lambda: _Conn())
    items = [
        {"indicator_id": "P6-I4", "law_name": "PDPA", "verbatim_quote": "clause A about cross border transfer"},
        {"indicator_id": "P6-I4", "law_name": "PDPA", "verbatim_quote": "clause A about cross border transfer"},  # dup
        {"indicator_id": "P6-I4", "law_name": "", "verbatim_quote": ""},  # incomplete -> skipped
    ]
    res = store.save_evidence("Singapore", items)
    assert res == {"saved": 1, "deduplicated": 1}


def test_store_degrades_gracefully_without_db(monkeypatch):
    import services.evidence_store as store

    class _Boom:
        def __enter__(self):
            raise RuntimeError("no db")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(store, "_db_connect", lambda: _Boom())
    assert store.save_evidence("SGP", [{"indicator_id": "P6-I4", "law_name": "x", "verbatim_quote": "y clause"}]) == {
        "saved": 0, "deduplicated": 0
    }
    assert store.find_evidence("SGP") == []
    assert store.set_review_status("id", "approved") is False
