from __future__ import annotations

from discovery.query_builder import build_queries, build_source_queries, terms_for_request
from discovery.registry import get_sources
from discovery.schemas import DiscoverySearchRequest


def test_pillar_6_and_7_generate_indicator_terms():
    req = DiscoverySearchRequest(country_code="SGP", pillars=[6, 7])

    terms = terms_for_request(req)

    assert "cross-border data transfer ban" in terms
    assert "data localization" in terms
    assert "personal data protection act" in terms
    assert "privacy law" in terms


def test_china_request_includes_local_language_terms():
    req = DiscoverySearchRequest(country_code="CHN", pillars=[6], keywords="data export security assessment")

    terms = terms_for_request(req)

    assert terms[0] == "data export security assessment"
    assert "数据出境 禁止" in terms
    assert "数据本地化" in terms


def test_china_english_language_request_excludes_local_language_terms():
    req = DiscoverySearchRequest(country_code="CHN", pillars=[6], languages=["en"])

    terms = terms_for_request(req)

    assert "cross-border data transfer ban" in terms
    assert "数据出境 禁止" not in terms
    assert all("数据" not in term for term in terms)


def test_china_local_language_request_includes_local_language_terms():
    req = DiscoverySearchRequest(country_code="CHN", pillars=[6], languages=["zh"])

    terms = terms_for_request(req)

    assert "数据出境 禁止" in terms
    assert "cross-border data transfer ban" not in terms


def test_build_queries_limits_total_and_uses_site_restriction():
    req = DiscoverySearchRequest(country_code="SGP", pillars=[6, 7])
    sources = get_sources("SGP")

    source_queries = build_queries(req, sources, max_total=10, max_per_source=4)
    flat_queries = [query for queries in source_queries.values() for query in queries]

    assert len(flat_queries) == 10
    assert all(query.startswith("site:") for query in flat_queries)
    assert any(query.startswith("site:sso.agc.gov.sg") for query in flat_queries)


def test_build_source_queries_covers_later_indicators_before_suffixes():
    req = DiscoverySearchRequest(country_code="SGP", pillars=[6, 7])
    source = get_sources("SGP")[0]

    queries = build_source_queries(req, source, max_per_source=8)

    assert any("personal data protection act" in query for query in queries)
    assert any("cybersecurity law" in query for query in queries)
    assert all(not query.endswith(" law law") for query in queries)


def test_build_source_queries_does_not_append_english_suffix_to_local_terms():
    req = DiscoverySearchRequest(country_code="CHN", pillars=[6], languages=["zh"])
    source = get_sources("CHN")[0]

    queries = build_source_queries(req, source, max_per_source=8)

    assert any("数据出境 禁止" in query for query in queries)
    assert all("数据出境 禁止 law" not in query for query in queries)
