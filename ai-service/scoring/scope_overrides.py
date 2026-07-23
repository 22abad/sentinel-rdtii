"""Deterministic scope guards for cross-domain over-scoring traps.

The Round-2 error taxonomy showed the dominant residual error is over-scoring
official-0 cells: the extractor finds a *genuine* measure whose text keyword-
matches an indicator, but the law is out of that indicator's official scope.
The generic scorer and the cross-model checker can't catch these — both see a
real restriction in the quote. This module encodes a small set of scope rules
grounded in the official methodology's OWN scope statements and exceptions
(an `enforce_indicator_rules` guard, limited to methodology-explicit cases to
avoid regressions).

Rules ONLY ever lower a score to 0 (a scope mismatch means "no qualifying
measure for THIS indicator"); they never raise a score. Every drop is
annotated so a reviewer sees exactly which scope rule fired.
"""

from __future__ import annotations

# Product-health / vice control laws — never digital-trade measures. A Tobacco
# Control Act's advertising ban is a health measure, not an online-advertising
# (9.x) / import (10.x) / e-commerce (12.x) digital-trade restriction.
_PRODUCT_CONTROL = (
    "tobacco", "cigarette", "alcohol", "liquor", "narcotic", "drug abuse",
    "gambling", "firearm", "pornography", "pornographic",
)
# Pillars where the product-control trap appears (digital-trade restriction
# indicators). Pillars 6/7 (data) are deliberately excluded — a health law can
# still carry a real data-retention clause.
_DIGITAL_TRADE_PILLARS = ("9.", "10.", "12.")

# 9.1 methodology text: "except internationally agreed illegal content / child
# pornography" — such blocking is explicitly NOT a 9.1 measure.
_ILLEGAL_CONTENT = (
    "child pornography", "child sexual", "obscene", "obscenity",
    "pornograph", "terroris",
)


def apply_scope_override(
    indicator_id: str,
    quote: str,
    law_name: str,
    score: float,
    justification: str,
) -> tuple[float, str]:
    """Return (score, justification), lowering to 0 on a methodology-grounded
    scope mismatch. No-op for zero scores or when no rule matches."""
    if not score or score <= 0:
        return score, justification

    law_lower = (law_name or "").lower()
    text_lower = f"{law_name or ''} {quote or ''}".lower()

    # Rule 1 — 9.1 excludes illegal / child-content blocking (methodology's own
    # exception). Applies only when the evidence is about that content.
    if indicator_id == "9.1" and any(k in text_lower for k in _ILLEGAL_CONTENT):
        return 0.0, (
            "Scope override (9.1): methodology explicitly excludes blocking of "
            "internationally-agreed illegal content / child pornography -> score 0. "
            f"[was: {justification}]"
        )

    # Rule 2 — product-health/vice control laws are not digital-trade measures.
    # Check the law name AND the verbatim: at scoring time the law name may not
    # be resolved yet (it's filled from the document title later), but a tobacco
    # ad-ban provision names the product in its own text.
    if any(indicator_id.startswith(p) for p in _DIGITAL_TRADE_PILLARS) and any(
        k in text_lower for k in _PRODUCT_CONTROL
    ):
        return 0.0, (
            f"Scope override ({indicator_id}): a product-control law "
            f"('{(law_name or '')[:40]}') is a health/vice measure, not a "
            f"digital-trade restriction -> score 0. [was: {justification}]"
        )

    return score, justification


__all__ = ["apply_scope_override"]
