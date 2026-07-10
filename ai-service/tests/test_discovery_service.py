from __future__ import annotations

import pytest

from discovery.registry import get_sources
from discovery.schemas import DiscoverySearchRequest, LegalCandidate, LegalSourceConfig, RawSearchHit
from discovery.service import DiscoveryService


@pytest.mark.anyio
@pytest.mark.parametrize("country_code", ["AUS", "CHN", "MYS", "SGP", "THA"])
async def test_mock_discovery_fixtures_use_configured_exact_domains(country_code):
    response = await DiscoveryService().search(
        DiscoverySearchRequest(country_code=country_code, browser_mode="mock")
    )

    assert response.diagnostics["filtered_off_domain"] == 0
    assert response.candidates


def test_filter_relevant_candidates_keeps_known_law_database_without_match():
    service = DiscoveryService()
    sources = get_sources("SGP")
    candidate = LegalCandidate(
        id="sso-no-match",
        country_code="SGP",
        title="Singapore Statutes Online Result",
        url="https://sso.agc.gov.sg/Act/EXAMPLE",
        source_domain="sso.agc.gov.sg",
        source_name="Singapore Statutes Online",
        source_grade="primary",
        document_type="act",
    )

    relevant, filtered = service._filter_relevant_candidates([candidate], sources)

    assert relevant == [candidate]
    assert filtered == 0


def test_filter_relevant_candidates_drops_non_database_without_match():
    service = DiscoveryService()
    sources = get_sources("SGP")
    candidate = LegalCandidate(
        id="pdpc-no-match",
        country_code="SGP",
        title="Generic PDPC page",
        url="https://www.pdpc.gov.sg/generic-page",
        source_domain="www.pdpc.gov.sg",
        source_name="Personal Data Protection Commission",
        source_grade="primary",
        document_type="unknown",
    )

    relevant, filtered = service._filter_relevant_candidates([candidate], sources)

    assert relevant == []
    assert filtered == 1


def test_filter_source_hits_drops_off_domain_and_non_http_results():
    service = DiscoveryService()
    source = LegalSourceConfig(
        name="Official Source",
        base_url="https://official.example",
        domains=["official.example"],
    )
    hits = [
        RawSearchHit(url="https://official.example/law"),
        RawSearchHit(url="https://archive.official.example/law"),
        RawSearchHit(url="https://official.example.evil.test/law"),
        RawSearchHit(url="file://official.example/private"),
    ]

    accepted, rejected_count, warnings = service._filter_source_hits(source, hits)

    assert [hit.url for hit in accepted] == ["https://official.example/law"]
    assert rejected_count == 3
    assert warnings == [
        "Discarded 3 result(s) outside configured domains for Official Source."
    ]
    assert not any("evil.test" in warning for warning in warnings)


def test_select_sources_respects_official_only_secondary_filter():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="SGP", pillars=[6, 7], source_mode="official_only")
    sources = [
        LegalSourceConfig(
            name="Official Source",
            base_url="https://official.example",
            domains=["official.example"],
            adapter="search_engine",
            source_grade="primary",
            languages=["en"],
        ),
        LegalSourceConfig(
            name="Secondary Source",
            base_url="https://secondary.example",
            domains=["secondary.example"],
            adapter="search_engine",
            source_grade="secondary",
            languages=["en"],
        ),
    ]

    selected, skipped = service._select_sources(request, sources, ["en"])

    assert [source.name for source in selected] == ["Official Source"]
    assert skipped == ["Secondary Source (secondary source)"]


def test_select_sources_respects_configured_pillar_scope():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="SGP", pillars=[6])
    sources = [
        LegalSourceConfig(
            name="Pillar Six Source",
            base_url="https://p6.example",
            domains=["p6.example"],
            adapter="search_engine",
            source_grade="primary",
            languages=["en"],
            pillars=[6],
        ),
        LegalSourceConfig(
            name="Pillar Seven Source",
            base_url="https://p7.example",
            domains=["p7.example"],
            adapter="search_engine",
            source_grade="primary",
            languages=["en"],
            pillars=[7],
        ),
    ]

    selected, skipped = service._select_sources(request, sources, ["en"])

    assert [source.name for source in selected] == ["Pillar Six Source"]
    assert skipped == ["Pillar Seven Source (pillar/indicator mismatch)"]


def test_select_sources_allows_pillar_scope_when_source_also_has_indicators():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="SGP", pillars=[6])
    sources = [
        LegalSourceConfig(
            name="Broad Pillar Source",
            base_url="https://broad.example",
            domains=["broad.example"],
            adapter="search_engine",
            source_grade="primary",
            languages=["en"],
            pillars=[6],
            indicators=["6.4"],
        ),
    ]

    selected, skipped = service._select_sources(request, sources, ["en"])

    assert [source.name for source in selected] == ["Broad Pillar Source"]
    assert skipped == []


def test_select_sources_with_indicators_still_respects_requested_pillars():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="SGP", pillars=[6], indicators=["6.4"])
    sources = [
        LegalSourceConfig(
            name="Pillar Seven Indicator Source",
            base_url="https://p7.example",
            domains=["p7.example"],
            adapter="search_engine",
            source_grade="primary",
            languages=["en"],
            pillars=[7],
            indicators=["7.4"],
        ),
        LegalSourceConfig(
            name="Pillar Six Indicator Source",
            base_url="https://p6.example",
            domains=["p6.example"],
            adapter="search_engine",
            source_grade="primary",
            languages=["en"],
            pillars=[6],
            indicators=["6.4"],
        ),
    ]

    selected, skipped = service._select_sources(request, sources, ["en"])

    assert [source.name for source in selected] == ["Pillar Six Indicator Source"]
    assert skipped == ["Pillar Seven Indicator Source (pillar/indicator mismatch)"]


def test_request_rejects_indicator_outside_requested_pillars():
    with pytest.raises(ValueError, match=r"7\.4.*\[7\]"):
        DiscoverySearchRequest(
            country_code="SGP",
            pillars=[6],
            indicators=["7.4"],
        )


def test_source_config_rejects_indicator_outside_configured_pillars():
    with pytest.raises(ValueError, match=r"6\.4.*\[7\]"):
        LegalSourceConfig(
            name="Inconsistent Source",
            base_url="https://source.example",
            domains=["source.example"],
            pillars=[7],
            indicators=["6.4"],
        )


def test_source_config_requires_base_hostname_in_exact_domains():
    with pytest.raises(ValueError, match="must be listed in domains"):
        LegalSourceConfig(
            name="Misconfigured Source",
            base_url="https://www.official.example",
            domains=["official.example"],
        )


def test_source_config_rejects_domain_urls_and_base_url_credentials():
    with pytest.raises(ValueError, match="must be a hostname"):
        LegalSourceConfig(
            name="Bad Domain",
            base_url="https://official.example",
            domains=["https://official.example"],
        )

    with pytest.raises(ValueError, match="invalid source domain"):
        LegalSourceConfig(
            name="Wildcard-like Domain",
            base_url="https://ocs.go.th",
            domains=[".ocs.go.th"],
        )

    with pytest.raises(ValueError, match="cannot include credentials"):
        LegalSourceConfig(
            name="Credential URL",
            base_url="https://user:password@official.example",
            domains=["official.example"],
        )


def test_filter_candidate_matches_respects_requested_pillar():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="CHN", pillars=[6])
    candidate = LegalCandidate(
        id="mixed",
        country_code="CHN",
        title="Data export and cybersecurity",
        url="https://flk.npc.gov.cn/detail2.html?token=abc%3D",
        matched_pillars=[6, 7],
        matched_indicators=["6.4", "7.2"],
    )

    filtered = service._filter_candidate_matches(candidate, request)

    assert filtered.matched_indicators == ["6.4"]
    assert filtered.matched_pillars == [6]


def test_filter_candidate_matches_respects_explicit_indicators():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="SGP", pillars=[6, 7], indicators=["7.4"])
    candidate = LegalCandidate(
        id="mixed",
        country_code="SGP",
        title="PDPA and DPO",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        matched_pillars=[7],
        matched_indicators=["7.1", "7.4"],
    )

    filtered = service._filter_candidate_matches(candidate, request)

    assert filtered.matched_indicators == ["7.4"]
    assert filtered.matched_pillars == [7]


def test_filter_candidate_matches_keeps_only_requested_indicator_and_pillar():
    service = DiscoveryService()
    request = DiscoverySearchRequest(country_code="SGP", pillars=[6], indicators=["6.4"])
    candidate = LegalCandidate(
        id="mixed",
        country_code="SGP",
        title="PDPA and DPO",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        matched_pillars=[6, 7],
        matched_indicators=["6.4", "7.4"],
    )

    filtered = service._filter_candidate_matches(candidate, request)

    assert filtered.matched_indicators == ["6.4"]
    assert filtered.matched_pillars == [6]


@pytest.mark.anyio
async def test_source_adapter_failure_does_not_fail_whole_country_search(monkeypatch):
    registry = {
        "languages": ["en"],
        "sources": [
            {
                "name": "Unavailable Official Source",
                "base_url": "https://down.example",
                "domains": ["down.example"],
                "adapter": "failing_adapter",
                "source_grade": "primary",
                "pillars": [7],
                "priority": 100,
            },
            {
                "name": "Working Official Source",
                "base_url": "https://working.example",
                "domains": ["working.example"],
                "adapter": "working_adapter",
                "source_grade": "primary",
                "pillars": [7],
                "priority": 100,
            },
        ],
    }

    class FailingAdapter:
        async def search(self, **_kwargs):
            raise RuntimeError("source temporarily unavailable")

    class WorkingAdapter:
        async def search(self, **_kwargs):
            return [
                RawSearchHit(
                    title="Personal Data Protection Act",
                    url="https://working.example/privacy-act",
                    snippet="Official personal data protection law.",
                    source_adapter="working_adapter",
                    retrieval_mode="fallback",
                    warnings=["Live source search was unavailable; returned configured fallback."],
                )
            ]

    monkeypatch.setattr("discovery.service.get_country_registry", lambda _country: registry)
    monkeypatch.setattr(
        "discovery.service.get_adapter",
        lambda name: FailingAdapter() if name == "failing_adapter" else WorkingAdapter(),
    )

    response = await DiscoveryService().search(
        DiscoverySearchRequest(
            country_code="SGP",
            pillars=[7],
            indicators=["7.1"],
            source_mode="official_only",
            browser_mode="auto",
            limit=5,
        )
    )

    assert [candidate.title for candidate in response.candidates] == [
        "Personal Data Protection Act"
    ]
    assert any(
        "failing_adapter failed" in warning
        for warning in response.diagnostics["warnings"]
    )
