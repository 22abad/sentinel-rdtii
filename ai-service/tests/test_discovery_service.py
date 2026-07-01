from __future__ import annotations

from discovery.registry import get_sources
from discovery.schemas import DiscoverySearchRequest, LegalCandidate, LegalSourceConfig
from discovery.service import DiscoveryService


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
            indicators=["7.4"],
        ),
    ]

    selected, skipped = service._select_sources(request, sources, ["en"])

    assert [source.name for source in selected] == ["Broad Pillar Source"]
    assert skipped == []


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
