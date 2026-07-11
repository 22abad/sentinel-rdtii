"""Offline tests for the judge-validated submission contract."""

from __future__ import annotations

import csv
import json

import pytest

from schemas import IndicatorMapping
from submission.pipeline import build_row
from submission.schema import (
    CSV_COLUMNS,
    SubmissionRow,
    discovery_tag_for_method,
    economy_code,
    economy_display_name,
    extract_law_number_ref,
    extract_year,
    indicator_to_rdtii_code,
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


@pytest.mark.parametrize(
    ("internal", "expected"),
    [("6.1", "P6-I1"), ("7.3", "P7-I3"), ("6.5", "P6-I5"), ("P6-I1", "P6-I1")],
)
def test_indicator_code_conversion(internal, expected):
    assert indicator_to_rdtii_code(internal) == expected


def test_indicator_code_rejects_garbage():
    with pytest.raises(ValueError):
        indicator_to_rdtii_code("banana")


@pytest.mark.parametrize(
    ("method", "tag"),
    [("known_mapping", "KNOWN"), ("official_search", "NEW"), ("web_search", "NEW"), ("", "NEW")],
)
def test_discovery_tag(method, tag):
    assert discovery_tag_for_method(method) == tag


def test_economy_resolution():
    assert economy_code("Singapore") == "SGP"
    assert economy_code("sgp") == "SGP"
    assert economy_display_name("MYS") == "Malaysia"
    with pytest.raises(ValueError):
        economy_code("Atlantis")


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
