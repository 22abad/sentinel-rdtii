"""Offline tests for the judge-validated submission contract."""

from __future__ import annotations

import csv
import json

import pytest

from schemas import IndicatorMapping
from submission.pipeline import build_row
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
    with pytest.raises(ValueError, match="No verified provisions"):
        validate_submission_rows([])


def test_submission_validator_allows_explicit_research_empty_results():
    validate_submission_rows([], allow_empty=True)


def test_submission_validator_requires_judge_critical_fields():
    assert REQUIRED_SUBMISSION_FIELDS == (
        "law_name", "indicator_id", "article", "verbatim_snippet", "source_url",
    )
    row = SubmissionRow(
        economy="Singapore",
        law_name="Test Act 2026",
        indicator_id="P6-I1",
        article=" ",
        verbatim_snippet="Exact provision.",
        source_url="",
    )

    with pytest.raises(ValueError, match=r"row 1: article, source_url"):
        validate_submission_rows([row], allow_empty=True)


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
    assert row.source_url.endswith("PDPA2012")
    assert row.confidence == pytest.approx(0.91)
    assert "requires human review" in row.notes
    assert "bilingual source" in row.notes
    # Context windows populated for the JSON audit view.
    assert row.raw_context_before or row.raw_context_after


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
