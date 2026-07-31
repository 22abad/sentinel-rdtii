"""Cost instrumentation: cache-token accounting + the Analyst cost switch.

Both exist to answer "what does a run actually cost, and which calls can we
stop making?". The accounting is inert (it only records), and the switch
defaults to ON, so these tests pin the default behaviour as hard as the
switched behaviour.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from providers.base import ExtractionUsage
from providers.openai_compatible import DeepSeekProvider, OpenAICompatibleProvider
from schemas import RunUsageSummary
from telemetry import UsageCollector

REPO_ROOT = Path(__file__).resolve().parents[2]


def _provider(input_price=0.27, output_price=1.10, cache_hit_price=0.0):
    """A provider with prices but no network client (bypasses __init__)."""
    p = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    p._input_price = input_price
    p._output_price = output_price
    p._cache_hit_price = cache_hit_price
    return p


# ── cache-token accounting ──────────────────────────────────────────────


def test_deepseek_cache_split_is_recorded():
    """DeepSeek reports hit/miss directly — both reach the usage record."""
    usage = ExtractionUsage()
    _provider()._populate_usage(
        usage,
        SimpleNamespace(
            prompt_tokens=1199,
            completion_tokens=263,
            prompt_cache_hit_tokens=1152,
            prompt_cache_miss_tokens=47,
        ),
    )
    assert usage.cache_hit_tokens == 1152
    assert usage.cache_miss_tokens == 47


def test_openai_cached_tokens_infer_the_miss_side():
    """OpenAI reports only cached_tokens; the miss side is derived, not guessed."""
    usage = ExtractionUsage()
    _provider(0.15, 0.60)._populate_usage(
        usage,
        SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=100,
            prompt_tokens_details={"cached_tokens": 768},
        ),
    )
    assert usage.cache_hit_tokens == 768
    assert usage.cache_miss_tokens == 232


def test_silent_provider_reports_unknown_not_zero():
    """No cache fields must read as 'unknown', never as a 0% hit rate."""
    usage = ExtractionUsage()
    _provider()._populate_usage(
        usage, SimpleNamespace(prompt_tokens=500, completion_tokens=50)
    )
    assert usage.cache_hit_tokens is None
    assert usage.cache_miss_tokens is None


def test_half_a_split_is_reported_as_no_split():
    """A cached-token count with no prompt_tokens to complete it would read as
    a 100% hit rate downstream. Report nothing rather than something wrong."""
    usage = ExtractionUsage()
    _provider()._populate_usage(
        usage,
        SimpleNamespace(
            prompt_tokens=None,
            completion_tokens=50,
            prompt_tokens_details={"cached_tokens": 900},
        ),
    )
    assert usage.cache_hit_tokens is None
    assert usage.cache_miss_tokens is None


def test_cost_unchanged_when_cache_price_unconfigured():
    """Default deployment prices every input token at the miss rate, as before."""
    provider = _provider()
    usage = ExtractionUsage(
        input_tokens=1000, output_tokens=100, cache_hit_tokens=900, cache_miss_tokens=100
    )
    assert provider._priced_cost(usage) == pytest.approx(
        provider.estimate_cost_usd(1000, 100)
    )


def test_cost_bills_hits_at_the_cache_rate_when_configured():
    provider = _provider(cache_hit_price=0.027)
    usage = ExtractionUsage(
        input_tokens=1000, output_tokens=100, cache_hit_tokens=900, cache_miss_tokens=100
    )
    expected = (900 * 0.027 + 100 * 0.27 + 100 * 1.10) / 1_000_000
    assert provider._priced_cost(usage) == pytest.approx(expected)
    assert provider._priced_cost(usage) < provider.estimate_cost_usd(1000, 100)


def test_provider_without_the_price_attribute_still_bills():
    """A provider built without __init__ predates _cache_hit_price."""
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider._input_price = 0.27
    provider._output_price = 1.10
    usage = ExtractionUsage(input_tokens=100, output_tokens=10, cache_hit_tokens=90)
    assert provider._priced_cost(usage) == pytest.approx(
        provider.estimate_cost_usd(100, 10)
    )


def test_collector_summarizes_hit_rate():
    collector = UsageCollector(run_id="t")
    collector.record(
        operation="extract_batch", provider="deepseek", model="m", latency_ms=10,
        input_tokens=1199, output_tokens=263,
        cache_hit_tokens=1152, cache_miss_tokens=47,
    )
    collector.record(
        operation="extract_batch", provider="deepseek", model="m", latency_ms=10,
        input_tokens=1207, output_tokens=407,
        cache_hit_tokens=0, cache_miss_tokens=1207,
    )
    summary = collector.summary()
    assert summary["known_cache_hit_tokens"] == 1152
    assert summary["known_cache_miss_tokens"] == 1254
    assert summary["cache_hit_rate"] == pytest.approx(1152 / 2406, abs=1e-4)
    assert summary["calls_with_cache_accounting"] == 2
    # Per-operation call counts survive (the existing dimension).
    assert summary["operations"] == {"extract_batch": 2}
    # And the summary still fits the response schema.
    RunUsageSummary(run_id="t", **summary)


def test_hit_rate_is_none_when_no_call_reported_cache_accounting():
    collector = UsageCollector(run_id="t")
    collector.record(
        operation="query", provider="ollama", model="m", latency_ms=5,
        input_tokens=10, output_tokens=2,
    )
    summary = collector.summary()
    assert summary["cache_hit_rate"] is None
    assert summary["calls_with_cache_accounting"] == 0


def test_hit_rate_is_none_when_only_some_calls_reported_a_split():
    """A run mixing a reporting provider with a silent one (failover, or the
    cross-model checker on Ollama) shares one collector. The ratio over accounted
    tokens would read 96% while the true share of the run's input is 13%, and one
    number cannot say both — so the field abstains and the raw counts stay."""
    collector = UsageCollector(run_id="mixed")
    collector.record(
        operation="extract_batch", provider="deepseek", model="m", latency_ms=1,
        input_tokens=1199, output_tokens=263,
        cache_hit_tokens=1152, cache_miss_tokens=47,
    )
    collector.record(
        operation="query", provider="ollama", model="q", latency_ms=1,
        input_tokens=8000, output_tokens=400,
    )
    summary = collector.summary()
    assert summary["cache_hit_rate"] is None
    assert summary["calls_with_cache_accounting"] == 1
    assert summary["llm_calls"] == 2
    # The ingredients survive so a consumer can be explicit about the partial view.
    assert summary["known_cache_hit_tokens"] == 1152
    assert summary["known_input_tokens"] == 9199


def test_cli_cost_line_stays_parseable_by_cost_report(monkeypatch):
    """FORMAT CONTRACT: tools/cost_report.py parses this exact stdout line and
    README documents `main.py | tee run.log | cost_report.py run.log`. Rewording
    it (as an earlier pass did) makes that workflow report 0 economies / $0."""
    # syspath_prepend, not sys.path.insert: a permanent insert of a directory
    # that also contains a `main.py` makes every later `import main` in the
    # session resolve to the wrong module (32 failures in a subset run).
    monkeypatch.syspath_prepend(str(REPO_ROOT / "tools"))
    from cost_report import parse_cost_line

    from telemetry import cache_note

    totals = {"cache_hit_tokens": 1152, "cache_miss_tokens": 47, "input_tokens": 1199}
    calls, _in, _out, cost, display = 15, 10601, 15209, 0.0196, "Singapore"
    line = (
        f"Total measured cost: {calls} LLM calls, {_in:,} in / {_out:,} out tokens, "
        f"${cost:.4f} ({display}){cache_note(totals)}"
    )
    parsed = parse_cost_line(line)
    assert parsed == {
        "economy": "Singapore", "llm_calls": 15,
        "input_tokens": 10601, "output_tokens": 15209, "cost_usd": 0.0196,
    }, line


def test_pricing_basis_names_the_provider_and_each_rate(monkeypatch):
    """The note must answer "which rates priced THIS run", per item.

    Scanning os.environ for any *_USD_PER_MTOK (an earlier version) let a stray
    OPENAI_INPUT_... vouch for an Ollama run, and a single configured/unconfigured
    verdict hid that DeepSeek's output price was still the compiled-in one when
    only its input price had been set."""
    from providers import pricing_basis

    for key in [k for k in os.environ if k.endswith("_USD_PER_MTOK")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("RDTII_LLM_FALLBACK_PROVIDER", raising=False)
    monkeypatch.delenv("RDTII_CHECKER_PROVIDER", raising=False)

    note = pricing_basis("deepseek")
    assert "deepseek" in note
    assert "compiled-in snapshot" in note
    assert "hits billed at the miss rate" in note

    # A stray OTHER-provider env must not vouch for this run.
    monkeypatch.setenv("OPENAI_INPUT_USD_PER_MTOK", "0.15")
    assert "compiled-in snapshot" in pricing_basis("deepseek")

    # Partially configured: the item that is still compiled-in must say so.
    monkeypatch.setenv("DEEPSEEK_INPUT_USD_PER_MTOK", "0.14")
    partial = pricing_basis("deepseek")
    assert "input: env DEEPSEEK_INPUT_USD_PER_MTOK" in partial
    assert "output: compiled-in snapshot" in partial
    assert "DEEPSEEK_OUTPUT_USD_PER_MTOK" in partial  # named in the "set these" line

    # A provider with no rate table says so rather than implying configuration.
    assert "no token-rate settings" in pricing_basis("ollama")

    # Every provider that can contribute calls to the same collector is listed
    # with its own price sources, rather than being hidden behind the primary.
    monkeypatch.setenv("RDTII_LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("RDTII_CHECKER_PROVIDER", "groq")
    mixed = pricing_basis("deepseek")
    assert "fallback openai rates" in mixed
    assert "checker groq rates" in mixed


def test_pricing_basis_is_a_separate_stdout_line_the_parser_ignores(monkeypatch):
    """README's workflow is `main.py | tee run.log | cost_report.py run.log`,
    which keeps stdout only — so the basis must be on stdout, and must not
    disturb the cost line's parse."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "tools"))
    from cost_report import parse_cost_line

    from providers import pricing_basis

    note = pricing_basis("deepseek")
    assert note.startswith("  ("), note
    for line in note.splitlines():
        assert parse_cost_line(line) is None, line


# ── analyst switch ──────────────────────────────────────────────────────


def test_analyst_defaults_on(monkeypatch):
    from agents.analyst import analyst_enabled

    monkeypatch.delenv("RDTII_ANALYST", raising=False)
    assert analyst_enabled() is True


@pytest.mark.parametrize("value", ["off", "0", "false", "no", "OFF"])
def test_analyst_switches_off(monkeypatch, value):
    from agents.analyst import analyst_enabled

    monkeypatch.setenv("RDTII_ANALYST", value)
    assert analyst_enabled() is False


class _FakeProvider:
    """Emits one clean, verifiable mapping for indicator 6.4."""

    name = "fake-provider"
    model_name = "fake-model"

    def __init__(self, quote: str):
        self._quote = quote

    def extract_batch(self, chunk_text, indicators):
        return {
            ind_id: {
                "verbatim_quote": self._quote,
                "article_clause": "Section 26",
                "source_legislation": "Singapore Personal Data Protection Act (PDPA), 2012, No. 26",
                "scope": "horizontal",
                "coverage": "Cross-cutting",
            }
            for ind_id, _ in indicators
        }

    def extract_features(self, *args, **kwargs):
        return {"verbatim_quote": self._quote}

    def repair_extraction(self, *args, **kwargs):
        return {}


def _run_orchestrator(monkeypatch, *, analyst_text: str):
    """Drive the real pipeline to an accepted mapping with a stubbed Analyst."""
    from agents.analyst import AnalystAgent
    from agents.orchestrator import MASOrchestrator

    # No LLM eligibility second-opinion in a unit test.
    monkeypatch.setenv("RDTII_ELIGIBILITY_VERIFIER", "0")

    called = {"n": 0}

    async def _fake_run(self, **kwargs):
        called["n"] += 1
        return analyst_text

    monkeypatch.setattr(AnalystAgent, "run", _fake_run)

    text = (
        "Section 26. An organisation shall not transfer any personal data to a "
        "country or territory outside Singapore except in accordance with "
        "requirements prescribed under this Act."
    )
    quote = (
        "An organisation shall not transfer any personal data to a country or "
        "territory outside Singapore except in accordance with requirements "
        "prescribed under this Act."
    )
    response = asyncio.run(
        MASOrchestrator(_FakeProvider(quote)).run_pipeline(
            text, target_indicators=["6.4"]
        )
    )
    return response, called


def test_analyst_text_reaches_impact_and_every_legacy_alias(monkeypatch):
    """The regression this guards: writing only ``mapping.impact`` left the three
    compatibility aliases carrying the deterministic scorer sentence, so one
    response contradicted itself."""
    monkeypatch.delenv("RDTII_ANALYST", raising=False)
    response, called = _run_orchestrator(monkeypatch, analyst_text="ANALYST-PROSE")

    assert response.mappings, "fixture must produce an accepted mapping"
    assert called["n"] >= 1, "analyst must run when enabled"
    mapping = response.mappings[0]
    assert "ANALYST-PROSE" in mapping.impact
    for alias in ("Impact_or_comments", "impact_or_comments", "impact_comments"):
        assert "ANALYST-PROSE" in getattr(mapping, alias), alias


def test_analyst_off_skips_the_call_and_keeps_the_deterministic_rationale(monkeypatch):
    """Off is a cost switch, not a data-loss switch: the submitted column falls
    back to the scorer's justification rather than going empty."""
    monkeypatch.setenv("RDTII_ANALYST", "off")
    response, called = _run_orchestrator(monkeypatch, analyst_text="ANALYST-PROSE")

    assert response.mappings, "fixture must produce an accepted mapping"
    assert called["n"] == 0, "analyst must not be called when disabled"
    mapping = response.mappings[0]
    assert "ANALYST-PROSE" not in mapping.impact
    assert mapping.impact.strip(), "the rationale column must not go empty"


def test_analyst_state_is_part_of_the_extraction_cache_key(monkeypatch):
    """The workbench cache is shared across sessions and keys on text only, so
    without this dimension an analyst-off run hands its terse rationale to
    everyone else's analyst-on session."""
    from services.extraction_cache import source_hash

    monkeypatch.setenv("RDTII_ANALYST", "on")
    on = source_hash("Section 26. Some statutory text.")
    monkeypatch.setenv("RDTII_ANALYST", "off")
    off = source_hash("Section 26. Some statutory text.")
    assert on != off


# ── the evaluator's switch must beat a stale .env ───────────────────────


@pytest.mark.parametrize(
    "argv, env_before, expected",
    [
        ([], {}, "off"),
        ([], {"RDTII_ANALYST": "on"}, "off"),
        (["--with-analyst"], {"RDTII_ANALYST": "off"}, "on"),
        (["--with-analyst"], {}, "on"),
    ],
)
def test_eval_runner_flag_beats_the_environment(argv, env_before, expected):
    """os.environ.setdefault would let a value already in .env win, silently
    making --with-analyst do nothing.

    Runs in a SUBPROCESS with python-dotenv stubbed out: importing the tool
    executes ``load_dotenv(REPO_ROOT/'.env')`` at module level, which would
    otherwise pull the developer's real secrets into the pytest process.
    """
    driver = textwrap.dedent(
        """
        import os, sys, runpy, types
        # Stub python-dotenv BEFORE the tool imports it, so the real .env is
        # never read into this process.
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda *a, **k: False
        sys.modules["dotenv"] = stub
        mod = runpy.run_path(sys.argv[1], run_name="_under_test")
        mod["asyncio"].run = lambda coro, *a, **k: (coro.close(), (_ for _ in ()).throw(SystemExit(0)))
        try:
            mod["main"](sys.argv[2:])
        except SystemExit:
            pass
        print(os.environ.get("RDTII_ANALYST"))
        """
    )
    env = {**os.environ, **env_before, "PYTHONPATH": str(REPO_ROOT / "ai-service")}
    for key in ("RDTII_ANALYST",):
        if key not in env_before:
            env.pop(key, None)

    result = subprocess.run(
        [sys.executable, "-c", driver,
         str(REPO_ROOT / "tools" / "run_round2_eval.py"), "--economy", "IND", *argv],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert result.stdout.strip().splitlines()[-1] == expected, result.stderr[-2000:]
