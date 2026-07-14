from pathlib import Path

from evaluation.coverage import CORE_INDICATORS, audit_coverage
from evaluation.models import GoldenCase, GoldenDocument
from evaluation.runner import load_jsonl


REPO_ROOT = Path(__file__).resolve().parents[2]


def _dataset():
    cases = load_jsonl(REPO_ROOT / "evaluation/golden/cases.jsonl", GoldenCase)
    documents = load_jsonl(
        REPO_ROOT / "evaluation/golden/documents.jsonl", GoldenDocument
    )
    return cases, documents


def test_candidate_set_meets_structural_coverage_contract():
    audit = audit_coverage(*_dataset())

    assert audit.structurally_complete, audit.issues
    assert set(audit.positive_by_indicator) == CORE_INDICATORS
    assert all(audit.positive_by_indicator.values())
    assert all(audit.negative_by_indicator.values())
    assert all(pillars == ["6", "7"] for pillars in audit.country_pillars.values())


def test_pending_expansion_does_not_overstate_approved_coverage():
    audit = audit_coverage(*_dataset(), approved_only=True)

    assert not audit.structurally_complete
    assert audit.case_count == 8
    assert any("below minimum" in issue for issue in audit.issues)
