"""Candidate selection — the only place the proxy reward is consumed.

Two invariants this module exists to hold:

1. **Labels never reach the selector.** ``select_best`` takes candidates and
   proxy rewards. There is no parameter through which a ``GoldenCase`` could
   arrive, so selection cannot be tuned on the benchmark by accident.
2. **Greedy wins ties.** Candidate 0 is the temperature-0 draw — byte-identical
   to today's pipeline. ``>`` rather than ``>=`` means a sampled candidate must
   strictly beat it, so best-of-N cannot regress the current output on the
   proxy objective.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from rlvr.reward import ProxyReward, score_candidate
from rlvr.sampling import SamplingParams


@dataclass(frozen=True)
class Candidate:
    """One sampled extraction plus the decoding args that produced it."""

    data: dict[str, Any]
    sampling: SamplingParams

    @property
    def fingerprint(self) -> str:
        """Hash of the quote — used to detect diversity collapse."""
        quote = (self.data.get("verbatim_quote") or "").strip()
        return hashlib.sha256(quote.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Selection:
    """Outcome of one best-of-N draw."""

    winner: Candidate
    winner_index: int
    rewards: tuple[ProxyReward, ...]
    distinct_candidates: int
    diversity_collapsed: bool
    margin: float
    upgraded: bool

    def as_record(self) -> dict:
        return {
            "winner_index": self.winner_index,
            "distinct_candidates": self.distinct_candidates,
            "diversity_collapsed": self.diversity_collapsed,
            "margin": round(self.margin, 6),
            "upgraded": self.upgraded,
            "rewards": [r.as_record() for r in self.rewards],
        }


def select_best(
    candidates: list[Candidate],
    *,
    chunk_text: str,
    indicator_id: str,
    raw_scores: list[float | None] | None = None,
) -> Selection:
    """Score every candidate with the proxy reward and return the winner.

    ``diversity_collapsed`` is reported, never silently swallowed: if every
    draw produced the same quote, best-of-N spent k× the extractor budget for
    one candidate, and the caller should hear about it rather than see a
    plausible-looking selection record.
    """
    if not candidates:
        raise ValueError("select_best requires at least one candidate")

    scores = raw_scores or [None] * len(candidates)
    rewards = tuple(
        score_candidate(
            c.data,
            chunk_text=chunk_text,
            indicator_id=indicator_id,
            raw_score=scores[i] if i < len(scores) else None,
        )
        for i, c in enumerate(candidates)
    )

    best_index = 0
    for i in range(1, len(candidates)):
        if rewards[i].total > rewards[best_index].total:
            best_index = i

    distinct = len({c.fingerprint for c in candidates})
    others = [r.total for i, r in enumerate(rewards) if i != best_index]

    return Selection(
        winner=candidates[best_index],
        winner_index=best_index,
        rewards=rewards,
        distinct_candidates=distinct,
        diversity_collapsed=len(candidates) > 1 and distinct == 1,
        margin=rewards[best_index].total - max(others) if others else 0.0,
        upgraded=best_index != 0,
    )


__all__ = ["Candidate", "Selection", "select_best"]
