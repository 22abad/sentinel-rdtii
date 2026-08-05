"""GET /api/rlvr/trajectories — the LIVE extraction log, not the golden study.

The endpoint sits on the same router as /report, which is exactly why these
tests exist: the two are different artifacts, and a client that blends them
would present live candidates as if they had been scored against an answer key.
They have not been — with best-of-N unwired every record is a single greedy
draw, so there is no top-1 rate here and none is served.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import rlvr


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "trajectory.jsonl"
    monkeypatch.setattr(rlvr, "TRAJECTORY_PATH", path)
    app = FastAPI()
    app.include_router(rlvr.router)
    return TestClient(app), path


def _record(**overrides):
    record = {
        "schema_version": 2,
        "run_id": "run-a",
        "logged_at": "2026-08-01T01:00:00+00:00",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "document_id": "doc-1",
        "chunk_index": 0,
        "indicator_id": "6.4",
        "quote_hash": "a" * 64,
        "candidate": {"verbatim_quote": "An organisation must not transfer..."},
        "proxy": {"total": 0.8, "passed_gates": True, "components": {}},
        "oracle": None,
        "selected": True,
    }
    record.update(overrides)
    return record


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


# ── empty / missing ──────────────────────────────────────────────────────


def test_missing_log_is_404_with_the_command_to_run(client):
    api, _ = client
    res = api.get("/api/rlvr/trajectories")
    assert res.status_code == 404
    assert "extraction" in res.json()["detail"].lower()


def test_empty_log_is_404_not_an_empty_success(client):
    api, path = client
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n", encoding="utf-8")
    assert api.get("/api/rlvr/trajectories").status_code == 404


# ── records ──────────────────────────────────────────────────────────────


def test_returns_records_newest_first(client):
    api, path = client
    _write(path, [
        _record(indicator_id="6.1", logged_at="2026-08-01T01:00:00+00:00"),
        _record(indicator_id="7.3", logged_at="2026-08-01T02:00:00+00:00"),
    ])
    body = api.get("/api/rlvr/trajectories").json()
    assert [r["indicator_id"] for r in body["records"]] == ["7.3", "6.1"]
    assert body["total"] == 2


def test_torn_last_line_does_not_blank_the_view(client):
    """A run killed mid-write must not 404 a view over good records."""
    api, path = client
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_record()) + "\n" + '{"partial": ', encoding="utf-8"
    )
    body = api.get("/api/rlvr/trajectories").json()
    assert body["total"] == 1


def test_limit_trims_but_total_reports_everything(client):
    api, path = client
    _write(path, [_record(indicator_id=str(i)) for i in range(10)])
    body = api.get("/api/rlvr/trajectories", params={"limit": 3}).json()
    assert body["returned"] == 3
    assert body["total"] == 10


def test_filter_by_run_id(client):
    api, path = client
    _write(path, [_record(run_id="run-a"), _record(run_id="run-b")])
    body = api.get("/api/rlvr/trajectories", params={"run_id": "run-b"}).json()
    assert body["matched"] == 1
    assert body["records"][0]["run_id"] == "run-b"


def test_filter_by_indicator(client):
    api, path = client
    _write(path, [_record(indicator_id="6.4"), _record(indicator_id="7.3")])
    body = api.get("/api/rlvr/trajectories", params={"indicator_id": "7.3"}).json()
    assert body["matched"] == 1


# ── rollup ───────────────────────────────────────────────────────────────


def test_rollup_groups_by_run_and_averages_proxy(client):
    api, path = client
    _write(path, [
        _record(run_id="run-a", proxy={"total": 0.6, "passed_gates": True}),
        _record(run_id="run-a", proxy={"total": 0.8, "passed_gates": True}),
        _record(run_id="run-b", proxy={"total": 1.0, "passed_gates": True}),
    ])
    runs = {r["run_id"]: r for r in api.get("/api/rlvr/trajectories").json()["runs"]}
    assert runs["run-a"]["records"] == 2
    assert runs["run-a"]["mean_proxy"] == pytest.approx(0.7)
    assert runs["run-b"]["mean_proxy"] == pytest.approx(1.0)


def test_rollup_counts_gate_failures(client):
    """A gate failure collapses the reward to 0 — the row worth looking at."""
    api, path = client
    _write(path, [
        _record(proxy={"total": 0.0, "passed_gates": False}),
        _record(proxy={"total": 0.8, "passed_gates": True}),
    ])
    runs = api.get("/api/rlvr/trajectories").json()["runs"]
    assert runs[0]["gate_failures"] == 1


def test_rollup_counts_distinct_documents_and_indicators(client):
    api, path = client
    _write(path, [
        _record(document_id="d1", indicator_id="6.4"),
        _record(document_id="d1", indicator_id="7.3"),
        _record(document_id="d2", indicator_id="6.4"),
    ])
    run = api.get("/api/rlvr/trajectories").json()["runs"][0]
    assert run["documents"] == 2
    assert sorted(run["indicators"]) == ["6.4", "7.3"]


def test_rollup_survives_records_with_no_proxy_total(client):
    api, path = client
    _write(path, [_record(proxy={})])
    assert api.get("/api/rlvr/trajectories").json()["runs"][0]["mean_proxy"] is None


# ── the artifacts must stay distinguishable ──────────────────────────────


def test_payload_says_it_is_not_the_golden_study(client):
    api, path = client
    _write(path, [_record()])
    note = api.get("/api/rlvr/trajectories").json()["note"].lower()
    assert "golden" in note and "k=1" in note


def test_trajectories_does_not_read_the_measurement_report(client, tmp_path, monkeypatch):
    """A missing report must not affect the live view, and vice versa."""
    api, path = client
    monkeypatch.setattr(rlvr, "REPORT_PATH", tmp_path / "does-not-exist.json")
    _write(path, [_record()])
    assert api.get("/api/rlvr/trajectories").status_code == 200
    assert api.get("/api/rlvr/report").status_code == 404
