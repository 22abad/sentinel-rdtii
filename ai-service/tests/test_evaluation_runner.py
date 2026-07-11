from __future__ import annotations

import json
import types
from pathlib import Path

import pytest
import httpx
import requests

from evaluation.models import GoldenCase
from discovery.schemas import LegalCandidate
from evaluation.runner import (
    _aggregate_ocr_usage,
    _candidate_rank,
    _combined_cost,
    _find_document_candidate,
    _is_transient_error,
    _retry_transient,
    _run_live_discovery,
    load_dataset,
    run_evaluation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.anyio
async def test_offline_runner_uses_real_pipeline_and_writes_both_reports(tmp_path):
    output_path = tmp_path / "offline-report.json"
    report = await run_evaluation(
        repo_root=REPO_ROOT,
        mode="offline",
        cases_path=REPO_ROOT / "evaluation/golden/cases.jsonl",
        documents_path=REPO_ROOT / "evaluation/golden/documents.jsonl",
        offline_responses_path=(
            REPO_ROOT / "evaluation/fixtures/offline-provider-responses.jsonl"
        ),
        output_path=output_path,
        include_pending=True,
    )

    assert output_path.exists()
    assert output_path.with_suffix(".md").exists()
    assert report["metadata"]["mode"] == "offline"
    assert report["metadata"]["include_pending"] is True
    assert report["dataset"]["cases_evaluated"] == 8
    assert report["dataset"]["documents_evaluated"] == 5
    assert report["mapping_evaluation"]["aggregate"]["predicted_mappings"] == 2
    assert report["mapping_evaluation"]["aggregate"]["mapping_recall"] == pytest.approx(1 / 3)
    assert report["source_failures"] == []
    assert report["usage"]["llm_calls"] == 0
    assert report["ocr_usage"]["vision_calls"] == 0
    assert report["cost_usd"]["known_llm_ocr_subtotal"] == 0.0
    assert report["cost_usd"]["search"] == 0.0
    assert report["cost_usd"]["total"] == 0.0
    assert report["timing_seconds"]["mapping"] >= 0
    assert report["timing_seconds"]["total"] >= report["timing_seconds"]["mapping"]

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["metadata"]["case_set_sha256"]
    markdown = output_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "Development-only report" in markdown
    assert "False negatives: 4" in markdown


@pytest.mark.anyio
async def test_pending_cases_are_excluded_by_default(tmp_path):
    with pytest.raises(ValueError, match="No approved golden cases"):
        await run_evaluation(
            repo_root=REPO_ROOT,
            mode="offline",
            cases_path=REPO_ROOT / "evaluation/golden/cases.jsonl",
            documents_path=REPO_ROOT / "evaluation/golden/documents.jsonl",
            offline_responses_path=(
                REPO_ROOT / "evaluation/fixtures/offline-provider-responses.jsonl"
            ),
            output_path=tmp_path / "should-not-exist.json",
        )


@pytest.mark.anyio
async def test_single_country_report_renders_complete_group_metrics(tmp_path):
    output_path = tmp_path / "mys-report.json"
    report = await run_evaluation(
        repo_root=REPO_ROOT,
        mode="offline",
        cases_path=REPO_ROOT / "evaluation/golden/cases.jsonl",
        documents_path=REPO_ROOT / "evaluation/golden/documents.jsonl",
        offline_responses_path=(
            REPO_ROOT / "evaluation/fixtures/offline-provider-responses.jsonl"
        ),
        output_path=output_path,
        countries={"MYS"},
        include_pending=True,
    )

    assert report["mapping_evaluation"]["per_country"]["MYS"]["mapping_precision"] == 1.0
    assert "| MYS | 100.00% |" in output_path.with_suffix(".md").read_text()


@pytest.mark.anyio
async def test_predictions_matching_pending_cases_do_not_pollute_approved_metrics(tmp_path):
    source_cases = [
        json.loads(line)
        for line in (REPO_ROOT / "evaluation/golden/cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    pending = next(
        case for case in source_cases
        if case["case_id"] == "mys-companies-7-3-section-245"
    )
    approved = {
        **pending,
        "case_id": "mys-companies-6-4-approved-negative",
        "indicator_id": "6.4",
        "should_map": False,
        "expected_raw_score": 0.0,
        "expected_cat_score": 0.0,
        "review": {
                "status": "approved",
                "reviewer_role": "Substantive Lead",
                "reviewed_at": "2026-07-11",
                "framework_version": "RDTII 2.1",
                "notes": "Regression fixture",
        },
    }
    selected = [pending, approved]
    cases_path = tmp_path / "mixed-review-cases.jsonl"
    cases_path.write_text(
        "\n".join(json.dumps(case) for case in selected) + "\n",
        encoding="utf-8",
    )

    report = await run_evaluation(
        repo_root=REPO_ROOT,
        mode="offline",
        cases_path=cases_path,
        documents_path=REPO_ROOT / "evaluation/golden/documents.jsonl",
        offline_responses_path=(
            REPO_ROOT / "evaluation/fixtures/offline-provider-responses.jsonl"
        ),
        output_path=tmp_path / "mixed-review-report.json",
    )

    aggregate = report["mapping_evaluation"]["aggregate"]
    assert aggregate["predicted_mappings"] == 0
    assert aggregate["mapping_precision"] == 1.0
    assert len(report["dataset"]["excluded_predictions"]) == 1


@pytest.mark.anyio
async def test_offline_document_failure_is_reported_without_aborting_run(
    tmp_path,
    monkeypatch,
):
    async def fail_extraction(*_args, **_kwargs):
        raise RuntimeError("broken offline fixture")

    monkeypatch.setattr("evaluation.runner.run_extraction", fail_extraction)
    output_path = tmp_path / "failed-document-report.json"
    report = await run_evaluation(
        repo_root=REPO_ROOT,
        mode="offline",
        cases_path=REPO_ROOT / "evaluation/golden/cases.jsonl",
        documents_path=REPO_ROOT / "evaluation/golden/documents.jsonl",
        offline_responses_path=(
            REPO_ROOT / "evaluation/fixtures/offline-provider-responses.jsonl"
        ),
        output_path=output_path,
        countries={"MYS"},
        include_pending=True,
    )

    assert output_path.exists()
    assert report["source_failures"][0]["stage"] == "extraction"
    assert report["source_failures"][0]["url"].startswith("https://")
    assert report["mapping_evaluation"]["aggregate"]["false_negatives"] == 1


@pytest.mark.anyio
async def test_live_discovery_rejects_unsupported_indicator_before_search():
    cases, documents = load_dataset(
        repo_root=REPO_ROOT,
        cases_path=REPO_ROOT / "evaluation/golden/cases.jsonl",
        documents_path=REPO_ROOT / "evaluation/golden/documents.jsonl",
    )
    source = cases[0].model_dump()
    source.update({
        "case_id": "unsupported-discovery-indicator",
        "indicator_id": "1.1",
    })
    unsupported = GoldenCase.model_validate(source)

    with pytest.raises(ValueError, match="supports only RDTII pillar 6/7"):
        await _run_live_discovery([unsupported], documents)


def test_transient_detection_covers_httpx_and_requests_errors():
    assert _is_transient_error(httpx.ConnectError("connection failed"))
    assert _is_transient_error(httpx.ReadTimeout("read timed out"))
    assert _is_transient_error(requests.ConnectionError("connection failed"))
    assert _is_transient_error(requests.Timeout("timed out"))


@pytest.mark.anyio
async def test_transient_retry_uses_non_zero_backoff(monkeypatch):
    attempts = 0
    delays = []

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary")
        return "ok"

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("evaluation.runner.asyncio.sleep", record_sleep)
    monkeypatch.setattr("evaluation.runner.random.uniform", lambda *_args: 0.0)
    result = await _retry_transient(
        operation,
        timeout_seconds=1,
        operation="test operation",
    )

    assert result == "ok"
    assert attempts == 2
    assert delays == [0.25]


def test_ocr_usage_preserves_partial_known_values_and_unknown_sidecar_calls():
    summary = _aggregate_ocr_usage([
        {
            "status": "success",
            "input_tokens": 100,
            "output_tokens": 20,
            "cost_usd": 0.001,
        },
        {
            "status": "unavailable",
            "call_count": None,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
        },
    ])

    assert summary["vision_calls"] is None
    assert summary["input_tokens"] is None
    assert summary["known_input_tokens"] == 100
    assert summary["known_output_tokens"] == 20
    assert summary["known_cost_usd"] == 0.001
    assert summary["unavailable_calls"] == 1
    assert summary["calls_with_unknown_usage"] == 1


def test_full_mode_without_extraction_keeps_llm_and_total_cost_unknown():
    costs = _combined_cost(
        None,
        _aggregate_ocr_usage([]),
        mode="full",
    )

    assert costs["llm"] is None
    assert costs["total"] is None


def test_document_candidate_selection_prefers_verified_primary_live_source():
    document = types.SimpleNamespace(source_legislation="Privacy Act")
    weak = LegalCandidate(
        id="weak",
        country_code="AUS",
        title="Privacy Act",
        url="https://secondary.example/privacy",
        source_grade="secondary",
        validation_status="weak",
        retrieval_mode="fallback",
    )
    strong = LegalCandidate(
        id="strong",
        country_code="AUS",
        title="Privacy Act 1988",
        url="https://legislation.gov.au/privacy",
        source_grade="primary",
        validation_status="verified",
        retrieval_mode="live",
    )

    assert _candidate_rank(strong) > _candidate_rank(weak)
    assert _find_document_candidate(document, [weak, strong]) is strong
