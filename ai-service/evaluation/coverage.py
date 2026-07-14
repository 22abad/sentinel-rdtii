"""Structural coverage checks for the Pillar 6/7 Golden Set."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import GoldenCase, GoldenDocument


CORE_INDICATORS = frozenset(
    {"6.1", "6.2", "6.3", "6.4", "6.5", "7.1", "7.2", "7.3", "7.4", "7.5"}
)
TARGET_COUNTRIES = frozenset({"AUS", "MYS", "SGP"})
MIN_CASES = 25
MAX_CASES = 40


@dataclass(frozen=True)
class CoverageAudit:
    case_count: int
    document_count: int
    positive_by_indicator: dict[str, int]
    negative_by_indicator: dict[str, int]
    country_pillars: dict[str, list[str]]
    pending_case_ids: list[str]
    pending_document_ids: list[str]
    issues: list[str]

    @property
    def structurally_complete(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict:
        return {
            "structurally_complete": self.structurally_complete,
            "case_count": self.case_count,
            "document_count": self.document_count,
            "positive_by_indicator": self.positive_by_indicator,
            "negative_by_indicator": self.negative_by_indicator,
            "country_pillars": self.country_pillars,
            "pending_case_ids": self.pending_case_ids,
            "pending_document_ids": self.pending_document_ids,
            "issues": self.issues,
        }


def audit_coverage(
    cases: Iterable[GoldenCase],
    documents: Iterable[GoldenDocument],
    *,
    approved_only: bool = False,
) -> CoverageAudit:
    """Check size, indicator boundaries, country pillars, and review state.

    Structural completeness deliberately does not imply legal approval. The
    pending lists are reported separately so candidate expansion can land
    without being included in formal accuracy claims.
    """
    all_cases = list(cases)
    all_documents = list(documents)
    selected = (
        [case for case in all_cases if case.review.status == "approved"]
        if approved_only
        else all_cases
    )
    selected_document_ids = {case.document_id for case in selected}
    selected_documents = [
        document for document in all_documents
        if document.document_id in selected_document_ids
    ]

    positives = Counter(case.indicator_id for case in selected if case.should_map)
    negatives = Counter(case.indicator_id for case in selected if not case.should_map)
    country_pillars = {
        country: sorted(
            {case.indicator_id.split(".", 1)[0] for case in selected if case.country_code == country}
        )
        for country in sorted(TARGET_COUNTRIES)
    }

    issues: list[str] = []
    if len(selected) < MIN_CASES:
        issues.append(f"case count {len(selected)} is below minimum {MIN_CASES}")
    if len(selected) > MAX_CASES:
        issues.append(f"case count {len(selected)} exceeds target maximum {MAX_CASES}")
    for indicator in sorted(CORE_INDICATORS):
        if positives[indicator] == 0:
            issues.append(f"indicator {indicator} has no positive case")
        if negatives[indicator] == 0:
            issues.append(f"indicator {indicator} has no boundary negative")
    for country, pillars in country_pillars.items():
        missing = sorted({"6", "7"} - set(pillars))
        if missing:
            issues.append(f"country {country} is missing pillar(s): {', '.join(missing)}")

    return CoverageAudit(
        case_count=len(selected),
        document_count=len(selected_documents),
        positive_by_indicator={key: positives[key] for key in sorted(CORE_INDICATORS)},
        negative_by_indicator={key: negatives[key] for key in sorted(CORE_INDICATORS)},
        country_pillars=country_pillars,
        pending_case_ids=sorted(
            case.case_id for case in selected if case.review.status == "pending"
        ),
        pending_document_ids=sorted(
            document.document_id
            for document in selected_documents
            if document.review.status == "pending"
        ),
        issues=issues,
    )
