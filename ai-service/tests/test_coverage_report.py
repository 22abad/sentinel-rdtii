"""TDD (red-first) for the official-cell coverage computation.

Seam under test: `coverage.official_cell_coverage(submission_rows, inventory_rows)`
— a pure function (no files, no network) that reports how many official
non-zero (economy, indicator) cells the submission provides evidence for.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _inv(economy, indicator, score):
    return {"economy": economy, "indicator_id": indicator, "official_score": score}


def _row(economy, indicator_id):
    # submission rows use the CSV 'Indicator ID' shape "P6-I1"
    return {"Economy": economy, "Indicator ID": indicator_id}


def test_counts_only_official_nonzero_cells_with_evidence():
    from coverage_report import official_cell_coverage

    inventory = [
        _inv("IDN", "6.1", 1.0),   # non-zero, covered below
        _inv("IDN", "6.4", 0.5),   # non-zero, NOT covered
        _inv("IDN", "7.1", 0.0),   # zero cell — never counted
    ]
    submission = [
        _row("Indonesia", "P6-I1"),   # covers IDN 6.1
        _row("Indonesia", "P7-I1"),   # a zero cell — must not count
    ]
    r = official_cell_coverage(submission, inventory)
    assert r["total_nonzero_cells"] == 2       # 6.1 and 6.4 (7.1 is zero)
    assert r["covered_cells"] == 1             # only 6.1
    assert r["coverage_rate"] == 0.5


def test_per_economy_breakdown():
    from coverage_report import official_cell_coverage

    inventory = [_inv("IDN", "6.1", 1.0), _inv("CHN", "7.2", 1.0)]
    submission = [_row("Indonesia", "P6-I1")]  # IDN covered, CHN not
    r = official_cell_coverage(submission, inventory)
    assert r["by_economy"]["IDN"] == {"covered": 1, "total": 1}
    assert r["by_economy"]["CHN"] == {"covered": 0, "total": 1}


def test_per_pillar_breakdown():
    """Which pillars are weak — coverage grouped by pillar number across all economies."""
    from coverage_report import official_cell_coverage

    inventory = [
        _inv("IDN", "6.1", 1.0), _inv("IDN", "6.4", 1.0),   # pillar 6: 2 cells
        _inv("CHN", "7.2", 1.0),                            # pillar 7: 1 cell
    ]
    submission = [_row("Indonesia", "P6-I1")]  # covers 6.1 only
    r = official_cell_coverage(submission, inventory)
    assert r["by_pillar"]["6"] == {"covered": 1, "total": 2}
    assert r["by_pillar"]["7"] == {"covered": 0, "total": 1}


def test_lists_uncovered_cells_for_targeting():
    """The report names the exact (economy, indicator) non-zero cells with no
    evidence — the actionable worklist for corpus/extraction follow-up."""
    from coverage_report import official_cell_coverage

    inventory = [_inv("IDN", "6.1", 1.0), _inv("IDN", "6.4", 0.5), _inv("CHN", "7.2", 1.0)]
    submission = [_row("Indonesia", "P6-I1")]  # covers IDN 6.1 only
    r = official_cell_coverage(submission, inventory)
    assert set(r["uncovered_cells"]) == {("IDN", "6.4"), ("CHN", "7.2")}


def test_coverage_delta_between_two_reports():
    """Quantify a coverage change (e.g. after a corpus re-fetch): total delta and
    which pillars moved."""
    from coverage_report import coverage_delta

    old = {"covered_cells": 132, "total_nonzero_cells": 229,
           "by_pillar": {"5": {"covered": 8, "total": 26}, "6": {"covered": 19, "total": 20}}}
    new = {"covered_cells": 140, "total_nonzero_cells": 229,
           "by_pillar": {"5": {"covered": 14, "total": 26}, "6": {"covered": 19, "total": 20}}}
    d = coverage_delta(old, new)
    assert d["covered_delta"] == 8
    assert d["rate_before"] == round(132 / 229, 3)
    assert d["rate_after"] == round(140 / 229, 3)
    assert d["pillar_gains"]["5"] == 6      # +6 on pillar 5
    assert "6" not in d["pillar_gains"]      # unchanged pillars omitted


def test_classify_gap_root_cause():
    """Each uncovered cell's root cause drives WHERE to fix it: a real statute
    present = extraction miss; only summary/stub = corpus-quality; no text at
    all = fetch gap."""
    from coverage_report import classify_gap

    assert classify_gap(has_local_text=True, is_statute=True) == "EXTRACTION"
    assert classify_gap(has_local_text=True, is_statute=False) == "CORPUS_QUALITY"
    assert classify_gap(has_local_text=False, is_statute=False) == "FETCH_GAP"


def test_summarize_gaps_three_way_split():
    """Aggregate uncovered cells (each tagged has_text/is_statute) into the
    reproducible 3-way recall-gap split + a per-pillar tally."""
    from coverage_report import summarize_gaps

    cells = [
        {"economy": "RUS", "indicator": "7.2", "has_text": True, "is_statute": True},   # EXTRACTION
        {"economy": "IDN", "indicator": "6.4", "has_text": True, "is_statute": False},  # CORPUS_QUALITY
        {"economy": "IDN", "indicator": "8.1", "has_text": True, "is_statute": False},  # CORPUS_QUALITY
        {"economy": "MNG", "indicator": "7.3", "has_text": False, "is_statute": False}, # FETCH_GAP
    ]
    s = summarize_gaps(cells)
    assert s["by_cause"] == {"EXTRACTION": 1, "CORPUS_QUALITY": 2, "FETCH_GAP": 1}
    assert s["by_pillar"]["7"] == {"EXTRACTION": 1, "FETCH_GAP": 1}


def test_gap_worklist_is_actionable_and_cause_ordered():
    """Turn tagged uncovered cells into an actionable worklist: one row per cell
    with its root cause, ordered so the tractable fixes (fetch, then corpus)
    lead and the hard extraction-recall ones trail."""
    from coverage_report import gap_worklist

    cells = [
        {"economy": "RUS", "indicator": "7.2", "has_text": True, "is_statute": True},   # EXTRACTION
        {"economy": "MNG", "indicator": "7.3", "has_text": False, "is_statute": False}, # FETCH_GAP
        {"economy": "IDN", "indicator": "6.4", "has_text": True, "is_statute": False},  # CORPUS_QUALITY
    ]
    wl = gap_worklist(cells)
    assert [r["cause"] for r in wl] == ["FETCH_GAP", "CORPUS_QUALITY", "EXTRACTION"]
    assert wl[0]["economy"] == "MNG" and wl[0]["indicator"] == "7.3"
    assert all({"economy", "indicator", "cause"} <= set(r) for r in wl)


def test_submission_stats_shape():
    """Submission shape for the meeting report / pitch: total rows, distinct
    laws & indicators, NEW/KNOWN split, per-pillar row counts."""
    from coverage_report import submission_stats

    rows = [
        {"Economy": "Indonesia", "Indicator ID": "P6-I1", "Law Name": "PDP Law", "Discovery Tag": "KNOWN"},
        {"Economy": "Indonesia", "Indicator ID": "P6-I4", "Law Name": "PDP Law", "Discovery Tag": "KNOWN"},
        {"Economy": "Indonesia", "Indicator ID": "P7-I2", "Law Name": "BSSN Reg", "Discovery Tag": "NEW"},
    ]
    s = submission_stats(rows)
    assert s["total_rows"] == 3
    assert s["distinct_laws"] == 2
    assert s["distinct_indicators"] == 3
    assert s["by_tag"] == {"KNOWN": 2, "NEW": 1}
    assert s["by_pillar"] == {"6": 2, "7": 1}


def test_aggregate_cell_status_uses_any_statute_across_entries():
    """A cell whose manifest has BOTH a summary and a real statute (e.g. THA
    12.7: .TH policy SUMMARY + Telecommunications Act STATUTE) must be tagged
    has_statute — the old law_name-exact join wrongly picked the summary."""
    from coverage_report import aggregate_cell_status

    kinds_by_cell = {
        ("THA", "12.7"): ["SUMMARY", "STATUTE"],
        ("THA", "5.3"): ["SUMMARY"],
        ("IDN", "7.1"): ["SUMMARY", "SUMMARY"],
    }
    status = aggregate_cell_status(kinds_by_cell)

    assert status[("THA", "12.7")] == (True, True)   # statute present → not a corpus-quality gap
    assert status[("THA", "5.3")] == (True, False)   # summary only
    assert status[("IDN", "7.1")] == (True, False)   # summaries only
    assert status.get(("CHN", "1.4"), (False, False)) == (False, False)  # no entries


def test_aggregate_cell_status_empty_input():
    from coverage_report import aggregate_cell_status

    assert aggregate_cell_status({}) == {}
