"""Offline tests for the measured cost report builder."""

from __future__ import annotations

from submission.cost import build_cost_report, is_local_model, price_tokens


def test_local_model_is_zero_cost():
    assert is_local_model("qwen2.5:14b")
    assert is_local_model("llama3.1")
    assert not is_local_model("gpt-4o")
    cost, basis = price_tokens("qwen2.5:14b", 10_000, 2_000)
    assert cost == 0.0
    assert "local" in basis


def test_published_rate_pricing():
    # gpt-4o: $2.50/1M in, $10.00/1M out
    cost, basis = price_tokens("gpt-4o", 1_000_000, 1_000_000)
    assert cost == 12.50
    assert basis == "measured tokens × published rate"


def test_unknown_model_has_no_price():
    cost, basis = price_tokens("some-new-model", 1000, 1000)
    assert cost is None
    assert "no published price" in basis


def test_report_prefers_provider_reported_cost():
    report = build_cost_report(
        document="benchmark.pdf",
        measured_on="2026-07-11",
        model="gpt-4o",
        input_tokens=1_000_000,
        output_tokens=0,
        llm_calls=5,
        processing_time_seconds=12.3,
        provider_reported_cost_usd=0.99,
    )
    # Provider-reported wins over the published-rate computation (2.50).
    assert report["llm"]["cost_usd"] == 0.99
    assert report["llm"]["cost_basis"] == "provider-reported"
    assert report["total_cost_usd"] == 0.99
    assert report["processing_time_seconds"] == 12.3


def test_report_local_run_is_zero_total():
    report = build_cost_report(
        document="pdpa.pdf",
        measured_on="2026-07-11",
        model="qwen2.5:14b",
        input_tokens=4248,
        output_tokens=1402,
        llm_calls=7,
        processing_time_seconds=60.6,
    )
    assert report["llm"]["cost_usd"] == 0.0
    assert report["total_cost_usd"] == 0.0
    assert report["ocr"]["cost_usd"] == 0.0
    # Shape matches the README template.
    assert set(report) >= {"document", "measured_on", "ocr", "embedding", "llm", "total_cost_usd", "processing_time_seconds"}


def test_report_unknown_model_totals_ignore_null_llm():
    report = build_cost_report(
        document="x.pdf",
        measured_on="2026-07-11",
        model="mystery-model",
        input_tokens=1000,
        output_tokens=500,
        llm_calls=2,
        processing_time_seconds=1.0,
        ocr_cost_usd=0.002,
    )
    assert report["llm"]["cost_usd"] is None
    # Null LLM cost is excluded from the total rather than crashing.
    assert report["total_cost_usd"] == 0.002
