from __future__ import annotations

from types import SimpleNamespace

import pytest

from discovery.ranker import rank_candidates
from discovery.schemas import DiscoverySearchRequest, LegalCandidate, LegalSourceConfig
from discovery.validator import CandidateValidator


def document(text: str, *, status: str = "good"):
    return SimpleNamespace(
        text=text,
        content_type="text",
        quality=SimpleNamespace(
            status=status,
            warnings=[],
            char_count=len(text),
        ),
    )


@pytest.mark.anyio
async def test_candidate_validator_verifies_live_candidate_text_matches_request():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "This official act requires a data protection officer and a data protection impact assessment."
        )

    candidate = LegalCandidate(
        id="live-dpo",
        country_code="SGP",
        title="Official privacy act",
        url="https://official.example/act",
        source_grade="primary",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.4"])
    validator = CandidateValidator(fetch_document_text=fake_fetch, validation_limit=5)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_attempted"] == 1
    assert diagnostics["validation_verified"] == 1
    assert validated[0].validation_status == "verified"
    assert validated[0].matched_indicators == ["7.4"]
    assert "fetched text validates requested indicators" in validated[0].reasons


@pytest.mark.anyio
async def test_candidate_validator_failure_does_not_drop_candidate():
    async def fake_fetch(_url: str, _browser_mode: str):
        raise RuntimeError("fetch down")

    candidate = LegalCandidate(
        id="live-error",
        country_code="SGP",
        title="Official privacy act",
        url="https://official.example/act",
        source_grade="primary",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7])
    validator = CandidateValidator(fetch_document_text=fake_fetch)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_failed"] == 1
    assert validated[0].id == "live-error"
    assert validated[0].validation_status == "failed"
    assert any("fetch down" in warning for warning in validated[0].warnings)
    assert set(validated[0].validation_metadata) == {
        "content_type",
        "quality_status",
        "char_count",
        "matched_indicators",
        "error",
    }


@pytest.mark.anyio
async def test_candidate_validator_times_out_hanging_fetch():
    async def fake_fetch(_url: str, _browser_mode: str):
        import asyncio

        await asyncio.sleep(1)
        return document("personal data protection")

    candidate = LegalCandidate(
        id="live-timeout",
        country_code="SGP",
        title="Official privacy act",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7])
    validator = CandidateValidator(fetch_document_text=fake_fetch, timeout_seconds=0.01)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_failed"] == 1
    assert validated[0].validation_status == "failed"
    assert any("Validation fetch failed" in warning for warning in validated[0].warnings)


@pytest.mark.anyio
async def test_candidate_validator_processing_error_does_not_crash_search(monkeypatch):
    async def fake_fetch(_url: str, _browser_mode: str):
        return document("personal data protection")

    def broken_indicator_match(*_args, **_kwargs):
        raise RuntimeError("indicator parser down")

    import discovery.validator as validator_module

    monkeypatch.setattr(validator_module, "infer_indicator_matches", broken_indicator_match)
    candidate = LegalCandidate(
        id="live-processing-error",
        country_code="SGP",
        title="Official privacy act",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7])
    validator = CandidateValidator(fetch_document_text=fake_fetch)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_failed"] == 1
    assert validated[0].validation_status == "failed"
    assert any("indicator parser down" in warning for warning in validated[0].warnings)


@pytest.mark.anyio
async def test_candidate_validator_weak_path_keeps_candidate_without_penalty_reason():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document("This page is mostly navigation and contact information.", status="weak")

    candidate = LegalCandidate(
        id="live-weak",
        country_code="SGP",
        title="Official page",
        url="https://official.example/page",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7])
    validator = CandidateValidator(fetch_document_text=fake_fetch)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_weak"] == 1
    assert validated[0].validation_status == "weak"
    assert "Fetched text did not match requested discovery indicator terms." in validated[0].warnings


@pytest.mark.anyio
async def test_candidate_validator_does_not_verify_from_search_title_alone():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document("Home About Contact Search Menu", status="weak")

    candidate = LegalCandidate(
        id="title-only-match",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://official.example/act",
        source_grade="primary",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])
    validator = CandidateValidator(fetch_document_text=fake_fetch)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_verified"] == 0
    assert diagnostics["validation_weak"] == 1
    assert validated[0].validation_status == "weak"
    assert validated[0].matched_indicators == []


@pytest.mark.anyio
async def test_candidate_validator_skips_fixture_and_fallback_candidates():
    calls = {"fetch": 0}

    async def fake_fetch(_url: str, _browser_mode: str):
        calls["fetch"] += 1
        return document("personal data protection")

    candidates = [
        LegalCandidate(
            id="fixture",
            country_code="SGP",
            title="Fixture",
            url="https://official.example/fixture",
            retrieval_mode="fixture",
        ),
        LegalCandidate(
            id="fallback",
            country_code="SGP",
            title="Fallback",
            url="https://official.example/fallback",
            retrieval_mode="fallback",
        ),
    ]
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7])
    validator = CandidateValidator(fetch_document_text=fake_fetch)

    validated, diagnostics = await validator.validate(candidates, request)

    assert calls["fetch"] == 0
    assert diagnostics["validation_attempted"] == 0
    assert [candidate.validation_status for candidate in validated] == ["unverified", "unverified"]


def test_ranker_boosts_verified_candidate_over_unverified_peer():
    sources = [
        LegalSourceConfig(
            name="Official Source",
            base_url="https://official.example",
            domains=["official.example"],
            priority=100,
        )
    ]
    unverified = LegalCandidate(
        id="unverified",
        country_code="SGP",
        title="Official result",
        url="https://official.example/unverified",
        source_name="Official Source",
        source_grade="primary",
        document_type="act",
        retrieval_mode="live",
    )
    verified = unverified.model_copy(update={
        "id": "verified",
        "url": "https://official.example/verified",
        "validation_status": "verified",
    })

    ranked = rank_candidates([unverified, verified], sources)

    assert ranked[0].id == "verified"
    assert "fetched text validation boost" in ranked[0].reasons


@pytest.mark.anyio
async def test_candidate_validator_ignores_malformed_indicator_matches(monkeypatch):
    async def fake_fetch(_url: str, _browser_mode: str):
        return document("personal data protection")

    def malformed_indicator_match(*_args, **_kwargs):
        return [], ["", "oops", "7.4"], ["empty", "bad", "valid"]

    import discovery.validator as validator_module

    monkeypatch.setattr(validator_module, "infer_indicator_matches", malformed_indicator_match)
    candidate = LegalCandidate(
        id="live-malformed",
        country_code="SGP",
        title="Official privacy act",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.4"])
    validator = CandidateValidator(fetch_document_text=fake_fetch)

    validated, diagnostics = await validator.validate([candidate], request)

    assert diagnostics["validation_verified"] == 1
    assert validated[0].matched_indicators == ["7.4"]
    assert "valid" in validated[0].reasons
    assert "bad" not in validated[0].reasons


@pytest.mark.anyio
async def test_candidate_validator_tolerates_missing_match_reason(monkeypatch):
    async def fake_fetch(_url: str, _browser_mode: str):
        return document("personal data protection")

    def indicator_without_reason(*_args, **_kwargs):
        return [7], ["7.1"], []

    import discovery.validator as validator_module

    monkeypatch.setattr(
        validator_module,
        "infer_indicator_matches",
        indicator_without_reason,
    )
    candidate = LegalCandidate(
        id="live-missing-reason",
        country_code="SGP",
        title="Official privacy act",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(
        country_code="SGP",
        pillars=[7],
        indicators=["7.1"],
    )

    validated, diagnostics = await CandidateValidator(
        fetch_document_text=fake_fetch
    ).validate([candidate], request)

    assert diagnostics["validation_verified"] == 1
    assert validated[0].matched_indicators == ["7.1"]
    assert validated[0].validation_status == "verified"
