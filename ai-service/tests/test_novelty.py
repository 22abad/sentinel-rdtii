from __future__ import annotations

from submission.novelty import (
    build_discovery_report,
    is_known_law,
    known_law_index,
    normalize_law_name,
    reconcile_discovery_tags,
    summarize_discovery,
)
from submission.schema import SubmissionRow


def _row(economy, law_name, indicator_id="P6-I1", tag="NEW", **kw):
    return SubmissionRow(
        economy=economy,
        law_name=law_name,
        indicator_id=indicator_id,
        verbatim_snippet=kw.get("verbatim_snippet", "…"),
        discovery_tag=tag,
        source_url=kw.get("source_url", "https://example.gov/x"),
        article=kw.get("article", ""),
    )


def test_normalize_drops_year_number_and_punctuation():
    assert normalize_law_name("Companies Act 2016 (Act 777)") == "companies act"
    assert normalize_law_name("Personal Data Protection Act 2012") == "personal data protection act"
    assert normalize_law_name("My Health Records Act 2012") == "my health records act"


def test_known_index_matches_baseline_and_rejects_unseen():
    index = known_law_index()
    # Laws in the KNOWN baseline (library), across title variants.
    assert is_known_law("Malaysia", "Companies Act 2016 (Act 777)", index)
    assert is_known_law("SGP", "Personal Data Protection Act 2012", index)
    assert is_known_law("Australia", "Privacy Act 1988", index)
    # A law we have not cached is not KNOWN.
    assert not is_known_law("Singapore", "Electronic Transactions Act 2010", index)
    # Right law, wrong economy -> not KNOWN.
    assert not is_known_law("Australia", "Companies Act 2016 (Act 777)", index)


def test_reconcile_flips_tags_from_the_baseline():
    rows = [
        _row("Malaysia", "Companies Act 2016 (Act 777)", "P7-I3", tag="NEW"),  # actually KNOWN
        _row("Singapore", "Electronic Transactions Act 2010", "P6-I5", tag="KNOWN"),  # actually NEW
    ]
    reconciled = reconcile_discovery_tags(rows)
    by_law = {r.law_name: r.discovery_tag for r in reconciled}
    assert by_law["Companies Act 2016 (Act 777)"] == "KNOWN"
    assert by_law["Electronic Transactions Act 2010"] == "NEW"
    # Reconciliation is immutable — inputs untouched.
    assert rows[0].discovery_tag == "NEW"


def test_report_lists_new_candidates_with_audit_and_gate():
    rows = [
        _row("Singapore", "Personal Data Protection Act 2012", "P6-I4", tag="NEW"),  # KNOWN baseline
        _row(
            "Singapore",
            "Electronic Transactions Act 2010",
            "P6-I5",
            tag="NEW",
            source_url="https://sso.agc.gov.sg/Act/ETA2010",
            verbatim_snippet="electronic records may be transferred…",
        ),
    ]
    report = build_discovery_report("Singapore", rows)
    summary = report["summary"]
    assert summary["total_provisions"] == 2
    assert summary["new_provisions"] == 1
    assert summary["known_provisions"] == 1
    assert summary["new_laws"] == [
        {"economy": "Singapore", "law_name": "Electronic Transactions Act 2010", "indicators": ["P6-I5"]}
    ]
    # NEW candidate carries the audit trail for the human gate.
    assert report["new_candidates"][0]["source_url"] == "https://sso.agc.gov.sg/Act/ETA2010"
    assert "draft lead for legal review" in report["review_gate"]


def test_summary_groups_indicators_per_law():
    rows = [
        _row("Australia", "My Health Records Act 2012", "P6-I1", tag="KNOWN"),
        _row("Australia", "My Health Records Act 2012", "P6-I2", tag="KNOWN"),
    ]
    summary = summarize_discovery(reconcile_discovery_tags(rows))
    assert summary["known_laws"] == [
        {
            "economy": "Australia",
            "law_name": "My Health Records Act 2012",
            "indicators": ["P6-I1", "P6-I2"],
        }
    ]
