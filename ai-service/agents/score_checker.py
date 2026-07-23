"""Cross-model second opinion for generic-scored indicators (Maker/Checker).

The generic methodology scorer (`scoring/generic.py`) maps the Extractor's
`matched_criterion` / `measure_present` features to a published score. On the
Round-2 benchmark the single dominant error family was OVER-scoring official-0
cells on P9-P12: one Extractor model reads topical relevance, a statement of
principle, or a bare grant of power as if it were a binding measure.

This module adds an independent second opinion for POSITIVE generic scores
only. A checker model — blind to the Extractor's features and score — re-reads
the exact quote against the official criterion text and returns the criterion
the quote EXPLICITLY satisfies (0 = principle / relevance / no measure). We
keep the conservative minimum of the two. A disagreement never silently drops
the row: it lowers the score and flags it for human review, matching our other
flag-not-drop gates.

Scope: only indicators that fall through to the generic scorer. Bespoke
Pillar 2/5/6/7 indicators are untouched — 6/7 already pass the
EligibilityVerifier gate, and the bespoke scorers encode their own boundaries.

Model: reuses the pipeline provider by default (a second, blind, conservative
pass is self-consistency — already catches over-claims). Set
RDTII_CHECKER_PROVIDER to a *different* provider name for a true cross-model
check. Disable entirely with RDTII_SCORE_CHECK=off.
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from dataclasses import dataclass, field

from providers.base import LLMProvider


# ── Override-rate ledger ─────────────────────────────────────────────────────
# The blind-verifier overturn rate is a HEADLINE quality signal, not just a gate.
# We track how often the blind checker actually disagrees with the extractor, so
# a run can report "the blind verifier reviewed N positive scores and overturned
# X% — nothing ships unverified." Process-local; sequential runs accumulate,
# parallel economies each keep their own.
@dataclass
class CheckerLedger:
    checks: int = 0
    overturned: int = 0
    by_indicator: Counter = field(default_factory=Counter)
    overturned_by_indicator: Counter = field(default_factory=Counter)

    def record(self, indicator_id: str, agreed: bool) -> None:
        self.checks += 1
        self.by_indicator[indicator_id] += 1
        if not agreed:
            self.overturned += 1
            self.overturned_by_indicator[indicator_id] += 1

    def summary(self) -> dict:
        rate = round(self.overturned / self.checks, 3) if self.checks else 0.0
        return {
            "blind_checks": self.checks,
            "overturned": self.overturned,
            "override_rate": rate,
        }


_LEDGER = CheckerLedger()


def checker_stats() -> dict:
    """Blind-verifier override stats accumulated this process (see CheckerLedger)."""
    return _LEDGER.summary()


def reset_checker_stats() -> None:
    global _LEDGER
    _LEDGER = CheckerLedger()

# Prefixes with a dedicated scorer; 6/7 also have the independent eligibility
# gate. Everything else falls through to scoring/generic.py.
_BESPOKE_PREFIXES = ("2.", "5.", "6.", "7.")

_provider_cache: dict[str, object] = {}


def is_generic_scored(indicator_id: str) -> bool:
    """True when this indicator is scored by the generic methodology path."""
    return not any(indicator_id.startswith(p) for p in _BESPOKE_PREFIXES)


def _enabled() -> bool:
    return os.getenv("RDTII_SCORE_CHECK", "on").strip().lower() not in {
        "off", "0", "false", "no",
    }


def _can_query(provider) -> bool:
    if provider is None:
        return False
    if getattr(provider, "name", "") in {"offline-fixture", "fake"}:
        return False
    return callable(getattr(provider, "query", None))


@dataclass
class ScoreCheck:
    """Outcome of the cross-model check. ``agreed`` false ⇒ score was lowered."""

    score: float
    agreed: bool
    reason: str  # empty when agreed / no-op


def _checker_provider(default_provider):
    """The provider to run the check with — a distinct one if configured."""
    name = os.getenv("RDTII_CHECKER_PROVIDER", "").strip()
    if not name or name == getattr(default_provider, "name", ""):
        return default_provider
    if name not in _provider_cache:
        try:
            from providers import resolve_provider

            _provider_cache[name] = resolve_provider(name)
        except Exception:  # noqa: BLE001 — fall back to the pipeline provider
            _provider_cache[name] = default_provider
    return _provider_cache[name]


def _score_for_tier(indicator_id: str, tier: int) -> float:
    """The published score the generic scorer assigns to criterion ``tier``."""
    from scoring import generic as _generic

    features = {"measure_present": tier >= 1, "matched_criterion": tier}
    score, _ = _generic.score(indicator_id, features)
    return float(score)


def _prompt(indicator_id: str, criteria: str, quote: str) -> str:
    return f"""You are an independent legal reviewer checking one mapping. You are given ONE exact quote from a law and the official RDTII 2.1 scoring criteria for indicator {indicator_id}. You are NOT told any prior score or label — judge only from the quote.

Official criteria (each numbered line is a tier; the FIRST tier is the strongest measure, the LAST tier means "no restriction / no measure"):
{criteria}

Exact quote:
\"\"\"{quote}\"\"\"

Which numbered criterion does the quote EXPLICITLY satisfy? Strict rules:
- A statement of principle, objective, purpose, or mere topical relevance is NOT a measure.
- A bare grant of power or legal basis, without the actual restriction/requirement, is NOT the measure.
- If none is explicitly satisfied, answer with the number of the "no restriction / no measure" tier.
- When unsure, choose the WEAKER (lower-scoring) tier.

Output ONLY valid JSON: {{"matched_criterion": <the criterion number>}}"""


async def check_generic_score(
    provider,
    indicator_id: str,
    quote: str,
    raw_score: float,
    cache: dict | None = None,
) -> ScoreCheck:
    """Independently re-check a positive generic score; keep the conservative min.

    No-op (returns the input score, ``agreed=True``) when: the check is disabled,
    the indicator is bespoke-scored, the score is already 0, the provider can't
    be queried, or the methodology has no criteria for the indicator.
    """
    if not _enabled() or not is_generic_scored(indicator_id) or raw_score <= 0:
        return ScoreCheck(raw_score, True, "")
    if not quote or not quote.strip():
        return ScoreCheck(raw_score, True, "")

    from methodology import get_rule

    rule = get_rule(indicator_id)
    if rule is None or not rule.options:
        return ScoreCheck(raw_score, True, "")

    checker = _checker_provider(provider)
    if not _can_query(checker):
        return ScoreCheck(raw_score, True, "")

    key = (indicator_id, " ".join(quote.split()))
    if cache is not None and key in cache:
        tier = cache[key]
    else:
        criteria = "\n".join(f"{i}) {' '.join(opt.split())}" for i, opt in enumerate(rule.options, 1))
        try:
            raw = await asyncio.to_thread(
                checker.query,
                _prompt(indicator_id, criteria, quote),
                system="Output ONLY valid JSON. Judge strictly from the quote; do not infer.",
            )
            parsed = LLMProvider.parse_json_response(raw)
            tier = int(parsed.get("matched_criterion"))
        except Exception:  # noqa: BLE001 — checker failure is a no-op, never a false demotion
            tier = -1
        if cache is not None:
            cache[key] = tier

    if not (0 <= tier <= len(rule.scores)):
        return ScoreCheck(raw_score, True, "")

    # A real second-model verdict was obtained — record it for the override rate.
    checker_score = _score_for_tier(indicator_id, tier)
    agreed = checker_score >= raw_score
    _LEDGER.record(indicator_id, agreed)
    if not agreed:
        return ScoreCheck(
            checker_score,
            False,
            (
                f"Cross-model checker read the quote as criterion {tier} "
                f"(score {checker_score}) against the extractor's {raw_score}; "
                "conservative minimum applied and flagged for human review."
            ),
        )
    return ScoreCheck(raw_score, True, "")


__all__ = [
    "ScoreCheck", "check_generic_score", "is_generic_scored",
    "checker_stats", "reset_checker_stats",
]
