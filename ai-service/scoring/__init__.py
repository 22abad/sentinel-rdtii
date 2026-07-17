"""Deterministic scoring functions per RDTII 2.1 indicator.

Each `score_X_Y(features)` function takes the feature dict produced by an
LLM provider and returns a Literal[0.0, 0.25, 0.5, 1.0] per the rule in the
RDTII 2.1 guide.

The scoring layer is deterministic Python — never an LLM. Why:
    1. Auditability: a reviewer can read the rule and confirm the score.
    2. Separation of concerns: an LLM bug becomes "wrong feature extraction"
       (catchable), not "wrong score" (unrecoverable).
    3. The scoring rules are public; encoding them is mechanical.

Implementation lives in `scoring/pillar_6.py` and `scoring/pillar_7.py`.
The `score_indicator()` dispatcher routes to the right per-indicator function.
"""

from __future__ import annotations

import logging
from typing import Literal

# 0.8 appears in the official Round 2 criteria (e.g. 3.1 foreign equity tiers).
Score = Literal[0.0, 0.25, 0.5, 0.75, 0.8, 1.0]

logger = logging.getLogger(__name__)

# The score for an indicator MUST be one the official methodology defines for
# THAT indicator — no fabricated in-between tier. This map is hard-coded from the
# "RDTII 2.1 Methodology" sheet's score column (verified 2026-07-17). Round 1
# scope (P6 = 6.1-6.4, P7 = 7.1-7.5); every value is exactly what the official
# answer key can contain. Note there is deliberately NO 6.5 here — the official
# P6 has only four indicators, and 7.4 is 0/0.5/1 (its old fabricated 0.25 tier
# only exists officially for indicator 3.4). See score_indicator's guard.
OFFICIAL_ALLOWED_SCORES: dict[str, frozenset[float]] = {
    "6.1": frozenset({0.0, 0.5, 1.0}),
    "6.2": frozenset({0.0, 0.5, 1.0}),
    "6.3": frozenset({0.0, 1.0}),
    "6.4": frozenset({0.0, 0.5, 1.0}),
    "7.1": frozenset({0.0, 0.5, 1.0}),
    "7.2": frozenset({0.0, 0.5, 1.0}),
    "7.3": frozenset({0.0, 1.0}),
    "7.4": frozenset({0.0, 0.5, 1.0}),
    "7.5": frozenset({0.0, 1.0}),
}


def _enforce_official_score(indicator_id: str, score: float, justification: str) -> tuple[float, str]:
    """Guard: never emit a score the official key can't contain for this indicator.

    For an indicator with a known official value set, snap an off-spec score to
    the nearest allowed value and log loudly (a scorer bug must be caught, but a
    judge's run must not ship a fabricated tier). Indicators without a hard-coded
    set (other pillars) pass through unchanged."""
    allowed = OFFICIAL_ALLOWED_SCORES.get(indicator_id)
    if allowed is None or score in allowed:
        return score, justification
    snapped = min(allowed, key=lambda a: (abs(a - score), a))
    logger.error(
        "Off-spec score %s for indicator %s (official allows %s) — snapped to %s. "
        "This is a scorer bug; scores must match the official methodology exactly.",
        score, indicator_id, sorted(allowed), snapped,
    )
    note = f" [corrected from off-spec {score}: official {indicator_id} allows {sorted(allowed)}]"
    return snapped, justification + note


def score_indicator(indicator_id: str, features: dict) -> tuple[Score, str]:
    """Dispatch to the correct per-indicator scorer.

    Bespoke pillar modules win where they exist (their rules encode boundary
    cases the generic path cannot); every other Round 2 indicator falls back
    to the methodology-driven generic scorer, which maps the extracted
    criterion tier to its published score.

    Returns:
        A tuple of (score, justification_string).

    Raises NotImplementedError for indicators outside the RDTII 2.1 methodology.
    """
    score, justification = _dispatch(indicator_id, features)
    return _enforce_official_score(indicator_id, score, justification)


def _dispatch(indicator_id: str, features: dict) -> tuple[Score, str]:
    # Imported lazily so partial pillar modules do not make package import fail.
    try:
        if indicator_id.startswith("2."):
            from . import pillar_2 as _p2

            return _p2.score(indicator_id, features)
        if indicator_id.startswith("5."):
            from . import pillar_5 as _p5

            return _p5.score(indicator_id, features)
        if indicator_id.startswith("6."):
            from . import pillar_6 as _p6

            return _p6.score(indicator_id, features)
        if indicator_id.startswith("7."):
            from . import pillar_7 as _p7

            return _p7.score(indicator_id, features)
    except (ImportError, AttributeError, NotImplementedError):
        # Bespoke module missing or does not cover this id — try generic.
        pass

    from . import generic as _generic

    return _generic.score(indicator_id, features)


__all__ = ["Score", "score_indicator", "OFFICIAL_ALLOWED_SCORES"]
