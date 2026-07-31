"""TDD for the Round-2 merged-submission tool (official header + dedup)."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "tools", _REPO / "ai-service"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from merge_submission import dotted, dedup, out_row  # noqa: E402
from submission.schema import CSV_HEADERS  # noqa: E402


def test_dotted_converts_and_keeps_tails():
    assert dotted("P6-I1") == "6.1"
    assert dotted("P12-I4.1") == "12.4.1"
    assert dotted("7.3") == "7.3"
    assert dotted("") == ""


def test_dedup_keeps_highest_confidence():
    rows = [
        {"Economy": "China", "Indicator ID": "P6-I1", "Law Name": "PIPL", "Verbatim Snippet": "abc", "Confidence": "0.5"},
        {"Economy": "China", "Indicator ID": "6.1", "Law Name": "PIPL", "Verbatim Snippet": "abc", "Confidence": "0.8"},
        {"Economy": "India", "Indicator ID": "7.3", "Law Name": "DPDP", "Verbatim Snippet": "xyz", "Confidence": "0.9"},
    ]
    out = dedup(rows)
    assert len(out) == 2  # first two dedup to one
    china = [r for r in out if _col(r, "Economy") == "China"][0]
    assert _col(china, "Confidence") == "0.8"


def test_out_row_uses_official_headers():
    r = {"Economy": "China", "Law Name": "X", "Law Number / Ref": "N1",
         "Last Amended": "2020", "Indicator ID": "P6-I1", "Article / Section": "s2",
         "Discovery Tag": "KNOWN", "Location Reference": "L", "Verbatim Snippet": "V",
         "Mapping Rationale": "R", "Source URL": "U", "Confidence": "0.7", "Notes": ""}
    row = out_row(r)
    assert list(row.keys()) == list(CSV_HEADERS)
    assert row["Indicator ID"] == "6.1"


def test_out_row_maps_snake_case_sources():
    r = {"economy": "China", "law_name": "X", "indicator_id": "6.1", "verbatim_snippet": "V",
         "source_url": "U", "confidence": "0.6"}
    row = out_row(r)
    assert row["Economy"] == "China"
    assert row["Verbatim Snippet"] == "V"
    assert row["Source URL"] == "U"


def _col(r, n):
    return (r.get(n) or "").strip()


def test_header_matches_official_template():
    """The merged file's header must be exactly the 13 official columns."""
    assert list(CSV_HEADERS) == [
        "Economy", "Law Name", "Law Number / Ref", "Last Amended", "Indicator ID",
        "Article / Section", "Discovery Tag", "Location Reference", "Verbatim Snippet",
        "Mapping Rationale", "Source URL", "Confidence", "Notes",
    ]
