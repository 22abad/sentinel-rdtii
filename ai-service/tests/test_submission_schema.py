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
    assert row.confidence == pytest.approx(0.91)
    assert row.amendment_version_date == "Amended 2020"
    assert "requires human review" in row.notes
    assert "bilingual source" in row.notes
    # Context windows populated for the JSON audit view.
    assert row.raw_context_before or row.raw_context_after
    assert row.confidence_type == "discovery_confidence"


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
        confidence_type="discovery_confidence",
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
        assert header == list(CSV_COLUMNS)
        first = next(reader)
        assert first[header.index("indicator_id")] == "P6-I4"
        assert first[header.index("confidence")] == "0.91"

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
