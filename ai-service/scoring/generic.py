"""Generic deterministic scorer driven by the official RDTII 2.1 methodology.

Covers every Round 2 indicator that has no bespoke ``scoring/pillar_N.py``
rule. The LLM never chooses the number: it extracts *which official
criterion* the provision matches (a categorical fact, verifiable against the
published criteria text), and this module maps that criterion to its
published score. Counting rules ("0.25 for each measure, up to 1") use the
extracted measure count instead.

Kept deterministic and auditable: the justification always cites the matched
criterion verbatim from the methodology.
"""

from __future__ import annotations

from methodology import get_rule


def _snap(value: float, allowed: tuple[float, ...]) -> float:
    """Snap a computed value to the nearest allowed score (ties go lower)."""

    return min(allowed, key=lambda s: (abs(s - value), s))


def score(indicator_id: str, features: dict) -> tuple[float, str]:
    """Score one indicator from extracted features per the official criteria."""

    rule = get_rule(indicator_id)
    if rule is None or not rule.scores:
        raise NotImplementedError(
            f"Indicator {indicator_id} is outside the RDTII 2.1 methodology; "
            f"add a bespoke scorer before treating it as automated."
        )

    present = features.get("measure_present")
    if present is False or present in ("false", "no", 0):
        return rule.min_score, (
            f"No qualifying measure evidenced for '{rule.category.splitlines()[0]}' "
            f"-> score {rule.min_score}"
        )

    # Additive rules: score = step x count, capped, snapped to the allowed set.
    if rule.counting_step is not None:
        count = features.get("measure_count")
        if isinstance(count, bool):
            count = int(count)
        if isinstance(count, (int, float)) and count >= 0:
            raw = min(rule.max_score, rule.counting_step * int(count))
            snapped = _snap(raw, rule.scores)
            return snapped, (
                f"{int(count)} qualifying measure(s) x {rule.counting_step} "
                f"(capped at {rule.max_score}) -> score {snapped}"
            )

    # Tier rules: matched criterion k (1-based) -> k-th published score.
    tier = features.get("matched_criterion")
    if isinstance(tier, bool):
        tier = int(tier)
    if isinstance(tier, str) and tier.strip().isdigit():
        tier = int(tier.strip())
    if isinstance(tier, (int, float)):
        tier = int(tier)
        if 1 <= tier <= len(rule.scores):
            option = rule.options[tier - 1] if tier <= len(rule.options) else ""
            return rule.scores[tier - 1], (
                f"Matches official criterion {tier}) {option} -> score {rule.scores[tier - 1]}"
            )
        if tier == 0:
            return rule.min_score, "No official criterion matched -> minimum score"

    # A measure is evidenced but the tier could not be pinned down — stay
    # conservative and flag rather than guess a high score.
    return rule.min_score, (
        "Measure evidenced but no criterion tier extracted; conservative minimum "
        "score assigned — requires human review"
    )


__all__ = ["score"]
