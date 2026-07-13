"""RDTII 2.1 methodology loader — the single source of truth for Round 2.

Loads ``data/rdtii21_methodology.json`` (extracted from the official Round 2
database by tools/build_round2_baseline.py) and parses each indicator's
scoring criteria into a machine-usable rule:

  * ``options``  — the numbered criteria ("1) More than three measures", …)
  * ``scores``   — the aligned possible scores, descending (1, 0.75, …, 0)
  * ``counting_step`` — set when the rule is additive ("0.25 for each
    measure, up to 1"), so the scorer can count instead of tiering.

The generic feature spec (features.py) and the generic deterministic scorer
(scoring/generic.py) are both driven by these rules, so adding or fixing an
indicator is a data change, not a code change.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# ai-service/methodology.py -> parents[1] == repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
METHODOLOGY_PATH = REPO_ROOT / "data" / "rdtii21_methodology.json"

_OPTION_RE = re.compile(r"^\s*(\d+)\)\s*(.+?)\s*$")
_COUNTING_RE = re.compile(r"\(\s*([\d.]+)\s+for\s+each\b", re.IGNORECASE)


@dataclass(frozen=True)
class IndicatorRule:
    """One indicator's official scoring rule, parsed."""

    indicator_id: str
    pillar: int
    pillar_name: str
    category: str
    criteria: str
    options: tuple[str, ...]
    scores: tuple[float, ...]
    counting_step: float | None

    @property
    def max_score(self) -> float:
        return max(self.scores) if self.scores else 1.0

    @property
    def min_score(self) -> float:
        return min(self.scores) if self.scores else 0.0


def _parse_scores(raw: str) -> tuple[float, ...]:
    out: list[float] = []
    for token in raw.split("\n"):
        token = token.strip().split()[0] if token.strip() else ""
        try:
            out.append(float(token))
        except ValueError:
            continue
    return tuple(out)


def _parse_options(criteria: str) -> tuple[str, ...]:
    options: list[str] = []
    for line in criteria.split("\n"):
        m = _OPTION_RE.match(line)
        if m:
            options.append(m.group(2))
        elif options and line.strip() and not line.strip().startswith("("):
            # Continuation of the previous option wrapped onto a new line.
            options[-1] += " " + line.strip()
    return tuple(options)


@lru_cache(maxsize=1)
def load_methodology() -> dict[str, IndicatorRule]:
    """Load and parse every Round 2 indicator rule (cached)."""

    if not METHODOLOGY_PATH.exists():
        return {}
    rules: dict[str, IndicatorRule] = {}
    for record in json.loads(METHODOLOGY_PATH.read_text(encoding="utf-8")):
        criteria = record.get("criteria", "")
        counting = _COUNTING_RE.search(criteria)
        rules[record["indicator_id"]] = IndicatorRule(
            indicator_id=record["indicator_id"],
            pillar=int(record["pillar"]),
            pillar_name=record.get("pillar_name", ""),
            category=record.get("category", ""),
            criteria=criteria,
            options=_parse_options(criteria),
            scores=_parse_scores(record.get("possible_scores", "")),
            counting_step=float(counting.group(1)) if counting else None,
        )
    return rules


def get_rule(indicator_id: str) -> IndicatorRule | None:
    """Return the parsed rule for an indicator, or None if outside Round 2."""

    return load_methodology().get(indicator_id.strip())


__all__ = ["IndicatorRule", "load_methodology", "get_rule"]
