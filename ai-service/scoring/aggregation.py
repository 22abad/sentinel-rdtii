"""Economy-level score aggregation for the RDTII 2.1 methodology.

Our pipeline scores each provision independently, but several indicators are
scored at the ECONOMY level with a count rule: their criterion 1 (top score)
reads "... OR more than one measure under category (2)". So an economy with two
or more category-2 (half-score) measures scores the FULL value for that
indicator, even though each individual provision only earns the half score.

`escalate_economy_score` applies that methodology rule when aggregating the
per-provision scores of one (economy, indicator) into a single economy score.
The set of escalation indicators is derived from the official methodology text,
not hand-listed.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_MORE_THAN_ONE = re.compile(r"more than one\s+(?:measure|measures)", re.IGNORECASE)


@lru_cache(maxsize=1)
def count_escalation_indicators() -> frozenset[str]:
    """Indicators whose criterion 1 escalates on "more than one category-2
    measure", read from the official methodology's criteria text."""
    try:
        path = Path(__file__).resolve().parents[1].parent / "data" / "rdtii21_methodology.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("indicators", raw) if isinstance(raw, dict) else raw
        items = items if isinstance(items, list) else list(items.values())
    except Exception:  # noqa: BLE001
        return frozenset()
    out = set()
    for item in items:
        criteria = str(item.get("criteria", ""))
        # Only the first criterion (the top score) carries the escalation.
        first = criteria.split("\n", 1)[0] if criteria else ""
        first = re.split(r"\b2\)", criteria, maxsplit=1)[0] or first
        if _MORE_THAN_ONE.search(first):
            code = str(item.get("indicator_id", "")).strip()
            scores = _parse_scores(item.get("possible_scores", ""))
            if code and scores:
                out.add(code)
    return frozenset(out)


def _parse_scores(raw: str) -> tuple[float, ...]:
    vals = []
    for tok in re.split(r"[\s/,]+", str(raw)):
        try:
            vals.append(float(tok))
        except ValueError:
            continue
    return tuple(sorted(set(vals), reverse=True))


@lru_cache(maxsize=256)
def _indicator_scores(indicator_id: str) -> tuple[float, ...]:
    try:
        path = Path(__file__).resolve().parents[1].parent / "data" / "rdtii21_methodology.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("indicators", raw) if isinstance(raw, dict) else raw
        items = items if isinstance(items, list) else list(items.values())
        for item in items:
            if str(item.get("indicator_id", "")).strip() == indicator_id:
                return _parse_scores(item.get("possible_scores", ""))
    except Exception:  # noqa: BLE001
        pass
    return ()


def escalate_economy_score(indicator_id: str, provision_scores: list[float]) -> float:
    """Aggregate one (economy, indicator)'s per-provision scores to an economy
    score, applying the "more than one category-2 measure -> top score" rule.

    - Any provision already at the top score -> top score.
    - Otherwise, if two or more provisions sit at the category-2 (half) tier,
      escalate to the top score.
    - Else the plain maximum.
    """
    if not provision_scores:
        return 0.0
    top = max(provision_scores)
    allowed = _indicator_scores(indicator_id)
    if indicator_id not in count_escalation_indicators() or len(allowed) < 3:
        return top

    full = max(allowed)
    if top >= full:
        return full
    # The category-2 tier is the second-highest allowed score (the half tier).
    half = sorted(allowed, reverse=True)[1]
    half_count = sum(1 for s in provision_scores if abs(s - half) < 1e-9)
    return full if half_count >= 2 else top


__all__ = ["escalate_economy_score", "count_escalation_indicators"]
