"""Offline tests for the judge-validated submission contract."""

from __future__ import annotations

import csv
import json

import pytest

from schemas import IndicatorMapping
from services.document_fetch import _join_pdf_pages
from submission.pipeline import build_row, page_location_reference
from submission.schema import (
    CSV_COLUMNS,
    CSV_HEADERS,
    REQUIRED_SUBMISSION_FIELDS,
    SubmissionRow,
    discovery_tag_for_method,
    economy_code,
    economy_display_name,
    extract_law_number_ref,
    extract_year,
    indicator_to_rdtii_code,
    validate_submission_rows,
)
from submission.writer import write_csv, write_json


def test_csv_columns_frozen_order():
    # Judges validate programmatically — this order must not change silently.
    assert CSV_COLUMNS == (
        "economy", "law_name", "law_number_ref", "last_amended", "indicator_id",
        "article", "discovery_tag", "location_reference", "verbatim_snippet",
        "mapping_rationale", "source_url", "confidence", "notes",
    )
    assert len(CSV_COLUMNS) == 13


def test_csv_headers_match_official_output_template():
    # The submission CSV's HEADER ROW must match the official Structured Output
    # Template (OUTPUT_TEMPLATE_31MAY.xlsx) exactly — Title Case with spaces.
    # Judges validate programmatically, so this is the header we write.
    assert CSV_HEADERS == (
        "Economy", "Law Name", "Law Number / Ref", "Last Amended", "Indicator ID",
        "Article / Section", "Discovery Tag", "Location Reference", "Verbatim Snippet",
        "Mapping Rationale", "Source URL", "Confidence", "Notes",
    )
    assert len(CSV_HEADERS) == len(CSV_COLUMNS)


def test_submission_validator_rejects_empty_results_by_default():
    with pytest.raises(ValueError, match="No judge-usable provisions"):
        validate_submission_rows([])


def test_submission_validator_allows_explicit_research_empty_results():
    validate_submission_rows([], allow_empty=True)


def test_submission_validator_drops_incomplete_rows_but_keeps_output():
    assert REQUIRED_SUBMISSION_FIELDS == (
        "law_name", "last_amended", "indicator_id", "article",
        "verbatim_snippet", "source_url",
    )
    good = SubmissionRow(
        economy="Singapore", law_name="Good Act 2026", indicator_id="P6-I1",
        article="Section 1", location_reference="p. 1",
        verbatim_snippet="A complete provision that reads like a real statutory clause.",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
    )
    bad = SubmissionRow(  # no source_url -> unusable, must be dropped
        economy="Singapore", law_name="Bad Act 2026", indicator_id="P6-I1",
        article="Section 1",
        verbatim_snippet="A provision with enough substance to be a real clause.",
        source_url="",
    )
    kept = validate_submission_rows([good])
    assert [r.law_name for r in kept] == ["Good Act 2026"]
    # One bad row is dropped, the good one survives — never zero output.
    kept = validate_submission_rows([bad, good])
    assert [r.law_name for r in kept] == ["Good Act 2026"]
    # All-bad with allow_empty -> empty list, no raise.
    assert validate_submission_rows([bad], allow_empty=True) == []
    # All-bad without allow_empty -> raise (nothing usable).
    with pytest.raises(ValueError, match="No judge-usable provisions"):
        validate_submission_rows([bad])


def test_validator_drops_off_topic_goods_laws_from_p6_p7():
    from submission.schema import _is_off_topic_law

    # goods/agriculture law mapped to P6/P7 -> out of scope
    assert _is_off_topic_law("Wine Export Charge Act", "P7-I5")
    assert _is_off_topic_law("Primary Industries (Customs) Charges Regulations", "P7-I3")
    # a real data law is fine; the same goods law under Pillar 1 is not our concern
    assert not _is_off_topic_law("Personal Data Protection Act 2012", "P6-I4")
    assert not _is_off_topic_law("Wine Export Charge Act", "P1-I1")

    good = SubmissionRow(
        economy="Australia", law_name="Privacy Act 1988", indicator_id="P7-I1",
        article="s 6", location_reference="p. 1",
        verbatim_snippet="A complete data-protection provision that reads like a clause.",
        source_url="https://www.legislation.gov.au/C2004A03712/latest/text",
    )
    wine = SubmissionRow(
        economy="Australia", law_name="Wine Export Charge Act", indicator_id="P7-I5",
        article="s 5", location_reference="p. 2",
        verbatim_snippet="A charge is imposed on the export of grape products from Australia.",
        source_url="https://www.legislation.gov.au/C2025G00364/latest/text",
    )
    kept = validate_submission_rows([good, wine])
    assert [r.law_name for r in kept] == ["Privacy Act 1988"]


def test_validator_drops_repealed_but_keeps_repeal_acts_and_quotes():
    from submission.schema import _is_repealed_law

    # explicit "(Repealed)" status marker -> excluded per the methodology
    assert _is_repealed_law("Spam Act 2003 (Repealed)")
    assert _is_repealed_law("Data Protection Act 1998 [REPEALED]")
    # an in-force "Repeal(s) Act" is NOT a repealed law; a quote mentioning repeal
    # is not a status marker either
    assert not _is_repealed_law("Statute Law (Repeals) Act 2016")
    assert not _is_repealed_law("Privacy Amendment (Repeal) Act 2024")
    assert not _is_repealed_law("Personal Data Protection Act 2012")

    good = SubmissionRow(
        economy="Australia", law_name="Privacy Act 1988", indicator_id="P7-I1",
        article="s 6", location_reference="p. 1",
        verbatim_snippet="A complete data-protection provision that reads like a clause.",
        source_url="https://www.legislation.gov.au/C2004A03712/latest/text",
    )
    repealed = SubmissionRow(
        economy="Australia", law_name="Spam Act 2003 (Repealed)", indicator_id="P7-I3",
        article="s 5", location_reference="p. 2",
        verbatim_snippet="This provision governs the handling of electronic messages and data.",
        source_url="https://www.legislation.gov.au/C2004A01214/latest/text",
    )
    kept = validate_submission_rows([good, repealed])
    assert [r.law_name for r in kept] == ["Privacy Act 1988"]


def test_validator_drops_name_or_heading_quotes_but_keeps_real_provisions():
    from submission.schema import _is_nonsubstantive_quote

    # verbatim = law name / a bare section heading -> not an operative provision
    assert _is_nonsubstantive_quote(
        "Credit Reporting Agencies Act 2010 (Act 710)",
        "Credit Reporting Agencies Act 2010 (Act 710)",
    )
    assert _is_nonsubstantive_quote(
        "Cyber Security Act 2024 (No. 98, 2024)",
        "Cyber Security Act 2024 (No. 98, 2024): Section 3 Objects",
    )
    # a real provision that opens with the statute name but states an obligation
    # is KEPT (it has operative language)
    assert not _is_nonsubstantive_quote(
        "Privacy Act 1988",
        "A personal information custodian may disclose personal information only where...",
    )
    assert not _is_nonsubstantive_quote(
        "Personal Data Protection Act 2012",
        "An organisation must not transfer personal data outside Singapore except as prescribed.",
    )

    good = SubmissionRow(
        economy="Australia", law_name="Privacy Act 1988", indicator_id="P7-I1",
        article="s 6", location_reference="p. 1",
        verbatim_snippet="An organisation must take reasonable steps to protect personal information it holds.",
        source_url="https://www.legislation.gov.au/C2004A03712/latest/text",
    )
    heading = SubmissionRow(
        economy="Malaysia", law_name="Credit Reporting Agencies Act 2010 (Act 710)",
        indicator_id="P7-I1", article="title", location_reference="p. 1",
        verbatim_snippet="Credit Reporting Agencies Act 2010 (Act 710)",
        source_url="https://lom.agc.gov.my/act-710",
    )
    kept = validate_submission_rows([good, heading])
    assert [r.law_name for r in kept] == ["Privacy Act 1988"]


def test_validator_drops_non_regulatory_indicator_rows():
    from submission.schema import NON_REGULATORY_INDICATORS

    # 6.5 (not in a binding data-transfer agreement) is non-regulatory — derived
    # from treaty membership, not a law — so a law-derived P6-I5 row is dropped.
    assert "P6-I5" in NON_REGULATORY_INDICATORS
    good = SubmissionRow(
        economy="Singapore", law_name="Personal Data Protection Act 2012",
        indicator_id="P6-I4", article="s 26", location_reference="p. 1",
        verbatim_snippet="An organisation must not transfer personal data outside Singapore except as prescribed.",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
    )
    non_reg = SubmissionRow(
        economy="Singapore", law_name="Some Free Trade Agreement Act",
        indicator_id="P6-I5", article="Art 14.2", location_reference="p. 2",
        verbatim_snippet="The parties commit to allowing cross-border transfer of information by electronic means.",
        source_url="https://sso.agc.gov.sg/Act/FTA",
    )
    kept = validate_submission_rows([good, non_reg])
    assert [r.indicator_id for r in kept] == ["P6-I4"]


def test_validator_drops_government_data_measures_but_keeps_personal_data():
    from submission.schema import _is_government_data_measure

    # Archives Act s24 regulates Commonwealth records → not scoreable.
    assert _is_government_data_measure(
        "Archives Act 1983",
        "the destruction or other disposal of a Commonwealth record",
    )
    # Evidence Act "official records relating to affairs of State" → government data.
    assert _is_government_data_measure(
        "Evidence Act",
        "produce any unpublished official records relating to affairs of State",
    )
    # Identity Verification Act mentions a Commonwealth record but regulates
    # facial images / personal data → KEEP.
    assert not _is_government_data_measure(
        "Identity Verification Services Act 2023",
        "take reasonable steps to destroy each facial image of an individual",
    )
    assert not _is_government_data_measure(
        "Personal Data Protection Act 2012",
        "an organisation must not transfer personal data outside Singapore",
    )

    good = SubmissionRow(
        economy="Australia", law_name="Privacy Act 1988", indicator_id="P7-I1",
        article="s 6", location_reference="p. 1",
        verbatim_snippet="A complete data-protection provision that reads like a clause.",
        source_url="https://www.legislation.gov.au/C2004A03712/latest/text",
    )
    gov = SubmissionRow(
        economy="Australia", law_name="Archives Act 1983", indicator_id="P7-I3",
        article="s 24", location_reference="p. 2",
        verbatim_snippet="A person must not engage in the destruction or other disposal of a Commonwealth record.",
        source_url="https://www.legislation.gov.au/C2004A02796/latest/text",
    )
    kept = validate_submission_rows([good, gov])
    assert [r.law_name for r in kept] == ["Privacy Act 1988"]


def test_canonicalize_collapses_one_url_many_names():
    from submission.schema import canonicalize_law_names_per_url

    url = "https://www.legislation.gov.au/C2023A00115/latest/text"
    seed = SubmissionRow(
        economy="Australia", law_name="Identity Verification Services Act 2023", indicator_id="P7-I1",
        article="s 10", location_reference="p. 1", retrieval_method="cached_discovery",
        verbatim_snippet="A complete provision reading like a real statutory clause.", source_url=url)
    mislabel1 = SubmissionRow(
        economy="Australia", law_name="Australia Privacy Act, 1988", indicator_id="P7-I1",
        article="s 9", location_reference="p. 2", retrieval_method="official_search",
        verbatim_snippet="Another complete provision reading like a real clause.", source_url=url)
    mislabel2 = SubmissionRow(
        economy="Australia", law_name="Participation Agreement Act, 2020", indicator_id="P7-I4",
        article="(2)", location_reference="p. 3", retrieval_method="official_search",
        verbatim_snippet="A third distinct provision reading like a real clause.", source_url=url)
    out = canonicalize_law_names_per_url([seed, mislabel1, mislabel2])
    # the authoritative seed name wins for every row on that URL
    assert {r.law_name for r in out} == {"Identity Verification Services Act 2023"}
    assert "normalised to the source document" in (mislabel1.notes or "")

    # no seed on the URL -> the most common name wins
    u2 = "https://gov.example/actX"
    rows = [
        SubmissionRow(economy="Australia", law_name="Data Act 2021", indicator_id="P6-I4",
                      article="s 1", location_reference="p.1", retrieval_method="official_search",
                      verbatim_snippet="A complete provision reading like a real clause.", source_url=u2),
        SubmissionRow(economy="Australia", law_name="Data Act 2021", indicator_id="P6-I4",
                      article="s 2", location_reference="p.2", retrieval_method="official_search",
                      verbatim_snippet="Another complete provision reading like a real clause.", source_url=u2),
        SubmissionRow(economy="Australia", law_name="Some Other Act 1999", indicator_id="P7-I1",
                      article="s 3", location_reference="p.3", retrieval_method="official_search",
                      verbatim_snippet="A third complete provision reading like a real clause.", source_url=u2),
    ]
    canonicalize_law_names_per_url(rows)
    assert {r.law_name for r in rows} == {"Data Act 2021"}


def test_validator_flags_url_reused_by_three_law_names():
    url = "https://www.legislation.gov.au/C2023A00115/latest/text"
    names = ["Identity Verification Services Act 2023", "Identity Verification Act 2023",
             "National Driver Licence Facial Recognition Act"]
    rows = [
        SubmissionRow(
            economy="Australia", law_name=n, indicator_id="P7-I1", article="s 10",
            location_reference="p. 1",
            verbatim_snippet="A complete data-handling provision reading like a real clause.",
            source_url=url,
        )
        for n in names
    ]
    kept = validate_submission_rows(rows)
    # none dropped (one name is the real law), but every row carries the note flag
    assert len(kept) == 3
    assert all("hallucination check" in (r.notes or "") for r in kept)


def test_validator_drops_fragment_quotes_but_keeps_title_and_provision():
    from submission.schema import _is_fragment_quote, _is_weak_evidence

    # Mid-sentence fragments the extractor emits by mistake -> dropped.
    assert _is_fragment_quote("Personal Data Protection Act 2012", "personal data")
    assert _is_fragment_quote("Information Privacy Act 2009 (QLD)", "data processor")
    assert _is_fragment_quote("Information Privacy Act 2009 (QLD)", "privacy principle requirements")
    # A framework-existence title-quote (e.g. P7-I1 evidence) -> kept, even short.
    assert not _is_fragment_quote("Privacy Act 1988", "Privacy Act 1988")
    assert not _is_fragment_quote(
        "Singapore Personal Data Protection Act (PDPA), 2012", "Personal Data Protection Act 2012"
    )
    # A substantive provision -> kept.
    assert not _is_fragment_quote(
        "PDPA", "An organisation must not transfer any personal data outside Singapore unless"
    )

    # A bare title-quote is evidence only for the framework indicator (P7-I1);
    # mapped to a provision-specific indicator it is too weak and is dropped.
    assert not _is_weak_evidence("Privacy Act 1988", "Privacy Act 1988", "P7-I1")
    assert _is_weak_evidence("Privacy Act 1988", "Privacy Act 1988", "P7-I5")
    assert _is_weak_evidence("Personal Data Protection Act 2012", "Personal Data Protection Act 2012", "P7-I3")
    # A substantive provision is valid for any indicator, title or not.
    assert not _is_weak_evidence(
        "PDPA", "An organisation must cease to retain documents containing personal data.", "P7-I3"
    )

    # End-to-end: a fragment row is dropped from the submission, a good row kept.
    frag = SubmissionRow(
        economy="Australia", law_name="Information Privacy Act 2009 (QLD)",
        indicator_id="P7-I4", article="", verbatim_snippet="privacy principle requirements",
        source_url="https://legislation.qld.gov.au/x",
    )
    prov = SubmissionRow(
        economy="Singapore", law_name="Personal Data Protection Act 2012",
        indicator_id="P7-I3", article="Section 25",
        verbatim_snippet="An organisation must cease to retain documents containing personal data.",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
    )
    kept = validate_submission_rows([frag, prov])
    assert [r.indicator_id for r in kept] == ["P7-I3"]


def test_validator_drops_agreements_and_blog_sources():
    from submission.schema import _is_out_of_scope_source

    # International instruments are not domestic measures the RDTII scores.
    assert _is_out_of_scope_source("Singapore-Australia Free Trade Agreement", "https://x.gov.sg/a")
    assert _is_out_of_scope_source("Australia-Singapore Digital Economy Agreement (DEA)", "https://x")
    assert _is_out_of_scope_source("Comprehensive and Progressive Agreement for TPP", "https://x")
    # A blog/news page is not authoritative legal text, even on an official domain.
    assert _is_out_of_scope_source(
        "Personal Data Protection Act 2012",
        "https://www.imda.gov.sg/resources/blog/blog-articles/2021/11/mastering-the-must-dos",
    )
    # A trade-agreement chapter whose name hides the agreement, caught by URL.
    assert _is_out_of_scope_source(
        "Chapter 14 Electronic Commerce", "https://fta.miti.gov.my/miti-fta/resources/Text of TPPA"
    )
    # A foreign jurisdiction named in a domestic-law title is a mislabel.
    assert _is_out_of_scope_source(
        "Hong Kong Personal Data (Privacy) Ordinance", "https://lom.agc.gov.my/act-detail.php?act=709"
    )
    # A real statute on its official Act page is in scope.
    assert not _is_out_of_scope_source("Personal Data Protection Act 2012", "https://sso.agc.gov.sg/Act/PDPA2012")
    assert not _is_out_of_scope_source("Privacy Act 1988", "https://www.legislation.gov.au/C2004A03712")


def test_cap_and_dedupe_merge_law_name_variants():
    from submission.schema import cap_rows_per_law, dedupe_submission_rows

    def mk(ind, name, quote):
        return SubmissionRow(economy="Malaysia", law_name=name, indicator_id=ind,
                             verbatim_snippet=quote, source_url="https://lom.agc.gov.my/act?709")
    # The same MYS PDPA under five title variants (a live run's shape).
    variants = ["Personal Data Protection Act 2010", "PERSONAL DATA PROTECTION ACT 2010",
                "Malaysia Personal Data Protection Act 2010", "Personal Data Protection Act (PDPA) 2010",
                "Personal Data Protection Act 2010 (Act 709)"]
    rows = [mk("P7-I1", v, f"a substantive provision clause number {i} about personal data handling")
            for i, v in enumerate(variants) for _ in range(3)]  # 15 rows, one real law
    capped = cap_rows_per_law(rows, cap=8)
    assert len(capped) == 8  # collapsed to one law, capped — not 15 across "5 laws"

    # Dedupe treats title variants + same quote as one.
    dup = [mk("P6-I4", "Personal Data Protection Act 2010", "identical cross-border transfer clause text here"),
           mk("P6-I4", "Malaysia Personal Data Protection Act 2010", "identical cross-border transfer clause text here")]
    assert len(dedupe_submission_rows(dup)) == 1

    # End-to-end: agreement + blog rows drop, the statute row survives.
    agreement = SubmissionRow(
        economy="Singapore", law_name="Singapore-Australia Free Trade Agreement",
        indicator_id="P6-I5", article="Article 14.2",
        verbatim_snippet="binding commitments to allow cross-border data flows apply",
        source_url="https://isomer-user-content.by.gov.sg/166/safta",
    )
    blog = SubmissionRow(
        economy="Singapore", law_name="Personal Data Protection Act 2012", indicator_id="P7-I1",
        article="Whole Act (framework-level evidence)",
        verbatim_snippet="Singapore put into place the PDPA to regulate the collection of data.",
        source_url="https://www.imda.gov.sg/resources/blog/blog-articles/2021/11/mastering",
    )
    statute = SubmissionRow(
        economy="Singapore", law_name="Personal Data Protection Act 2012", indicator_id="P6-I4",
        article="Section 26",
        verbatim_snippet="An organisation must not transfer any personal data outside Singapore unless",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
    )
    kept = validate_submission_rows([agreement, blog, statute])
    assert [r.indicator_id for r in kept] == ["P6-I4"]


@pytest.mark.parametrize(
    ("internal", "expected"),
    [
        ("6.1", "P6-I1"), ("7.3", "P7-I3"), ("6.5", "P6-I5"), ("P6-I1", "P6-I1"),
        # Round 2: double-digit and dotted sub-indicators
        ("4.10", "P4-I10"), ("12.4.1", "P12-I4.1"), ("P12-I4.1", "P12-I4.1"),
    ],
)
def test_indicator_code_conversion(internal, expected):
    assert indicator_to_rdtii_code(internal) == expected


def test_indicator_code_rejects_garbage():
    with pytest.raises(ValueError):
        indicator_to_rdtii_code("banana")


@pytest.mark.parametrize(
    ("method", "tag"),
    [
        ("known_mapping", "KNOWN"),
        ("cached_discovery", "NEW"),
        ("official_search", "NEW"),
        ("web_search", "NEW"),
        ("fixture", "KNOWN"),
        ("fallback", "KNOWN"),
        ("", "NEW"),
    ],
)
def test_discovery_tag(method, tag):
    assert discovery_tag_for_method(method) == tag


def test_economy_resolution():
    assert economy_code("Singapore") == "SGP"
    assert economy_code("sgp") == "SGP"
    assert economy_display_name("MYS") == "Malaysia"
    with pytest.raises(ValueError):
        economy_code("Atlantis")


def test_round2_economy_resolution():
    # The 7 Round 2 economies all resolve; display names match the official
    # Round 2 database sheet names so outputs join against the baseline.
    assert economy_code("Indonesia") == "IDN"
    assert economy_code("Lao PDR") == "LAO"
    assert economy_code("Laos") == "LAO"
    assert economy_code("Russia") == "RUS"
    assert economy_display_name("RUS") == "Russian Federation"
    assert economy_display_name("LAO") == "Lao PDR"
    assert economy_code("Mongolia") == "MNG"


def test_round2_indicator_ids_are_in_output_schema():
    # Every normalised indicator id in the extracted methodology must be an
    # allowed IndicatorId, or the orchestrator would silently skip it.
    import json
    from pathlib import Path
    from typing import get_args

    from schemas import IndicatorId

    meth_path = Path(__file__).resolve().parents[2] / "data" / "rdtii21_methodology.json"
    methodology = json.loads(meth_path.read_text(encoding="utf-8"))
    allowed = set(get_args(IndicatorId))
    missing = {m["indicator_id"] for m in methodology} - allowed
    assert not missing, f"methodology ids missing from IndicatorId: {sorted(missing)}"
    assert len(methodology) == 61


def test_law_number_and_year_extraction():
    assert extract_law_number_ref("Companies Act 2016 (Act 777)") == "Act 777"
    assert extract_law_number_ref("Personal Data Protection Act 2010") == ""
    assert extract_year("Amended 2020", "enacted 1988") == "2020"
    assert extract_year("no dates here") == ""


def test_rationale_clipped_to_300_chars():
    long_text = "word " * 200
    clipped = SubmissionRow.clip_rationale(long_text)
    assert len(clipped) <= 301  # 300 + ellipsis
    assert clipped.endswith("…")


def _sample_mapping() -> IndicatorMapping:
    return IndicatorMapping(
        pillar=6,
        indicator="6.4",
        score=1.0,
        verbatim_quote="An organisation must not transfer any personal data outside Singapore except in accordance with requirements prescribed under this Act.",
        quote_start=100,
        quote_end=230,
        article_clause="Section 26",
        source_legislation="Personal Data Protection Act 2012",
        last_update="Amended 2020",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
        impact="Conditional cross-border flow regime, not an outright ban.",
        requires_human_review=True,
        flag_reasons=["scope needs legal review"],
    )


class _FakeCandidate:
    discovery_method = "known_mapping"
    title = "Personal Data Protection Act 2012"
    url = "https://sso.agc.gov.sg/Act/PDPA2012"
    last_update = "2012"
    confidence = 0.91
    warnings = ["bilingual source"]


class _FixtureCandidate(_FakeCandidate):
    discovery_method = "official_search"
    retrieval_mode = "fixture"
    title = "Configured Fixture Act 2099"


def test_confidence_reflects_human_review_gate():
    """Confidence (official col 12) must AGREE with the review gate: any row
    routed to a human sits below 0.80; a clean row sits high. Guards against
    the old two-state flag (1.0 seed / 0.8 live) that ignored the gates."""
    text = "x" * 100 + _sample_mapping().verbatim_quote + "y" * 200

    flagged = build_row(
        _sample_mapping(),  # requires_human_review=True, 1 flag
        economy_display="Singapore",
        candidate=_FakeCandidate(),
        source_text=text,
        doc_meta={"quality": "good"},
    )
    assert flagged.requires_human_review is True
    assert flagged.confidence < 0.80

    clean = _sample_mapping()
    clean.requires_human_review = False
    clean.flag_reasons = []
    clean_row = build_row(
        clean,
        economy_display="Singapore",
        candidate=_FakeCandidate(),
        source_text=text,
        doc_meta={"quality": "good"},
    )
    assert clean_row.requires_human_review is False
    assert clean_row.confidence >= 0.80


def test_build_row_maps_all_fields():
    text = "x" * 100 + _sample_mapping().verbatim_quote + "y" * 200
    row = build_row(
        _sample_mapping(),
        economy_display="Singapore",
        candidate=_FakeCandidate(),
        source_text=text,
        doc_meta={"quality": "good", "pdf_is_scanned": False},
    )
    assert row.economy == "Singapore"
    assert row.indicator_id == "P6-I4"
    assert row.discovery_tag == "KNOWN"
    assert row.article == "Section 26"
    assert row.last_amended == "2020"
    assert row.source_url.endswith("PDPA2012")
    # This mapping is flagged for human review (1 flag), so confidence must
    # sit BELOW the official 0.80 review threshold — not the old hardcoded 0.8.
    assert row.confidence == pytest.approx(0.75)
    assert row.confidence < 0.80
    assert row.source_confidence == pytest.approx(0.91)
    assert row.amendment_version_date == "Amended 2020"
    assert "requires human review" in row.notes
    assert "bilingual source" in row.notes
    # Context windows populated for the JSON audit view.
    assert row.raw_context_before or row.raw_context_after
    assert row.confidence_type == "mapping_confidence"


def test_amendment_year_from_text_is_amendment_specific():
    from submission.pipeline import amendment_year_from_text

    # Explicit amendment language -> year is picked up.
    assert amendment_year_from_text("This Act was last amended in March 2022.") == "2022"
    assert amendment_year_from_text("amended on 1 July 2019 by Act 5") == "2019"
    # A bare enactment year is NOT an amendment -> stays empty.
    assert amendment_year_from_text("Personal Data Protection Act 2012. Section 1 ...") == ""
    # A "current as at" consolidation date must NOT be read as an amendment year.
    assert amendment_year_from_text("Act 2009 No. 14, current as at 1 July 2026") == ""
    assert amendment_year_from_text("") == ""


def test_build_row_fills_last_amended_from_document_text():
    # Live finds usually carry no candidate last_update; the amendment year then
    # comes from the document's own text rather than being left blank.
    mapping = _sample_mapping().model_copy(update={"last_update": ""})
    text = (
        "x" * 100
        + mapping.verbatim_quote
        + "y" * 50
        + " This Act was last amended in 2023. "
    )
    row = build_row(mapping, economy_display="Singapore", source_text=text)
    assert row.last_amended == "2023"

    # No amendment language anywhere -> honest blank, never a guessed year.
    plain = "z" * 100 + mapping.verbatim_quote + "w" * 100
    row2 = build_row(mapping, economy_display="Singapore", source_text=plain)
    assert row2.last_amended == "Not stated in source"


def test_build_row_surfaces_curated_currency_version_in_notes():
    # A curated seed carries a verified "current version" label + check date;
    # the row note must surface it so a reviewer sees we are on the current
    # consolidated version, not a stale copy.
    text = "x" * 100 + _sample_mapping().verbatim_quote + "y" * 100
    row = build_row(
        _sample_mapping(),
        economy_display="Singapore",
        source_text=text,
        doc_meta={
            "law_version": "2020 Revised Edition (Act 26 of 2012)",
            "currency_checked_at": "2026-07-13",
        },
    )
    assert "current version: 2020 Revised Edition (Act 26 of 2012)" in row.notes
    assert "currency verified 2026-07-13" in row.notes

    # A live find with no curated version adds no currency note.
    live = build_row(_sample_mapping(), economy_display="Singapore", source_text=text)
    assert "current version:" not in live.notes


def test_pdf_offsets_resolve_to_page_and_cross_page_range():
    text, spans = _join_pdf_pages(["first page", "second page quote", "third page"])
    quote_start = text.index("page quote")
    quote_end = quote_start + len("page quote")

    assert page_location_reference(spans, quote_start, quote_end) == "p. 2"
    assert page_location_reference(
        spans,
        text.index("quote"),
        text.index("third") + len("third"),
    ) == "pp. 2–3"

    mapping = _sample_mapping().model_copy(update={
        "verbatim_quote": "page quote",
        "quote_start": quote_start,
        "quote_end": quote_end,
    })
    row = build_row(
        mapping,
        economy_display="Singapore",
        source_text=text,
        doc_meta={"page_char_spans": spans, "pdf_type": "pure_text"},
    )
    assert row.location_reference == "p. 2"


def test_html_location_prefers_anchor_then_dom_path_then_legal_section():
    mapping = _sample_mapping()

    anchored = build_row(
        mapping,
        economy_display="Singapore",
        doc_meta={"final_url": "https://official.example/act#section-26"},
    )
    assert anchored.location_reference.endswith("#section-26")

    dom = build_row(
        mapping,
        economy_display="Singapore",
        doc_meta={
            "final_url": "https://official.example/act",
            "html_selector": "main article:nth-of-type(2)",
        },
    )
    assert dom.location_reference.endswith("(DOM: main article:nth-of-type(2))")

    section = build_row(
        mapping,
        economy_display="Singapore",
        doc_meta={"final_url": "https://official.example/act"},
    )
    assert section.location_reference.endswith("(Section 26)")


def test_framework_title_quote_gets_explicit_whole_act_citation():
    mapping = _sample_mapping().model_copy(update={
        "indicator": "7.1",
        "article_clause": "",
        "verbatim_quote": "Personal Data Protection Act 2012",
        "source_legislation": "Personal Data Protection Act 2012",
    })
    row = build_row(
        mapping,
        economy_display="Singapore",
        doc_meta={"location_reference": "https://sso.agc.gov.sg/Act/PDPA2012"},
    )
    assert row.article == "Whole Act (framework-level evidence)"
    assert row.location_reference.endswith("(Whole Act (framework-level evidence))")
    assert row.last_amended == "2020"


def test_detailed_novelty_fields_are_json_only():
    row = SubmissionRow(
        economy="Singapore",
        law_name="Test Act 2026",
        indicator_id="P6-I1",
        discovery_tag="NEW",
        novelty_type="NEW_PROVISION",
        canonical_law_id="SGP:test-act",
        amendment_version_date="2026-07-14",
        normalized_article="section 2",
        normalized_quote_hash="abc123",
        verbatim_snippet="Exact provision.",
    )

    assert "novelty_type" not in row.csv_record()
    assert row.json_record()["novelty_type"] == "NEW_PROVISION"
    assert row.json_record()["canonical_law_id"] == "SGP:test-act"


def test_audit_metadata_fields_are_json_only():
    row = SubmissionRow(
        economy="Singapore",
        law_name="Test Act 2026",
        indicator_id="P6-I1",
        verbatim_snippet="Exact provision.",
        model_version="model-v2",
        source_file_sha256="a" * 64,
        source_pdf_path="/evidence/test.pdf",
        pdf_type="mixed",
        confidence_type="mapping_confidence",
    )

    json_record = row.json_record()
    for field in (
        "model_version", "source_file_sha256", "source_pdf_path",
        "pdf_type", "confidence_type",
    ):
        assert field not in row.csv_record()
        assert field in json_record


def test_build_row_never_marks_fixture_new_and_preserves_fixture_fetch_audit():
    row = build_row(
        _sample_mapping(),
        economy_display="Singapore",
        candidate=_FixtureCandidate(),
        doc_meta={
            "final_url": "https://sso.agc.gov.sg/Act/PDPA2012",
            "http_status": 200,
            "fetch_method": "download",
        },
    )

    assert row.discovery_tag == "KNOWN"
    assert row.retrieval_method == "fixture"
    assert row.retrieval_mode == "fixture"
    assert row.final_url.endswith("PDPA2012")
    assert row.http_status == 200
    assert row.fetch_method == "download"


def test_csv_and_json_round_trip(tmp_path):
    row = build_row(
        _sample_mapping(),
        economy_display="Singapore",
        candidate=_FakeCandidate(),
        source_text="",
    )
    csv_path = write_csv([row], tmp_path / "out.csv")
    json_path = write_json([row], tmp_path / "out.json", meta={"economy": "Singapore"})

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        # The submission CSV header must match the official Structured Output
        # Template exactly (Title Case), NOT the internal snake_case field keys.
        assert header == list(CSV_HEADERS)
        assert len(header) == len(CSV_COLUMNS)
        first = next(reader)
        assert first[list(CSV_COLUMNS).index("indicator_id")] == "P6-I4"
        # Flagged-for-review row → confidence below the 0.80 review threshold.
        assert first[list(CSV_COLUMNS).index("confidence")] == "0.75"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["meta"]["economy"] == "Singapore"
    assert payload["provisions"][0]["indicator_id"] == "P6-I4"
    # Extended metadata present only in JSON.
    assert "raw_context_before" in payload["provisions"][0]


def test_infer_article_reference_backfills_nearest_heading():
    from submission.pipeline import infer_article_reference

    text = (
        "Section 25. Retention.\nAn organisation must cease to retain documents.\n"
        "Section 26(2). Transfer.\nAn organisation must not transfer personal data "
        "outside Singapore unless prescribed requirements are met."
    )
    quote_start = text.index("An organisation must not transfer")
    assert infer_article_reference(text, quote_start) == "Section 26(2)"
    # Nearest heading wins, not the first.
    early = text.index("An organisation must cease")
    assert infer_article_reference(text, early) == "Section 25"
    # No high-precision heading -> empty, never a guess.
    assert infer_article_reference("just some text with 9. numbering", 20) == ""
    # Multilingual: Chinese and Indonesian heading forms.
    zh = "第 19 条 数据处理者应当履行下列义务。"
    assert infer_article_reference(zh, zh.index("数据处理者")) == "第 19 条"
    idn = "Pasal 21\nSetiap orang berhak atas perlindungan data pribadi."
    assert infer_article_reference(idn, idn.index("Setiap")) == "Pasal 21"


def test_build_row_backfills_article_and_flags_it():
    text = (
        "Paragraph 3. Purchase preference.\n"
        "Purchase preference shall be given to local suppliers in all procurements."
    )
    quote = "Purchase preference shall be given to local suppliers"
    start = text.index(quote)
    mapping = IndicatorMapping(
        pillar=2, indicator="2.1", score=0.5, verbatim_quote=quote,
        quote_start=start, quote_end=start + len(quote),
        article_clause="",  # LLM left it blank
        source_legislation="India Public Procurement Order, 2017",
        last_update="", source_url="", impact="Local preference in procurement.",
    )
    row = build_row(mapping, economy_display="India", source_text=text)
    assert row.article == "Paragraph 3"
    assert "article inferred from document structure" in row.notes
    # An explicit LLM-provided clause is never overridden.
    mapping2 = mapping.model_copy(update={"article_clause": "Paragraph 3(b)"})
    row2 = build_row(mapping2, economy_display="India", source_text=text)
    assert row2.article == "Paragraph 3(b)"
    assert "inferred" not in row2.notes


def test_attribution_note_when_quote_source_differs_from_named_law():
    # LLM names the statute the provision talks about (PSSA) while the quote
    # physically lives in RBI guidelines — the note must say so.
    mapping = _sample_mapping().model_copy(update={
        "source_legislation": "Payment and Settlement Systems Act (PSSA), 2007",
    })

    class _GuidelinesCandidate(_FakeCandidate):
        title = "RBI Guidelines on Regulation of Payment Aggregators 2020"
        discovery_method = "known_mapping"

    row = build_row(mapping, economy_display="India", candidate=_GuidelinesCandidate())
    assert "quoted from document: RBI Guidelines on Regulation" in row.notes
    # No note when names agree.
    row2 = build_row(_sample_mapping(), economy_display="Singapore", candidate=_FakeCandidate())
    assert "quoted from document" not in row2.notes


def test_title_quote_guard_flags_name_only_quotes():
    # A quote that is just the document's own name evidences nothing.
    mapping = _sample_mapping().model_copy(update={
        "verbatim_quote": "Personal Data Protection Act 2012",
        "source_legislation": "Personal Data Protection Act 2012",
    })
    row = build_row(mapping, economy_display="Singapore", candidate=_FakeCandidate())
    assert "quote appears to be a title" in row.notes
    # An operative provision is not flagged.
    row2 = build_row(_sample_mapping(), economy_display="Singapore", candidate=_FakeCandidate())
    assert "quote appears to be a title" not in row2.notes


def test_dedupe_drops_repeated_provisions():
    from submission.schema import dedupe_submission_rows

    def mk(quote, ind="P7-I1", law="Privacy Act 1988"):
        return SubmissionRow(economy="Australia", law_name=law,
                             indicator_id=ind, verbatim_snippet=quote,
                             source_url="https://legislation.gov.au/x")
    rows = [
        mk("The same clause."),
        mk("the  same   clause."),                 # whitespace/case dup -> dropped
        mk("A different clause."),                  # kept
        mk("The same clause.", ind="P7-I3"),        # different indicator -> kept
        mk("The same clause.", law="Other Act"),    # different law -> kept
    ]
    out = dedupe_submission_rows(rows)
    assert len(out) == 4  # only the whitespace/case duplicate is removed


def test_authoritative_law_name_overrides_llm_guess():
    from types import SimpleNamespace

    mapping = _sample_mapping().model_copy(update={
        "source_legislation": "South Korea Queensland Privacy Act (hallucinated)",
    })
    candidate = SimpleNamespace(
        title="Information Privacy Act 2009 (QLD)",
        authoritative_law_name="Information Privacy Act 2009 (QLD)",
        discovery_method="known_mapping", url="https://x", last_update="",
        confidence=1.0, warnings=[],
    )
    row = build_row(mapping, economy_display="Australia", candidate=candidate)
    assert row.law_name == "Information Privacy Act 2009 (QLD)"


def test_pdf_row_source_url_falls_back_to_file_path():
    # A provided-PDF run has no official URL; the file path is the provenance,
    # so the row must not be dropped for an empty source_url (OCR deliverable).
    row = build_row(
        _sample_mapping().model_copy(update={"source_url": ""}),
        economy_display="India", candidate=None,
        doc_meta={"source_pdf_path": "/tmp/scan.pdf", "quality": "unknown"},
    )
    assert row.source_url == "/tmp/scan.pdf"
    assert validate_submission_rows([row]) == [row]


def test_cap_rows_per_law_indicator_trims_over_extraction():
    from submission.schema import cap_rows_per_law_indicator

    def mk(quote, ind="P7-I1", law="QLD IP Act"):
        return SubmissionRow(economy="Australia", law_name=law, indicator_id=ind,
                             verbatim_snippet=quote, source_url="https://x")
    rows = [mk(f"provision number {i} " + "x" * i) for i in range(15)]  # 15 for one (law,ind)
    rows += [mk("other indicator provision", ind="P7-I3")]
    out = cap_rows_per_law_indicator(rows, cap=10)
    p7i1 = [r for r in out if r.indicator_id == "P7-I1"]
    assert len(p7i1) == 10                       # capped
    assert len([r for r in out if r.indicator_id == "P7-I3"]) == 1  # untouched
    # The longest (most substantive) quotes are the ones kept.
    assert all("x" * 5 in r.verbatim_snippet for r in p7i1)


def test_cap_rows_per_law_balances_a_dominant_statute_across_indicators():
    from submission.schema import cap_rows_per_law

    def mk(ind, n, law="Information Privacy Act 2009 (QLD)"):
        return SubmissionRow(economy="Australia", law_name=law, indicator_id=ind,
                             verbatim_snippet=f"{ind} provision text number {n} " + "y" * n,
                             source_url="https://legislation.qld.gov.au/x")
    # One statute floods four indicators (34 rows); a federal law has one each.
    rows = [mk("P7-I1", i) for i in range(12)]
    rows += [mk("P7-I3", i) for i in range(10)]
    rows += [mk("P7-I5", i) for i in range(8)]
    rows += [mk("P7-I2", i) for i in range(4)]
    rows += [
        SubmissionRow(economy="Australia", law_name="Privacy Act 1988", indicator_id="P7-I1",
                      verbatim_snippet="Privacy Act 1988", source_url="https://legislation.gov.au/x"),
    ]
    out = cap_rows_per_law(rows, cap=8)
    qld = [r for r in out if "QLD" in r.law_name]
    fed = [r for r in out if r.law_name == "Privacy Act 1988"]
    assert len(qld) == 8                         # dominant statute capped
    assert len(fed) == 1                          # small law untouched
    # The 8 kept QLD rows are spread across its indicators, not one indicator's tail.
    assert len({r.indicator_id for r in qld}) == 4


def test_foreign_jurisdiction_rows_dropped_for_run_economy():
    """A multi-jurisdiction digest can make the extractor emit e.g. China PIPL
    rows inside a Singapore run — the validator must drop them, while the same
    laws stay valid in their OWN economy's runs (Round 2)."""
    from submission.schema import SubmissionRow, validate_submission_rows

    def row(economy, law):
        return SubmissionRow(
            economy=economy, law_name=law, indicator_id="P6-I4",
            article="Art 38",
            verbatim_snippet=("Personal information handlers shall meet one of the "
                              "following conditions to provide data outside the borders."),
            source_url="https://official.example/x",
        )

    kept = validate_submission_rows(
        [
            row("Singapore", "China Personal Information Protection Law (PIPL)"),
            row("Singapore", "India Digital Personal Data Protection Bill, 2022"),
            row("Singapore", "Personal Data Protection Act 2012"),
        ],
        allow_empty=True,
    )
    assert [r.law_name for r in kept] == ["Personal Data Protection Act 2012"]

    # Same PIPL row in a CHINA run is legitimate and must survive.
    kept_chn = validate_submission_rows(
        [row("China", "Personal Information Protection Law of the People's Republic of China")],
        allow_empty=True,
    )
    assert len(kept_chn) == 1


def test_non_statute_instruments_dropped():
    """Bills, drafts, consultations and digests are not in-force statutory
    measures — never valid evidence rows."""
    from submission.schema import SubmissionRow, validate_submission_rows

    def row(law):
        return SubmissionRow(
            economy="Singapore", law_name=law, indicator_id="P6-I4",
            article="Cl 5",
            verbatim_snippet=("An organisation must not transfer personal data outside "
                              "Singapore except in accordance with prescribed requirements."),
            source_url="https://official.example/x",
        )

    kept = validate_submission_rows(
        [
            row("PERSONAL DATA PROTECTION DIGEST - Singapore Academy of Law"),
            row("Singapore Consultation Approaches to Managing Data Flows"),
            row("Personal Data Protection (Amendment) Bill"),
            row("Personal Data Protection Act 2012"),
        ],
        allow_empty=True,
    )
    assert [r.law_name for r in kept] == ["Personal Data Protection Act 2012"]


def test_p6_rows_without_data_language_are_flagged_not_dropped():
    """A P6 row quoting a licence/asset 'transfer' provision (no data language)
    is KEPT but loudly flagged for human review — the semantic call is the
    reviewer's, never silently decided either way."""
    from submission.schema import SubmissionRow, validate_submission_rows

    gas = SubmissionRow(
        economy="Singapore", law_name="Gas Act 2001", indicator_id="P6-I4",
        article="Section 43(5)",
        verbatim_snippet=("The transfer of the whole or any part of the undertaking "
                          "of a licensee requires the prior written approval of the Authority."),
        source_url="https://sso.agc.gov.sg/Act/GA2001",
    )
    pdpa = SubmissionRow(
        economy="Singapore", law_name="Personal Data Protection Act 2012", indicator_id="P6-I4",
        article="Section 26",
        verbatim_snippet=("An organisation must not transfer any personal data to a "
                          "country or territory outside Singapore except in accordance "
                          "with requirements prescribed under this Act."),
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
    )
    kept = validate_submission_rows([gas, pdpa], allow_empty=True)
    assert len(kept) == 2, "flag, never drop"
    assert "topic check" in kept[0].notes and "needs human review" in kept[0].notes
    assert kept[0].requires_human_review is True
    assert "topic check" not in (kept[1].notes or "")
    assert kept[1].requires_human_review is False


def test_names_without_statute_words_are_dropped():
    """'Executive Summary' / 'MOU with ...' are documents, not legislation."""
    from submission.schema import SubmissionRow, validate_submission_rows

    def row(law):
        return SubmissionRow(
            economy="Australia", law_name=law, indicator_id="P7-I5",
            article="Part 2",
            verbatim_snippet=("An agency may disclose personal information where the "
                              "disclosure is required or authorised by or under law."),
            source_url="https://official.example/x",
        )

    kept = validate_submission_rows(
        [row("Executive Summary"),
         row("MOU with the Data Protection Commissioner"),
         row("Privacy Act 1988"),
         row("Royal Decree Exempting Data Controllers B.E. 2563")],
        allow_empty=True,
    )
    assert [r.law_name for r in kept] == [
        "Privacy Act 1988",
        "Royal Decree Exempting Data Controllers B.E. 2563",
    ]
    # (Bonus check that surfaced while writing this test: a "Singapore TRM
    # Notices" row inside an AUSTRALIA run is dropped too — by the
    # foreign-jurisdiction gate, exactly as designed.)


def test_drop_zero_confidence_rows_removes_unscoreable_noise():
    """Final-assembly guard: rows the extractor scored 0.00 confidence are noise.

    Live discovery surfaces marginal instruments (guidance notes, circular
    definitions, contract clauses) that the extractor honestly scores 0.00.
    They are dropped at assembly. This runs OUTSIDE validate_submission_rows, so
    it does not depend on the fixture-confidence convention used elsewhere.
    """
    from submission.schema import SubmissionRow, drop_zero_confidence_rows

    def row(law, conf):
        return SubmissionRow(
            economy="Australia", law_name=law, indicator_id="P7-I3",
            article="s 17", verbatim_snippet="The record must be retained for seven years.",
            mapping_rationale="[s 17] Retention duty maps to 7.3.",
            source_url="https://official.example/x", confidence=conf,
        )

    kept = drop_zero_confidence_rows([
        row("My Health Records Act 2012", 0.6),
        row("Pasture Seeds Levy Agreement clause", 0.0),
        row("Privacy Act 1988", 0.4),
    ])
    assert [r.law_name for r in kept] == [
        "My Health Records Act 2012",
        "Privacy Act 1988",
    ]


def test_formal_submission_filter_excludes_review_and_low_confidence_rows(monkeypatch):
    from submission.schema import filter_formal_submission_rows

    def row(law, confidence, *, review=False, decision="supported"):
        return SubmissionRow(
            economy="Australia", law_name=law, indicator_id="P7-I3",
            article="s 17", verbatim_snippet="Records must be retained for seven years.",
            source_url="https://official.example/x", confidence=confidence,
            requires_human_review=review, mapping_decision=decision,
        )

    accepted = row("Accepted Act 2024", 0.8)
    review = row("Review Act 2024", 0.8, review=True)
    weak = row("Weak Act 2024", 0.5)
    contradicted = row("Wrong Act 2024", 0.9, decision="contradicted")

    monkeypatch.setenv("RDTII_ELIGIBILITY_MODE", "reject")
    assert filter_formal_submission_rows([accepted, review, weak, contradicted]) == [accepted]
    assert filter_formal_submission_rows(
        [accepted, review, weak, contradicted], include_review=True
    ) == [accepted, review, weak, contradicted]


def test_formal_submission_filter_flag_mode_keeps_flagged_rows(monkeypatch):
    """Flag-not-drop default: flagged rows stay in the formal output, annotated
    for human validation, instead of being excluded at the output boundary."""
    from submission.schema import filter_formal_submission_rows

    def row(law, confidence, *, review=False, decision="supported"):
        return SubmissionRow(
            economy="Australia", law_name=law, indicator_id="P7-I3",
            article="s 17", verbatim_snippet="Records must be retained for seven years.",
            source_url="https://official.example/x", confidence=confidence,
            requires_human_review=review, mapping_decision=decision,
        )

    accepted = row("Accepted Act 2024", 0.8)
    review = row("Review Act 2024", 0.8, review=True)
    weak = row("Weak Act 2024", 0.5)
    contradicted = row("Wrong Act 2024", 0.9, decision="contradicted")
    rows = [accepted, review, weak, contradicted]

    # Unset → flag mode is the default.
    monkeypatch.delenv("RDTII_ELIGIBILITY_MODE", raising=False)
    assert filter_formal_submission_rows(rows) == rows
    monkeypatch.setenv("RDTII_ELIGIBILITY_MODE", "flag")
    assert filter_formal_submission_rows(rows) == rows
def test_mapping_gate_drops_offtopic_and_confabulated_maps():
    """Mapping-layer gate: real quote, wrong indicator/label must be dropped.

    Covers the live-discovery mis-maps found in the 2026-07-18 verification:
    export-control-of-goods laws on P6, payment laws on data-localization with no
    locality language, draft-bill quotes, and rationales whose subject statute
    differs from the row's law name. Legitimate rows (incl. a genuine
    cross-reference to another Act) survive.
    """
    from submission.schema import validate_submission_rows, SubmissionRow

    def row(law, ind, quote, rat, url="https://sso.agc.gov.sg/Act/x"):
        return SubmissionRow(
            economy="Singapore", law_name=law, indicator_id=ind, article="s 1",
            verbatim_snippet=quote, mapping_rationale=rat, source_url=url,
            last_amended="2020", confidence=0.9,
        )

    keeper = row(
        "Personal Data Protection Act 2012", "P7-I3",
        "An organisation must cease to retain personal data as soon as it is reasonable to assume the purpose has ceased.",
        "[s 25] Section 25 of the Personal Data Protection Act 2012 imposes a retention-limitation duty.",
    )
    xref_keeper = row(
        "My Health Records Act 2012", "P7-I1",
        "An authorisation to collect health information under this Act is also an authorisation for the purposes of the Privacy Act 1988.",
        "[Section 5] Section 5 of the My Health Records Act 2012 operates as a sectoral data protection measure linking to the Privacy Act 1988.",
        url="https://legislation.gov.au/x",
    )
    strategic = row(
        "Strategic Goods (Control) Act 2002", "P6-I2",
        '"goods" means any movable or personal property but does not include choses in action or money.',
        "[Section 2(1)] The definition of goods maps to local storage.",
    )
    payment = row(
        "Payment Services Act 2019", "P6-I1",
        "Restrictions on personal payment account that contains e-money.",
        "[Section 24] Section 24 of the Monetary Authority of Singapore Act imposes restrictions on personal payment accounts.",
    )
    draft = row(
        "Personal Data Protection Act 2012", "P7-I2",
        "Under Sections 10 and 15 of the Draft Bill, CIIOs must notify the Commissioner of any significant cybersecurity incident.",
        "[Sections 10 and 15] Draft cybersecurity notification obligations.",
    )
    confab = row(
        "Identity Verification Services Act 2023", "P7-I1",
        "General privacy obligations of parties to participation agreement apply to each party.",
        "[Section 9] Section 9 of Australia's Privacy Act 1988 imposes general privacy obligations.",
        url="https://legislation.gov.au/x",
    )
    kept = validate_submission_rows(
        [keeper, xref_keeper, strategic, payment, draft, confab], allow_empty=True
    )
    names = [r.law_name for r in kept]
    assert "Personal Data Protection Act 2012" in names       # retention keeper
    assert "My Health Records Act 2012" in names              # legit cross-reference kept
    assert "Strategic Goods (Control) Act 2002" not in names  # export-control dropped
    assert "Payment Services Act 2019" not in names           # payment off-localization dropped
    assert not any(r.indicator_id == "P7-I2" for r in kept)   # draft-bill dropped
    assert not any(r.indicator_id == "P7-I1" and "Identity" in r.law_name for r in kept)  # confab dropped


def test_flag_7_3_rows_without_minimum_retention_period():
    """7.3 rows without a specific minimum period are flagged (never dropped)."""
    from submission.schema import validate_submission_rows, SubmissionRow, _P7_I3_NO_PERIOD_FLAG

    def row(quote):
        return SubmissionRow(
            economy="Singapore", law_name="Personal Data Protection Act 2012",
            indicator_id="P7-I3", article="s 25", verbatim_snippet=quote,
            mapping_rationale="[s 25] retention rule.",
            source_url="https://sso.agc.gov.sg/x", last_amended="2020", confidence=0.9,
        )
    with_period = row("The company shall retain the records for a period of seven years from the end of the year.")
    no_period = row("An organisation must cease to retain personal data as soon as retention is no longer necessary.")
    kept = validate_submission_rows([with_period, no_period], allow_empty=True)
    assert len(kept) == 2  # flag, never drop
    flagged = {("period" if "seven years" in r.verbatim_snippet else "no-period"):
               (_P7_I3_NO_PERIOD_FLAG in (r.notes or "")) for r in kept}
    assert flagged["period"] is False    # has "seven years"
    assert flagged["no-period"] is True  # no minimum period -> flagged


def test_flag_p6_localization_rows_without_restriction():
    """6.1/6.2/6.3 rows with no localization/restriction language are flagged."""
    from submission.schema import validate_submission_rows, SubmissionRow, _P6_LOC_NO_RESTRICTION_FLAG

    def row(quote):
        return SubmissionRow(
            economy="Singapore", law_name="Financial Services and Markets Act 2022",
            indicator_id="P6-I1", article="s 28E", verbatim_snippet=quote,
            mapping_rationale="[s 28E] disclosure provision.",
            source_url="https://sso.agc.gov.sg/x", last_amended="2022", confidence=0.9,
        )
    restrictive = row("A data user shall not transfer personal data to a place outside Singapore.")
    permissive = row("A prescribed financial institution may on its own motion disclose risk information to another institution.")
    kept = validate_submission_rows([restrictive, permissive], allow_empty=True)
    assert len(kept) == 2  # flag, never drop
    flags = {("permissive" if "may on its own motion" in r.verbatim_snippet else "restrictive"):
             (_P6_LOC_NO_RESTRICTION_FLAG in (r.notes or "")) for r in kept}
    assert flags["restrictive"] is False   # "shall not transfer … outside"
    assert flags["permissive"] is True     # permissive disclosure -> flagged


def test_drops_citation_plus_heading_verbatim():
    """A '<Law> — Section N (Heading)' citation is a heading, dropped even when
    the heading text contains an operative word like 'access'."""
    from submission.schema import validate_submission_rows, SubmissionRow

    def row(quote, ind="P7-I1"):
        return SubmissionRow(
            economy="Singapore", law_name="Criminal Procedure Code 2010",
            indicator_id=ind, article="Section 39", verbatim_snippet=quote,
            mapping_rationale="[s 39] x.", source_url="https://sso.agc.gov.sg/Act/CPC2010",
            last_amended="2010", confidence=0.9,
        )
    heading = row("Criminal Procedure Code 2010 — Section 39 (Power to access computer)")
    provision = row(
        "a police officer investigating an arrestable offence may at any time access and inspect the operation of a computer in Singapore.",
        ind="P7-I5",
    )
    kept = validate_submission_rows([heading, provision], allow_empty=True)
    names_inds = {(r.law_name, r.indicator_id) for r in kept}
    assert ("Criminal Procedure Code 2010", "P7-I1") not in names_inds  # heading dropped
    assert ("Criminal Procedure Code 2010", "P7-I5") in names_inds       # real provision kept


def test_document_self_title_corrects_mislabeled_live_rows():
    """Live rows quoting the IVS Act were shipped as 'Privacy Act 1988' (the
    act a provision talks ABOUT), and levy Collection Agreements as privacy
    instruments — the document's own opening title is the ground truth."""
    from types import SimpleNamespace

    from schemas import IndicatorMapping
    from submission.pipeline import (
        _document_self_title,
        _names_disagree,
        build_row,
    )

    ivs_head = (
        "Identity Verification Services Act 2023 No. 115, 2023 Compilation "
        "No. 1 Compilation date: 11 December 2024"
    )
    pasture_head = (
        "Pasture Seeds Levy Collection Agreement – Western Australia – 2026 "
        "Department of Agriculture, Fisheries and Forestry"
    )
    assert _document_self_title(ivs_head) == "Identity Verification Services Act 2023"
    assert "Pasture Seeds Levy Collection Agreement" in _document_self_title(pasture_head)

    assert _names_disagree("Australia Privacy Act, 1988", "Identity Verification Services Act 2023")
    # Same-instrument phrasings must NOT be renamed.
    assert not _names_disagree("Privacy Act 1988", "Privacy Act 1988")
    assert not _names_disagree(
        "Information Privacy Act 2009 (QLD)", "Queensland Information Privacy Act 2009"
    )
    # Years disjoint → different instruments even with word overlap.
    assert _names_disagree(
        "Australia Privacy Act, 1988",
        "Privacy Amendment (Public Health Contact Information) Act 2020",
    )

    mapping = IndicatorMapping(
        pillar=7, indicator="7.3", score=1.0,
        verbatim_quote="The record must be retained for seven years.",
        quote_start=60, quote_end=100,
        source_legislation="Australia Privacy Act, 1988",
        impact="[s 10] Retention duty maps to 7.3.",
        source_url="https://www.legislation.gov.au/C2023A00115/latest/text",
    )
    candidate = SimpleNamespace(
        title="Privacy Act 1988", url=mapping.source_url,
        authoritative_law_name="", last_update="", discovery_method="live_search",
        retrieval_mode="live", confidence=0.9, legal_review_approved=False,
    )
    row = build_row(
        mapping, economy_display="Australia", candidate=candidate,
        source_text=ivs_head + " The record must be retained for seven years.",
    )
    assert row.law_name == "Identity Verification Services Act 2023"
    assert "law name corrected" in row.notes
