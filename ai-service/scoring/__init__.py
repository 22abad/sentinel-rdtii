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

from typing import Literal

# 0.8 appears in the official Round 2 criteria (e.g. 3.1 foreign equity tiers).
Score = Literal[0.0, 0.25, 0.5, 0.75, 0.8, 1.0]


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


__all__ = ["Score", "score_indicator"]
