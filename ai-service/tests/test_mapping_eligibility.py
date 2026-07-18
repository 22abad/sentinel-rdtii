from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext

from agents.eligibility import EligibilityVerifier, deterministic_eligibility


def test_retention_requires_duty_and_explicit_minimum_duration():
    good = deterministic_eligibility(
        "The company must retain transaction records for at least seven years.",
        "7.3",
        {"has_minimum_retention_period": True},
    )
    assert good.supported
    assert good.evidence_spans["duration"]

    minimisation = deterministic_eligibility(
        "The company must cease to retain records as soon as they are no longer necessary.",
        "7.3",
        {"has_minimum_retention_period": False},
    )
    assert not minimisation.supported
    assert any("minimisation" in reason.lower() for reason in minimisation.exclusion_reasons)


def test_dpia_without_dpo_is_insufficient_for_7_4():
    result = deterministic_eligibility(
        "An organisation must conduct a data protection impact assessment.",
        "7.4",
        {"has_dpia_requirement": True, "has_dpo_requirement": False},
    )
    assert not result.supported


def test_criminal_investigation_purpose_is_not_an_objectives_clause():
    result = deterministic_eligibility(
        "For the purposes of a criminal investigation, a police officer may require production of any document.",
        "7.5",
        {"has_government_access_without_judicial_oversight": True},
    )
    assert result.supported


def test_court_order_access_is_not_warrantless_government_access():
    result = deterministic_eligibility(
        "A police officer may obtain personal records pursuant to a court order.",
        "7.5",
        {"has_government_access_without_judicial_oversight": True},
    )
    assert not result.supported
    assert result.evidence_spans["access_gate"] == ["pursuant to a court order"]


class _VerifierProvider:
    name = "test-real-provider"

    def __init__(self, payload):
        self.payload = payload

    def usage_operation(self, *_args, **_kwargs):
        return nullcontext()

    def query(self, prompt, system=""):
        assert "assigned score" not in prompt.lower()
        assert "proposed indicator" not in prompt.lower()
        return json.dumps(self.payload)


def test_independent_verifier_can_choose_none(monkeypatch):
    monkeypatch.setenv("RDTII_ELIGIBILITY_VERIFIER", "1")
    quote = "An organisation must not transfer personal data outside Singapore."
    provider = _VerifierProvider({
        "decision": "insufficient",
        "supported_indicators": [],
        "evidence_spans": {},
        "exclusion_reasons": ["NONE"],
    })
    result = asyncio.run(EligibilityVerifier(provider).verify(
        quote, "6.1", {"has_ban": True, "has_local_processing": False}
    ))
    assert not result.supported
    assert result.verifier_mode == "independent_llm"


def test_independent_verifier_requires_exact_evidence_span(monkeypatch):
    monkeypatch.setenv("RDTII_ELIGIBILITY_VERIFIER", "1")
    quote = "An organisation must not transfer personal data outside Singapore."
    provider = _VerifierProvider({
        "decision": "supported",
        "supported_indicators": ["6.1"],
        "evidence_spans": {"6.1": ["paraphrased transfer restriction"]},
        "exclusion_reasons": [],
    })
    result = asyncio.run(EligibilityVerifier(provider).verify(
        quote, "6.1", {"has_ban": True, "has_local_processing": False}
    ))
    assert not result.supported
    assert any("exact quote" in reason for reason in result.exclusion_reasons)
