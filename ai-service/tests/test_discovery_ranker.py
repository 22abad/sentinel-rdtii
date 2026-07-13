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


def test_indicator_scoped_source_outranks_generic_portal_for_same_pillar():
    sources = get_sources("SGP")
    generic_act = LegalCandidate(
        id="generic-act",
        country_code="SGP",
        title="Interpretation Act",
        url="https://sso.agc.gov.sg/Act/IA1965",
        source_domain="sso.agc.gov.sg",
        source_name="Singapore Statutes Online",
        source_grade="primary",
        document_type="act",
    )
    scoped_treaty = LegalCandidate(
        id="scoped-treaty",
        country_code="SGP",
        title="Australia-Singapore Digital Economy Agreement",
        url=(
            "https://isomer-user-content.by.gov.sg/166/"
            "australia-singapore-digital-economy-agreement.pdf"
        ),
        source_domain="isomer-user-content.by.gov.sg",
        source_name="Ministry of Trade and Industry",
        source_grade="primary",
        document_type="pdf",
        matched_pillars=[6],
        matched_indicators=["6.5"],
        snippet="Binding cross-border transfer of information commitment.",
    )

    ranked = rank_candidates([generic_act, scoped_treaty], sources)

    assert ranked[0].id == "scoped-treaty"
    assert "indicator-specific official source" in ranked[0].reasons


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


def test_validation_scoring_rewards_evidence_and_keeps_fetch_errors_neutral():
    sources = get_sources("SGP")
    base = LegalCandidate(
        id="base",
        country_code="SGP",
        title="Official result",
        url="https://www.pdpc.gov.sg/result",
        source_domain="www.pdpc.gov.sg",
        source_name="Personal Data Protection Commission",
        source_grade="primary",
        matched_pillars=[7],
        matched_indicators=["7.1"],
    )
    verified = base.model_copy(update={"id": "verified", "validation_status": "verified"})
    weak = base.model_copy(update={"id": "weak", "validation_status": "weak"})
    content_failed = base.model_copy(update={
        "id": "content-failed",
        "validation_status": "failed",
        "validation_metadata": {"quality_status": "error_page", "error": ""},
    })
    fetch_failed = base.model_copy(update={
        "id": "fetch-failed",
        "validation_status": "failed",
        "validation_metadata": {"error": "Validation fetch failed: timeout"},
    })

    ranked = rank_candidates([weak, fetch_failed, content_failed, base, verified], sources)
    scores = {candidate.id: candidate.rank_score for candidate in ranked}

    assert scores["verified"] == scores["base"] + 6
    assert scores["fetch-failed"] == scores["base"]
    assert scores["weak"] == scores["base"] - 4
    assert scores["content-failed"] == scores["base"] - 4
    assert "fetched text relevance penalty" in weak.reasons
    assert "fetched content validation penalty" in content_failed.reasons
    assert not any("penalty" in reason for reason in fetch_failed.reasons)
