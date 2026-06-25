from __future__ import annotations

from discovery.ranker import rank_candidates
from discovery.registry import get_sources
from discovery.schemas import LegalCandidate


def test_official_source_candidate_outranks_secondary_article():
    sources = get_sources("SGP")
    official = LegalCandidate(
        id="official",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_domain="sso.agc.gov.sg",
        source_name="Singapore Statutes Online",
        source_grade="primary",
        document_type="act",
        matched_pillars=[6, 7],
        matched_indicators=["6.4", "7.1"],
        snippet="Personal data may be transferred outside Singapore.",
    )
    secondary = LegalCandidate(
        id="secondary",
        country_code="SGP",
        title="Law firm article about Singapore privacy",
        url="https://example-law-firm.test/privacy-update",
        source_domain="example-law-firm.test",
        source_grade="secondary",
        document_type="secondary",
        matched_pillars=[7],
        matched_indicators=["7.1"],
        snippet="Commentary about the law.",
    )

    ranked = rank_candidates([secondary, official], sources)

    assert ranked[0].id == "official"
    assert ranked[0].rank_score > ranked[1].rank_score
    assert "official statute portal" in ranked[0].reasons


def test_warning_candidate_gets_staleness_penalty():
    sources = get_sources("SGP")
    clean = LegalCandidate(
        id="clean",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_domain="sso.agc.gov.sg",
        source_name="Singapore Statutes Online",
        source_grade="primary",
        document_type="act",
        matched_pillars=[7],
        matched_indicators=["7.1"],
        snippet="Personal data protection law.",
    )
    stale = clean.model_copy(update={
        "id": "stale",
        "warnings": ["candidate appears repealed or no longer in force"],
    })

    ranked = rank_candidates([stale, clean], sources)

    assert ranked[0].id == "clean"
    assert "staleness/version warning penalty" in ranked[1].reasons


def test_operational_warning_does_not_get_staleness_penalty():
    sources = get_sources("CHN")
    clean = LegalCandidate(
        id="adapter-warning",
        country_code="CHN",
        title="中华人民共和国个人信息保护法",
        url="https://flk.npc.gov.cn/detail2.html?token=abc%3D",
        source_domain="flk.npc.gov.cn",
        source_name="National Laws and Regulations Database",
        source_grade="primary",
        document_type="act",
        matched_pillars=[7],
        matched_indicators=["7.1"],
        snippet="个人信息保护",
        warnings=["china_flk adapter failed; using fixture fallback"],
    )

    ranked = rank_candidates([clean], sources)

    assert ranked[0].id == "adapter-warning"
    assert "staleness/version warning penalty" not in ranked[0].reasons


def test_local_language_known_title_gets_exact_title_boost():
    sources = get_sources("CHN")
    candidate = LegalCandidate(
        id="pipl",
        country_code="CHN",
        title="中华人民共和国个人信息保护法",
        url="https://flk.npc.gov.cn/detail2.html?token=abc%3D",
        source_domain="flk.npc.gov.cn",
        source_name="National Laws and Regulations Database",
        source_grade="primary",
        document_type="act",
        matched_pillars=[7],
        matched_indicators=["7.1"],
        snippet="个人信息保护",
    )

    ranked = rank_candidates([candidate], sources)

    assert "title matches known legal instrument" in ranked[0].reasons
