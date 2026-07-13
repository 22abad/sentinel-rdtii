from __future__ import annotations

from submission.novelty import (
    build_discovery_report,
    is_known_law,
    known_law_index,
    load_known_inventory,
    normalize_law_name,
    reconcile_discovery_tags,
    summarize_discovery,
)
from submission.schema import SubmissionRow


def test_official_inventory_loads_and_covers_three_economies():
    inv = load_known_inventory()
    assert len(inv) > 150  # ~195 distinct KNOWN laws
    economies = {econ for econ, _ in inv}
    assert economies == {"AUS", "MYS", "SGP"}
    # A representative KNOWN law from the official ESCAP inventory.
    assert ("MYS", normalize_law_name("Personal Data Protection Act 2010")) in inv


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
    # Laws only in the official ESCAP Legal Inventory are also KNOWN.
    assert is_known_law("Singapore", "Cybersecurity Act 2018", index)
    assert is_known_law("Australia", "Security of Critical Infrastructure Act 2018", index)
    # A law in neither the library nor the official inventory is not KNOWN.
    assert not is_known_law("Singapore", "Zzz Data Localisation Act 2099", index)
    # Right law, wrong economy -> not KNOWN.
    assert not is_known_law("Australia", "Companies Act 2016 (Act 777)", index)


def test_reconcile_flips_tags_from_the_baseline():
    rows = [
        _row("Malaysia", "Companies Act 2016 (Act 777)", "P7-I3", tag="NEW"),  # actually KNOWN
        _row("Singapore", "Zzz Data Localisation Act 2099", "P6-I5", tag="KNOWN"),  # actually NEW
    ]
    reconciled = reconcile_discovery_tags(rows)
    by_law = {r.law_name: r.discovery_tag for r in reconciled}
    assert by_law["Companies Act 2016 (Act 777)"] == "KNOWN"
    assert by_law["Zzz Data Localisation Act 2099"] == "NEW"
    # Reconciliation is immutable — inputs untouched.
    assert rows[0].discovery_tag == "NEW"


def test_reconcile_never_labels_fixture_sources_new():
    fixture = _row(
        "Singapore",
        "Unseen Fixture Act 2099",
        tag="NEW",
    ).model_copy(update={"retrieval_method": "fixture"})
    fallback = fixture.model_copy(
        update={"law_name": "Unseen Fallback Act 2099", "retrieval_method": "fallback"}
    )

    reconciled = reconcile_discovery_tags([fixture, fallback])

    assert [row.discovery_tag for row in reconciled] == ["KNOWN", "KNOWN"]


def test_report_lists_new_candidates_with_audit_and_gate():
    rows = [
        _row("Singapore", "Personal Data Protection Act 2012", "P6-I4", tag="NEW"),  # KNOWN baseline
        _row(
            "Singapore",
            "Zzz Data Localisation Act 2099",
            "P6-I5",
            tag="NEW",
            source_url="https://sso.agc.gov.sg/Act/ZZZ2099",
            verbatim_snippet="data must be stored locally…",
        ),
    ]
    report = build_discovery_report("Singapore", rows)
    summary = report["summary"]
    assert summary["total_provisions"] == 2
    assert summary["new_provisions"] == 1
    assert summary["known_provisions"] == 1
    assert summary["new_laws"] == [
        {"economy": "Singapore", "law_name": "Zzz Data Localisation Act 2099", "indicators": ["P6-I5"]}
    ]
    # NEW candidate carries the audit trail for the human gate.
    assert report["new_candidates"][0]["source_url"] == "https://sso.agc.gov.sg/Act/ZZZ2099"
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
