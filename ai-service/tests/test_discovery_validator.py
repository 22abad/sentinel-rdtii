from __future__ import annotations

from types import SimpleNamespace

import pytest

from discovery.ranker import rank_candidates
from discovery.schemas import DiscoverySearchRequest, LegalCandidate, LegalSourceConfig
from discovery.validator import CandidateValidator


def document(
    text: str,
    *,
    status: str = "good",
    warnings: list[str] | None = None,
    fetch_method: str = "http_fallback",
    final_url: str = "https://official.example/act",
):
    return SimpleNamespace(
        text=text,
        content_type="text",
        quality=SimpleNamespace(
            status=status,
            warnings=warnings or [],
            char_count=len(text),
        ),
        crawl_metadata={
            "fetch_method": fetch_method,
            "final_url": final_url,
            "http_status": 200,
            "tls_verified": True,
            "document_origin_domain": "official.example",
        },
    )


@pytest.mark.anyio
async def test_candidate_validator_verifies_live_candidate_text_matches_request():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "Official privacy act. This official act requires a data protection officer "
            "and a data protection impact assessment."
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
        "quality_warnings",
            "final_url",
            "final_url_official",
        "fetch_method",
            "document_retrieval_mode",
            "http_status",
            "tls_verified",
            "document_origin_domain",
            "document_origin_trusted",
            "document_identity_match",
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
    assert any("Validation fetch timed out" in warning for warning in validated[0].warnings)


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
    assert "Fetched text quality was not good enough for verification." in validated[0].warnings


@pytest.mark.anyio
async def test_candidate_validator_does_not_verify_matching_weak_short_page():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "Personal Data Protection Act personal data protection law.",
            status="weak",
        )

    candidate = LegalCandidate(
        id="short-match",
        country_code="SGP",
        title="Personal Data Protection Act",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert diagnostics["validation_weak"] == 1
    assert validated[0].validation_status == "weak"


@pytest.mark.anyio
async def test_candidate_validator_treats_unknown_fetch_method_as_unknown_not_live():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "Personal Data Protection Act personal data protection law. " * 30,
            fetch_method="future_fixture_cache",
        )

    candidate = LegalCandidate(
        id="unknown-provenance",
        country_code="SGP",
        title="Personal Data Protection Act",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert validated[0].validation_status == "weak"
    assert validated[0].validation_metadata["document_retrieval_mode"] == "unknown"
    assert any("Unknown document fetch method" in warning for warning in validated[0].warnings)


@pytest.mark.anyio
async def test_candidate_validator_requires_tls_transport_evidence():
    async def fake_fetch(_url: str, _browser_mode: str):
        value = document("Privacy Act 1988 personal data protection law. " * 30)
        value.crawl_metadata["tls_verified"] = False
        return value

    candidate = LegalCandidate(
        id="no-tls",
        country_code="AUS",
        title="Privacy Act 1988",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="AUS", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert validated[0].validation_status == "weak"
    assert any("TLS verification" in warning for warning in validated[0].warnings)


@pytest.mark.anyio
async def test_candidate_validator_requires_fetched_law_title_identity():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "A different privacy regulation contains personal data protection law duties. "
            * 30
        )

    candidate = LegalCandidate(
        id="identity-mismatch",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert validated[0].validation_status == "weak"
    assert validated[0].validation_metadata["document_identity_match"] is False
    assert any("candidate's law title" in warning for warning in validated[0].warnings)


@pytest.mark.anyio
async def test_candidate_validator_accepts_exact_short_law_acronym_identity():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document("PDPA personal data protection law obligations. " * 30)

    candidate = LegalCandidate(
        id="pdpa",
        country_code="SGP",
        title="PDPA",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 1
    assert validated[0].validation_metadata["document_identity_match"] is True


@pytest.mark.anyio
async def test_candidate_validator_rejects_live_redirect_outside_official_domains():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "Privacy Act 1988 personal data protection law duties. " * 30,
            final_url="https://evil.example/copied-law",
        )

    candidate = LegalCandidate(
        id="redirected-copy",
        country_code="AUS",
        title="Privacy Act 1988",
        url="https://official.example/act",
        official_domains=["official.example"],
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="AUS", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert validated[0].validation_status == "weak"
    assert validated[0].validation_metadata["final_url_official"] is False
    assert any("outside" in warning for warning in validated[0].warnings)


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
async def test_candidate_validator_does_not_verify_matching_error_page():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "404 page not found for the Personal Data Protection Act.",
            status="error_page",
            warnings=["Fetched text looks like an error, block, or challenge page."],
        )

    candidate = LegalCandidate(
        id="matching-error-page",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://official.example/act",
        source_grade="primary",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert diagnostics["validation_failed"] == 1
    assert validated[0].validation_status == "failed"
    assert "Fetched text failed document quality checks." in validated[0].warnings


@pytest.mark.anyio
async def test_candidate_validator_does_not_verify_navigation_heavy_page():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "Personal data protection home menu search contact.",
            status="weak",
            warnings=["Fetched text appears navigation-heavy."],
        )

    candidate = LegalCandidate(
        id="matching-navigation-page",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 0
    assert diagnostics["validation_weak"] == 1
    assert validated[0].validation_status == "weak"


@pytest.mark.anyio
async def test_candidate_validator_finds_indicator_evidence_after_old_twelve_k_limit():
    prefix = "general provision " * 900
    assert len(prefix) > 12000

    async def fake_fetch(_url: str, _browser_mode: str):
        return document(prefix + " Cyber Security Act 2024 cybersecurity incident reporting.")

    candidate = LegalCandidate(
        id="late-evidence",
        country_code="AUS",
        title="Cyber Security Act 2024",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="AUS", pillars=[7], indicators=["7.2"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 1
    assert validated[0].validation_status == "verified"
    assert validated[0].validation_metadata["char_count"] > 12000


@pytest.mark.anyio
async def test_candidate_validator_downgrades_archived_document_retrieval():
    async def fake_fetch(_url: str, _browser_mode: str):
        return document(
            "Personal Data Protection Act 2012. Personal data protection law and "
            "personal information obligations.",
            fetch_method="wayback_machine",
            final_url="https://web.archive.org/web/20250101/https://official.example/act",
        )

    candidate = LegalCandidate(
        id="archived-evidence",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://official.example/act",
        retrieval_mode="live",
    )
    request = DiscoverySearchRequest(country_code="SGP", pillars=[7], indicators=["7.1"])

    validated, diagnostics = await CandidateValidator(fetch_document_text=fake_fetch).validate(
        [candidate], request
    )

    assert diagnostics["validation_verified"] == 1
    assert validated[0].validation_status == "verified"
    assert validated[0].retrieval_mode == "fallback"
    assert validated[0].validation_metadata["document_retrieval_mode"] == "fallback"
    assert any("fallback retrieval via wayback_machine" in warning for warning in validated[0].warnings)


@pytest.mark.anyio
async def test_candidate_validator_skips_fixture_and_fallback_candidates():
    calls = {"fetch": 0}

    async def fake_fetch(_url: str, _browser_mode: str):
        calls["fetch"] += 1
        return document("Official privacy act personal data protection")

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
        return document("Official privacy act personal data protection")

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
        return document("Official privacy act personal data protection")

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
