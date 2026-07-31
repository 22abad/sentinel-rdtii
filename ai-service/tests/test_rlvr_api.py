"""The RLVR tracking endpoints read committed reports; they never measure."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import rlvr


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(rlvr, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(rlvr, "REPORT_PATH", tmp_path / "rlvr-measurement.json")
    monkeypatch.setattr(
        rlvr, "HISTORY_PATH", tmp_path / "rlvr-measurement-history.jsonl"
    )
    app = FastAPI()
    app.include_router(rlvr.router)
    return TestClient(app), tmp_path


def _write_report(directory, **overrides):
    report = {
        "generated_at": "2026-07-31T17:00:00+00:00",
        "commit": "abc123",
        "mode": "offline-synthetic-distractors",
        "case_set_sha256": "deadbeef",
        "summary": {"hygiene_top1_rate": 0.875, "cases_measured": 16},
        "by_kind": {"page_dump": {"win_rate": 0.82, "class": "hygiene"}},
        "reward_config": {
            "proxy": {"component_weights": {"citation_exactness": 3.0}},
            "oracle": {"evidence_threshold": 0.8},
        },
        "component_analysis": {
            "citation_exactness": {
                "weight": 3.0,
                "reference_mean": 1.0,
                "distractor_mean": 0.84,
                "discrimination": 0.16,
            }
        },
        "cases": [
            {
                "case_id": "sgp-pdpa-6-4-section-26",
                "candidates": [
                    {
                        "kind": "reference",
                        "proxy": {
                            "total": 1.0,
                            "components": {
                                "citation_exactness": {"value": 1.0, "weight": 3.0}
                            },
                        },
                    }
                ],
            }
        ],
    }
    report.update(overrides)
    (directory / "rlvr-measurement.json").write_text(json.dumps(report))
    return report


def test_missing_report_explains_how_to_generate_it(client):
    api, _ = client
    response = api.get("/api/rlvr/report")
    assert response.status_code == 404
    assert "scripts/rlvr_measure.py" in response.json()["detail"]


def test_report_returns_the_full_document(client):
    api, directory = client
    _write_report(directory)
    body = api.get("/api/rlvr/report").json()
    assert body["summary"]["hygiene_top1_rate"] == 0.875
    assert body["cases"][0]["case_id"] == "sgp-pdpa-6-4-section-26"


def test_summary_keeps_the_per_distractor_breakdown(client):
    """An aggregate that cannot say WHAT regressed is not worth checking."""
    api, directory = client
    _write_report(directory)
    body = api.get("/api/rlvr/report/summary").json()
    assert body["summary"]["hygiene_top1_rate"] == 0.875
    assert body["by_kind"]["page_dump"]["win_rate"] == 0.82
    assert "cases" not in body


def test_summary_carries_the_weights_that_produced_it(client):
    """A rate without its reward config says a score moved, not why."""
    api, directory = client
    _write_report(directory)
    body = api.get("/api/rlvr/report/summary").json()
    weights = body["reward_config"]["proxy"]["component_weights"]
    assert weights["citation_exactness"] == 3.0
    assert body["component_analysis"]["citation_exactness"]["discrimination"] == 0.16


def test_config_endpoint_returns_weights_and_thresholds(client):
    api, directory = client
    _write_report(directory)
    body = api.get("/api/rlvr/config").json()
    assert body["proxy"]["component_weights"]["citation_exactness"] == 3.0
    assert body["oracle"]["evidence_threshold"] == 0.8


def test_components_endpoint_exposes_discrimination(client):
    api, directory = client
    _write_report(directory)
    body = api.get("/api/rlvr/components").json()
    entry = body["components"]["citation_exactness"]
    assert entry["weight"] == 3.0
    assert entry["reference_mean"] == 1.0


def test_case_drilldown_returns_per_component_values(client):
    api, directory = client
    _write_report(directory)
    body = api.get("/api/rlvr/case/sgp-pdpa-6-4-section-26").json()
    components = body["candidates"][0]["proxy"]["components"]
    assert components["citation_exactness"]["value"] == 1.0
    assert components["citation_exactness"]["weight"] == 3.0


def test_unknown_case_lists_the_known_ones(client):
    api, directory = client
    _write_report(directory)
    response = api.get("/api/rlvr/case/does-not-exist")
    assert response.status_code == 404
    assert "sgp-pdpa-6-4-section-26" in response.json()["detail"]["known"]


def test_history_returns_runs_and_respects_limit(client):
    api, directory = client
    lines = [json.dumps({"commit": f"c{i}", "hygiene_top1_rate": i / 10}) for i in range(5)]
    (directory / "rlvr-measurement-history.jsonl").write_text("\n".join(lines) + "\n")
    body = api.get("/api/rlvr/history?limit=2").json()
    assert body["total_runs"] == 5
    assert body["returned"] == 2
    assert body["runs"][-1]["commit"] == "c4"


def test_torn_history_line_does_not_blank_the_view(client):
    """A killed run leaves a partial line; the rest must still render."""
    api, directory = client
    (directory / "rlvr-measurement-history.jsonl").write_text(
        json.dumps({"commit": "good"}) + "\n{\"commit\": \"tor\n"
    )
    body = api.get("/api/rlvr/history").json()
    assert body["total_runs"] == 1
    assert body["runs"][0]["commit"] == "good"


def test_corrupt_report_is_a_500_not_a_silent_empty(client):
    api, directory = client
    (directory / "rlvr-measurement.json").write_text("{not json")
    response = api.get("/api/rlvr/report")
    assert response.status_code == 500
