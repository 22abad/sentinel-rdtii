"""Regression: an out-of-schema indicator must not crash the pipeline.

A 41-page real PDF once made the keyword classifier surface indicator "5.3"
(Pillar 5), which is outside the IndicatorMapping ``IndicatorId`` literal. The
orchestrator built the mapping unguarded, so a Pydantic ``ValidationError``
propagated out of ``asyncio.gather`` and crashed the entire document run (and
therefore the judges' CLI). Unsupported indicators must be skipped instead.
"""

from __future__ import annotations

import asyncio
import sys
from typing import get_args

import agents.orchestrator as orchestrator_module
from agents.orchestrator import SUPPORTED_MAPPING_INDICATORS, MASOrchestrator
from schemas import IndicatorId


class _FakeProvider:
    """Provider stand-in; it should never be called for a skipped indicator."""

    name = "fake-provider"

    def __init__(self) -> None:
        self.calls = 0

    def extract_batch(self, chunk_text, indicators):
        self.calls += 1
        return {ind_id: {"verbatim_quote": chunk_text[:20]} for ind_id, _ in indicators}

    def extract_features(self, *args, **kwargs):
        self.calls += 1
        return {}

    def repair_extraction(self, *args, **kwargs):
        return {}


def test_supported_set_matches_schema():
    assert SUPPORTED_MAPPING_INDICATORS == frozenset(get_args(IndicatorId))
    # 9.2 does not exist in the RDTII 2.1 methodology (P9 has 9.1/9.3/9.4);
    # 5.3 became a legitimate Round 2 indicator, so it is supported now.
    assert "9.2" not in SUPPORTED_MAPPING_INDICATORS
    assert "5.3" in SUPPORTED_MAPPING_INDICATORS
    assert "6.4" in SUPPORTED_MAPPING_INDICATORS


def test_unsupported_indicator_is_skipped_without_crashing(monkeypatch):
    import main as main_module

    # Force the classifier to surface only the out-of-schema indicator.
    monkeypatch.setattr(main_module, "classify_indicator", lambda _t: ["9.2"])

    provider = _FakeProvider()
    orchestrator = MASOrchestrator(provider)
    response = asyncio.run(
        orchestrator.run_pipeline(
            "Section 3. Some Pillar 5 provision about market access and services."
        )
    )

    # No crash, no mappings, and the provider was never invoked for the
    # skipped indicator.
    assert response.mappings == []
    assert provider.calls == 0


def test_orchestrator_does_not_import_web_entrypoint(monkeypatch):
    """Lean CLI/evaluation runs must not require FastAPI via ``main``."""
    monkeypatch.delitem(sys.modules, "main", raising=False)
    monkeypatch.setattr(orchestrator_module, "classify_indicator", lambda _text: [])

    provider = _FakeProvider()
    response = asyncio.run(MASOrchestrator(provider).run_pipeline("No indicators here."))

    assert "main" not in sys.modules
    assert response.mappings == []
    assert provider.calls == 0
