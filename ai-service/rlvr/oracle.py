"""The LABELLED reward — a per-candidate decomposition of the golden harness.

``evaluation/metrics.py`` grades a whole prediction *set* against the reviewed
cases and reports rates. RLVR needs the same judgement for a single candidate,
so this module reuses the harness's own primitives (``evidence_similarity``,
``clauses_compatible``, and the offset-recovery rule behind
``citation_exact_match_rate``) rather than restating them. If the harness's
definition of "correct" changes, this reward changes with it — that coupling is
intentional.

This reward is only defined where a reviewed ``GoldenCase`` exists: 29 cases,
16 positive. It is the measuring stick and the future training signal. It must
never reach the inference-time selector — see ``rlvr/__init__.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.metrics import clauses_compatible, evidence_similarity
from evaluation.models import GoldenCase

# Matching threshold — the harness default. Kept as a named constant so a
# drift between the two is a visible edit rather than a silent divergence.
EVIDENCE_THRESHOLD = 0.8

# Component weights, following what the graded feedback punished hardest:
# a quote that does not contain the mapped requirement outranks a wrong scope.
W_MATCHED = 0.35
W_CITATION_EXACT = 0.30
W_SCORE_CORRECT = 0.15
W_ARTICLE_CORRECT = 0.10
W_SCOPE_CORRECT = 0.10

# A prediction that hits an explicit `should_map: false` case is the failure
# mode the grader called out by name ("not quite related, remove"). It is worse
# than silence, so it is the only negative value the candidate reward can take.
R_NEGATIVE_CASE_HIT = -1.0

# Case-level terms, for scoring a whole (case -> answered / abstained) decision
# rather than one candidate. Needed because 20 of 29 cases expect 0.0 and 13
# are explicit negatives: a reward that pays only for correct rows makes
# "answer nothing" optimal.
R_MISSED_POSITIVE = -0.5
R_AVOIDED_NEGATIVE = 0.25


@dataclass(frozen=True)
class OracleReward:
    """Labelled reward for one candidate against one reviewed case."""

    total: float
    matched: bool
    negative_case_hit: bool
    citation_exact: bool
    article_correct: bool
    score_correct: bool
    scope_correct: bool
    evidence_similarity: float
    case_id: str

    def as_record(self) -> dict:
        return {
            "total": round(self.total, 6),
            "matched": self.matched,
            "negative_case_hit": self.negative_case_hit,
            "citation_exact": self.citation_exact,
            "article_correct": self.article_correct,
            "score_correct": self.score_correct,
            "scope_correct": self.scope_correct,
            "evidence_similarity": round(self.evidence_similarity, 6),
            "case_id": self.case_id,
        }


def _citation_is_exact(quote: str, document_text: str) -> bool:
    """The harness's citation rule, applied to a candidate.

    ``evaluation.metrics._citation_is_exact`` checks
    ``text[quote_start:quote_end] == verbatim_quote``. A candidate carries no
    offsets yet, so the equivalent question is whether the quote occurs
    literally in the document — if it does, the pipeline's offsets will
    recover it; if it does not, no offset pair can.
    """
    return bool(quote) and quote in document_text


def score_against_case(
    data: dict[str, Any],
    case: GoldenCase,
    *,
    document_text: str,
    raw_score: float | None = None,
    evidence_threshold: float = EVIDENCE_THRESHOLD,
) -> OracleReward:
    """Grade one candidate against one reviewed case."""
    quote = (data.get("verbatim_quote") or "").strip()
    similarity = evidence_similarity(case.verbatim_quote, quote) if quote else 0.0
    matched = similarity >= evidence_threshold

    if matched and not case.should_map:
        return OracleReward(
            total=R_NEGATIVE_CASE_HIT,
            matched=True,
            negative_case_hit=True,
            citation_exact=False,
            article_correct=False,
            score_correct=False,
            scope_correct=False,
            evidence_similarity=similarity,
            case_id=case.case_id,
        )

    if not matched:
        # Either a false positive (wrong provision) or a correct abstention on
        # a negative case. Both are zero at candidate level; the distinction is
        # a case-level property, handled by ``score_case_decision``.
        return OracleReward(
            total=0.0,
            matched=False,
            negative_case_hit=False,
            citation_exact=False,
            article_correct=False,
            score_correct=False,
            scope_correct=False,
            evidence_similarity=similarity,
            case_id=case.case_id,
        )

    citation_exact = _citation_is_exact(quote, document_text)
    article_correct = clauses_compatible(
        case.article_clause, (data.get("article_clause") or "").strip()
    )
    scope_correct = case.expected_scope == (data.get("scope") or "").strip().lower()
    score_correct = (
        raw_score is not None and abs(case.expected_raw_score - raw_score) < 1e-9
    )

    total = (
        W_MATCHED
        + W_CITATION_EXACT * citation_exact
        + W_ARTICLE_CORRECT * article_correct
        + W_SCORE_CORRECT * score_correct
        + W_SCOPE_CORRECT * scope_correct
    )

    return OracleReward(
        total=total,
        matched=True,
        negative_case_hit=False,
        citation_exact=citation_exact,
        article_correct=article_correct,
        score_correct=score_correct,
        scope_correct=scope_correct,
        evidence_similarity=similarity,
        case_id=case.case_id,
    )


def score_case_decision(case: GoldenCase, answered: bool) -> float:
    """Case-level term that prices silence.

    Without this, the objective is maximised by never answering: 13 of 29
    cases are explicit negatives and 20 expect a zero score.
    """
    if case.should_map and not answered:
        return R_MISSED_POSITIVE
    if not case.should_map and not answered:
        return R_AVOIDED_NEGATIVE
    return 0.0



__all__ = [
    "EVIDENCE_THRESHOLD",
    "OracleReward",
    "R_AVOIDED_NEGATIVE",
    "R_MISSED_POSITIVE",
    "R_NEGATIVE_CASE_HIT",
    "score_against_case",
    "score_case_decision",
]
