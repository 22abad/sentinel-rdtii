"""Adversarial refuter — decision seam + LLM adapter.

N independent models each try to REFUTE a mapping (vote: True = "does not
hold"); the mapping is killed only when the refute rate exceeds
``kill_threshold`` (default 0.5 = majority). ``refuter_verdict`` is the pure,
unit-tested decision; ``refute_mapping`` is the thin LLM adapter that gathers the
votes. Conservative: a tie, no votes, or an unparseable vote all survive
(flag-not-drop discipline).
"""
from __future__ import annotations

import asyncio

from providers.base import LLMProvider


def refuter_verdict(refutes: list[bool], *, kill_threshold: float = 0.5) -> dict:
    n = len(refutes)
    rate = round(sum(1 for r in refutes if r) / n, 3) if n else 0.0
    return {
        "refuted": rate > kill_threshold,
        "refute_rate": rate,
        "votes": n,
    }


def _prompt(quote: str, indicator: str, criterion: str) -> str:
    return f"""You are an adversarial reviewer. Your job is to REFUTE a proposed legal mapping if you honestly can. You are given ONE exact quote from a law, an RDTII 2.1 indicator, and the criterion it is claimed to satisfy.

Indicator: {indicator}
Claimed criterion: {criterion}
Exact quote:
\"\"\"{quote}\"\"\"

Does the quote FAIL to satisfy the claimed criterion — i.e. is the mapping wrong? A statement of principle/objective, mere topical relevance, or a bare grant of power WITHOUT the actual measure means the mapping is wrong (refuted=true). If the quote genuinely states the measure, refuted=false.

Output ONLY valid JSON: {{"refuted": true|false}}"""


async def refute_mapping(
    provider,
    *,
    quote: str,
    indicator: str,
    criterion: str,
    n_votes: int = 3,
    kill_threshold: float = 0.5,
) -> dict:
    """Gather ``n_votes`` independent refute votes and return the verdict."""
    async def _one() -> bool:
        try:
            raw = await asyncio.to_thread(
                provider.query,
                _prompt(quote, indicator, criterion),
                system="Output ONLY valid JSON. Refute only when the quote does not state the measure.",
            )
            return bool(LLMProvider.parse_json_response(raw).get("refuted"))
        except Exception:  # noqa: BLE001 — an unparseable/failed vote is NOT a refute
            return False

    votes = await asyncio.gather(*[_one() for _ in range(max(1, n_votes))])
    return refuter_verdict(list(votes), kill_threshold=kill_threshold)


__all__ = ["refuter_verdict", "refute_mapping"]
