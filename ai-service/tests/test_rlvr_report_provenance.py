"""The measurement report must not lie about how it was produced.

``render_markdown`` hardcoded "(no API calls, no network)" onto every report,
including ``--with-llm`` runs that bill one eligibility call per candidate. The
offline and live numbers differ materially (100% vs 87.5% hygiene top-1), so a
reader who cannot tell which run they are holding cannot tell whether best-of-N
is cleared to wire. These tests pin the provenance line to the actual mode.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rlvr_measure.py"


@pytest.fixture(scope="module")
def rlvr_measure():
    spec = importlib.util.spec_from_file_location("rlvr_measure_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _report(mode: str, llm_provider: str | None) -> dict:
    """A real committed report, with only the mode/provider varied.

    Built from the checked-in artifact rather than hand-rolled so these tests
    exercise the same shape render_markdown sees in production and do not rot
    when a new section is added to the report.
    """
    base = json.loads(
        (ROOT / "evaluation" / "reports" / "rlvr-measurement.json").read_text("utf-8")
    )
    base["mode"] = mode
    base["llm_provider"] = llm_provider
    return base


def test_offline_run_still_claims_offline(rlvr_measure):
    md = rlvr_measure.render_markdown(_report("offline-synthetic-distractors", None))
    assert "no API calls, no network" in md


def test_llm_run_must_not_claim_it_stayed_offline(rlvr_measure):
    md = rlvr_measure.render_markdown(
        _report("synthetic-distractors+llm-eligibility", "deepseek")
    )
    assert "no API calls, no network" not in md, (
        "a billed run reporting itself as offline is how the stale 87.5% "
        "measurement got mistaken for the 100% one"
    )
    assert "REAL API calls" in md
    assert "deepseek" in md


def test_llm_provider_is_named_so_runs_are_attributable(rlvr_measure):
    md = rlvr_measure.render_markdown(
        _report("synthetic-distractors+llm-eligibility", "ollama")
    )
    assert "`ollama`" in md
