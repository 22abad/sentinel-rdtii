from __future__ import annotations

from discovery.metadata import (
    canonicalize_url,
    infer_document_type,
    infer_indicator_matches,
    normalize_hit,
    source_allows_url,
    source_domain,
)
from discovery.registry import get_sources
from discovery.schemas import RawSearchHit


def test_canonicalize_url_strips_tracking_params():
    url = canonicalize_url("HTTPS://SSO.AGC.GOV.SG/Act/PDPA2012/?utm_source=x&section=1&fbclid=y")

    assert url == "https://sso.agc.gov.sg/Act/PDPA2012?section=1"


def test_canonicalize_url_preserves_opaque_query_encoding():
    url = canonicalize_url("https://flk.npc.gov.cn/detail2.html?token=abc%3D&utm_source=x")

    assert url == "https://flk.npc.gov.cn/detail2.html?token=abc%3D"


def test_canonicalize_url_preserves_spa_fragment():
    url = canonicalize_url("https://searchlaw.ocs.go.th/council-of-state/#/public/doc/12345")

    assert url == "https://searchlaw.ocs.go.th/council-of-state/#/public/doc/12345"


def test_source_url_matching_uses_exact_configured_hostnames():
    source = get_sources("CHN")[1]

    assert source_allows_url(source, "https://gov.cn/policy")
    assert source_allows_url(source, "https://www.gov.cn/policy")
    assert not source_allows_url(source, "https://subdomain.gov.cn/policy")
    assert not source_allows_url(source, "https://gov.cn.evil.example/policy")
    assert not source_allows_url(source, "https://evil.example/?next=gov.cn")
    assert not source_allows_url(source, "file://gov.cn/policy")
    assert not source_allows_url(source, "https://user:password@gov.cn/policy")
    assert not source_allows_url(source, "https://gov.cn:not-a-port/policy")


def test_source_domain_uses_same_idna_normalization_as_source_config():
    assert source_domain("https://例子.测试/path") == "xn--fsqu00a.xn--0zwm56d"


def test_off_domain_candidate_is_not_inherited_as_primary_source():
    source = get_sources("SGP")[1]
    hit = RawSearchHit(
        title="Personal Data Protection Act commentary",
        url="https://unrelated.example/pdpa",
        snippet="Personal data protection law.",
    )

    candidate = normalize_hit("SGP", source, hit)

    assert candidate.source_grade == "unknown"
    assert candidate.source_domain == "unrelated.example"
    assert "outside the configured source domains" in candidate.warnings[-1]
    assert "high-priority official source" not in candidate.reasons


def test_indicator_match_reasons_stay_aligned_after_sorting():
    _pillars, indicators, reasons = infer_indicator_matches(
        "",
        "",
        "Personal Data Protection Act with a data localization requirement.",
    )

    assert indicators == ["6.1", "7.1"]
    assert reasons == [
        "matches indicator 6.1 terms",
        "matches indicator 7.1 terms",
    ]


def test_indicator_matches_real_australian_act_title_wording():
    _pillars, privacy_indicators, _reasons = infer_indicator_matches(
        "", "", "Privacy Act 1988"
    )
    _pillars, cyber_indicators, _reasons = infer_indicator_matches(
        "", "", "Cyber Security Act 2024"
    )

    assert "7.1" in privacy_indicators
    assert "7.2" in cyber_indicators


def test_infer_document_type_uses_token_boundaries():
    assert infer_document_type(
        "Cross-border Personal Data Transfer Requirements",
        "https://example.test/practice-note",
        "Official law on personal data.",
    ) == "act"


def test_candidate_with_dpo_maps_to_indicator_7_4():
    source = get_sources("SGP")[1]
    hit = RawSearchHit(
        title="Advisory Guidelines on Data Protection Officer Requirement",
        url="https://www.pdpc.gov.sg/guidelines",
        snippet="Organisations must appoint a data protection officer and conduct impact assessment where required.",
    )

    candidate = normalize_hit("SGP", source, hit)

    assert "7.4" in candidate.matched_indicators
    assert 7 in candidate.matched_pillars
    assert candidate.source_grade == "primary"


def test_candidate_with_standard_contract_maps_to_indicator_6_4():
    source = get_sources("CHN")[0]
    hit = RawSearchHit(
        title="个人信息出境 标准合同",
        url="https://flk.npc.gov.cn/detail2.html?id=1",
        snippet="个人信息处理者通过标准合同向境外提供个人信息。",
    )

    candidate = normalize_hit("CHN", source, hit)

    assert "6.4" in candidate.matched_indicators
    assert 6 in candidate.matched_pillars


def test_candidate_extracts_last_update_from_raw_metadata():
    source = get_sources("CHN")[0]
    hit = RawSearchHit(
        title="中华人民共和国个人信息保护法",
        url="https://flk.npc.gov.cn/detail2.html?id=pipl",
        snippet="现行有效",
        raw={"publish_date": "2021-08-20", "status": "现行有效"},
    )

    candidate = normalize_hit("CHN", source, hit)

    assert candidate.last_update == "2021-08-20"
    assert not candidate.warnings


def test_candidate_does_not_treat_act_title_year_as_last_update():
    source = get_sources("SGP")[0]
    hit = RawSearchHit(
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        snippet="An Act to govern the collection, use and disclosure of personal data.",
    )

    candidate = normalize_hit("SGP", source, hit)

    assert candidate.last_update == ""
    assert not candidate.warnings


def test_candidate_does_not_treat_url_path_year_as_last_update():
    source = get_sources("SGP")[1]
    hit = RawSearchHit(
        title="Advisory Guidelines on Key Concepts",
        url="https://www.pdpc.gov.sg/guidelines-and-consultation/2020/03/key-concepts",
        snippet="Guidance on personal data protection.",
    )

    candidate = normalize_hit("SGP", source, hit)

    assert candidate.last_update == ""


def test_candidate_extracts_thai_buddhist_era_year():
    source = get_sources("THA")[0]
    hit = RawSearchHit(
        title="Personal Data Protection Act B.E. 2562",
        url="https://searchlaw.ocs.go.th/council-of-state/#/public/doc/pdpa-2562",
        snippet="Personal Data Protection Act B.E. 2562 is in force.",
    )

    candidate = normalize_hit("THA", source, hit)

    assert candidate.last_update == "01/2019"


def test_candidate_flags_repealed_or_draft_status():
    source = get_sources("SGP")[0]
    hit = RawSearchHit(
        title="Old Privacy Rules",
        url="https://sso.agc.gov.sg/SL/OLD",
        snippet="This instrument has been repealed and is no longer in force.",
        raw={"publish_date": "2010-01-01", "status": "repealed"},
    )

    candidate = normalize_hit("SGP", source, hit)

    assert candidate.last_update == "2010-01-01"
    assert any("repealed" in warning.lower() for warning in candidate.warnings)
