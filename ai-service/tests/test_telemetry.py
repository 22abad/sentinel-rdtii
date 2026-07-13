from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from telemetry import UsageCollector


def test_usage_collector_is_thread_safe_and_aggregates_complete_usage():
    collector = UsageCollector(run_id="test-run")

    def add(index: int) -> None:
        collector.record(
            operation="repair" if index % 2 else "extract_single",
            provider="fake",
            model="fake-model",
            latency_ms=10,
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.001,
            cost_basis="actual_tokens_x_pricing_snapshot",
            pricing_date="2026-07-11",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(100)))

    summary = collector.summary()
    assert summary["llm_calls"] == 100
    assert summary["input_tokens"] == 10_000
    assert summary["output_tokens"] == 2_000
    assert summary["cost_usd"] == 0.1
    assert summary["latency_sum_ms"] == 1_000
    assert summary["operations"] == {"extract_single": 50, "repair": 50}


def test_unknown_usage_is_null_not_zero():
    collector = UsageCollector(run_id="partial-run")
    collector.record(
        operation="query",
        provider="fake",
        model="fake-model",
        latency_ms=25,
    )

    payload = collector.to_dict()
    assert payload["calls"][0]["input_tokens"] is None
    assert payload["summary"]["input_tokens"] is None
    assert payload["summary"]["cost_usd"] is None
    assert "Unavailable" in collector.render_markdown()


def test_json_and_markdown_exports_are_explicit_and_independent(tmp_path):
    collector = UsageCollector(
        run_id="write-run",
        metadata={"mode": "offline", "commit_sha": "abc123"},
    )
    collector.record(
        operation="extract_batch",
        provider="deepseek",
        model="fake-deepseek",
        latency_ms=1234,
        input_tokens=1_200,
        output_tokens=300,
        cost_usd=0.000654,
        cost_basis="actual_tokens_x_pricing_snapshot",
        pricing_date="2026-07-11",
        input_usd_per_million=0.27,
        output_usd_per_million=1.10,
        indicator_ids=("6.4", "7.1"),
    )

    json_path = collector.write_json(tmp_path / "usage.json")
    assert not (tmp_path / "usage.md").exists()
    markdown_path = collector.write_markdown(tmp_path / "usage.md")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["run_id"] == "write-run"
    assert payload["summary"]["llm_calls"] == 1
    assert "| LLM calls | 1 |" in markdown
    assert "`extract_batch`" in markdown
    assert "$0.000654" in markdown


def test_openai_compatible_records_at_provider_boundary():
    from providers.openai_compatible import OpenAICompatibleProvider

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )
    completions = SimpleNamespace(create=lambda **_kwargs: response)

    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.model_name = "fake-model"
    provider.name = "fake-provider"
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider._input_price = 1.0
    provider._output_price = 2.0
    collector = UsageCollector(run_id="provider-run")
    provider.set_usage_collector(collector)

    result = provider._call_llm(
        "prompt",
        operation="repair",
        indicator_ids=("6.1",),
    )

    assert result == {"ok": True}
    record = collector.records[0]
    assert record.operation == "repair"
    assert record.indicator_ids == ("6.1",)
    assert record.input_tokens == 11
    assert record.output_tokens == 7
    assert record.cost_usd == pytest.approx(0.000025)
    assert provider.last_usage.input_tokens == 11


def test_provider_identity_uses_class_name_while_model_uses_instance_name():
    from providers.base import ExtractionUsage, LLMProvider

    class NamedProvider(LLMProvider):
        name = "provider-family"
        model_name = "model-version"

        def __init__(self):
            self.name = self.model_name

        def query(self, prompt: str, system: str = "") -> str:
            return "unused"

        def extract_features(self, article_text, indicator_id, feature_spec):
            return {}

    provider = NamedProvider()
    collector = UsageCollector(run_id="provider-identity")
    provider.set_usage_collector(collector)
    provider._record_usage(
        "query",
        ExtractionUsage(input_tokens=1, output_tokens=1),
    )

    record = collector.records[0]
    assert record.provider == "provider-family"
    assert record.model == "model-version"


def test_vertex_tokens_do_not_turn_unknown_pricing_into_zero_cost():
    from providers.vertex_ai import VertexAIProvider

    provider = VertexAIProvider.__new__(VertexAIProvider)
    provider.model_name = "gemini-test"
    provider.name = provider.model_name
    provider._request = lambda *_args, **_kwargs: {
        "candidates": [{"content": {"parts": [{"text": "response"}]}}],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 30,
        },
    }
    collector = UsageCollector(run_id="vertex-unknown-cost")
    provider.set_usage_collector(collector)

    assert provider.query("prompt") == "response"
    record = collector.records[0]
    assert record.provider == "vertex-ai"
    assert record.model == "gemini-test"
    assert record.input_tokens == 120
    assert record.output_tokens == 30
    assert record.cost_usd is None
    assert record.cost_basis == "unavailable"
    assert collector.summary()["cost_usd"] is None


@pytest.mark.anyio
async def test_run_extraction_returns_usage_without_writing_report_files(monkeypatch, tmp_path):
    import main as main_module
    from providers.base import ExtractionUsage, LLMProvider
    from services.extraction import run_extraction

    class InstrumentedProvider(LLMProvider):
        name = "instrumented"
        model_name = "instrumented-model"

        def query(self, prompt: str, system: str = "") -> str:
            operation, indicator_ids = self._usage_context("query")
            self._record_usage(
                operation,
                ExtractionUsage(
                    input_tokens=50,
                    output_tokens=10,
                    cost_usd=0.001,
                    latency_ms=5,
                ),
                indicator_ids=indicator_ids,
                cost_basis="actual_tokens_x_pricing_snapshot",
            )
            return "Measured legal analysis."

        def extract_features(self, article_text, indicator_id, feature_spec):
            self._record_usage(
                "extract_single",
                ExtractionUsage(
                    input_tokens=100,
                    output_tokens=20,
                    cost_usd=0.002,
                    latency_ms=10,
                ),
                indicator_ids=(indicator_id,),
                cost_basis="actual_tokens_x_pricing_snapshot",
            )
            return {
                "verbatim_quote": "Personal data shall not be transferred abroad",
                "article_clause": "Article 1",
                "source_legislation": "Test Privacy Act 2026",
                "source_url": "",
                "last_update": "2026-01-01",
                "scope": "horizontal",
                "personal_data": True,
                "has_ban": True,
            }

    monkeypatch.setattr(main_module, "classify_indicator", lambda _text: ["6.1"])
    monkeypatch.chdir(tmp_path)

    response = await run_extraction(
        "Article 1. Personal data shall not be transferred abroad.",
        InstrumentedProvider(),
    )

    assert response.usage is not None
    assert response.usage.llm_calls == 2
    assert response.usage.input_tokens == 150
    assert response.usage.output_tokens == 30
    assert response.usage.cost_usd == pytest.approx(0.003)
    assert response.usage.operations == {
        "analyst_comment": 1,
        "extract_single": 1,
    }
    assert list(tmp_path.glob("*.json")) == []
    assert list(tmp_path.glob("*.md")) == []


@pytest.mark.anyio
async def test_stream_extraction_emits_usage_snapshot_before_done(monkeypatch):
    import main as main_module
    from providers.base import ExtractionUsage, LLMProvider
    from services.streaming_extraction import stream_extraction

    class StreamProvider(LLMProvider):
        name = "stream-instrumented"
        model_name = "stream-model"

        def query(self, prompt: str, system: str = "") -> str:
            return "unused"

        def extract_features(self, article_text, indicator_id, feature_spec):
            self._record_usage(
                "extract_single",
                ExtractionUsage(
                    input_tokens=80,
                    output_tokens=15,
                    cost_usd=0.001,
                    latency_ms=8,
                ),
                indicator_ids=(indicator_id,),
                cost_basis="actual_tokens_x_pricing_snapshot",
            )
            return {
                "verbatim_quote": "Personal data shall not be transferred abroad",
                "article_clause": "Article 1",
                "source_legislation": "Test Privacy Act 2026",
                "source_url": "",
                "last_update": "2026-01-01",
                "scope": "horizontal",
                "personal_data": True,
                "has_ban": True,
            }

    monkeypatch.setattr(main_module, "classify_indicator", lambda _text: ["6.1"])
    events = [
        event
        async for event in stream_extraction(
            "Article 1. Personal data shall not be transferred abroad.",
            StreamProvider(),
        )
    ]

    names = [event.splitlines()[0].removeprefix("event: ") for event in events]
    assert "usage" in names
    assert names[-1] == "done"
    usage_event = next(event for event in events if event.startswith("event: usage"))
    usage_payload = json.loads(usage_event.split("data: ", 1)[1])
    assert usage_payload["llm_calls"] == 1
    assert usage_payload["input_tokens"] == 80
