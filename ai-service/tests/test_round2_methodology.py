"""Tests for the methodology-driven Round 2 extraction/scoring layer.

The single source of truth is data/rdtii21_methodology.json; these tests lock
in the contract between the loader, the generic feature spec, and the generic
deterministic scorer.
"""

from __future__ import annotations

import pytest

from features import get_feature_spec, list_supported_indicators
from methodology import get_rule, load_methodology
from scoring import score_indicator
from scoring.generic import score as generic_score


def test_methodology_loads_all_61_indicators():
    rules = load_methodology()
    assert len(rules) == 61
    pillars = {r.pillar for r in rules.values()}
    assert pillars == set(range(1, 13))


def test_rule_parsing_tiers_align_with_options():
    # 1.4 has 5 numbered criteria and 5 published scores, plus a counting note.
    rule = get_rule("1.4")
    assert rule is not None
    assert len(rule.options) == 5
    assert rule.scores == (1.0, 0.75, 0.5, 0.25, 0.0)
    assert rule.counting_step == 0.25
    # 3.2 is a plain binary rule.
    rule32 = get_rule("3.2")
    assert rule32.scores == (1.0, 0.0)
    assert rule32.counting_step is None
    # 0.50 in the sheet parses to 0.5, and 3.1's 0.8 tier survives.
    assert 0.8 in get_rule("3.1").scores


def test_generic_spec_embeds_official_criteria():
    spec = get_feature_spec("3.1")  # no bespoke spec — must be generic
    assert "measure_present" in spec and "matched_criterion" in spec
    assert "Ban (0%)" in spec["matched_criterion"]["description"]
    # Counting indicators also ask for a measure count.
    assert "measure_count" in get_feature_spec("1.4")
    # Bespoke specs still win.
    assert "has_minimum_retention_period" in get_feature_spec("7.3")


def test_generic_scorer_tier_mapping():
    score, why = generic_score("3.1", {"measure_present": True, "matched_criterion": 1})
    assert score == 1.0 and "criterion 1" in why
    score, _ = generic_score("3.1", {"measure_present": True, "matched_criterion": 2})
    assert score == 0.8
    score, _ = generic_score("3.1", {"measure_present": False})
    assert score == 0.0


def test_generic_scorer_counting_rule():
    # 1.4: 0.25 per measure, capped at 1.
    assert generic_score("1.4", {"measure_present": True, "measure_count": 2})[0] == 0.5
    assert generic_score("1.4", {"measure_present": True, "measure_count": 9})[0] == 1.0
    assert generic_score("1.4", {"measure_present": True, "measure_count": 0})[0] == 0.0


def test_generic_scorer_conservative_when_tier_missing():
    score, why = generic_score("3.2", {"measure_present": True})
    assert score == 0.0
    assert "human review" in why


def test_dispatcher_falls_back_to_generic_for_new_pillars():
    # 8.2 has no bespoke module — the dispatcher must route to generic.
    score, why = score_indicator("8.2", {"measure_present": True, "matched_criterion": 1})
    assert score == get_rule("8.2").scores[0]
    # Bespoke 7.3 still routes to the hand-written rule.
    score, _ = score_indicator("7.3", {"has_minimum_retention_period": True})
    assert score == 1.0
    # Outside the methodology entirely -> NotImplementedError (critic then flags).
    with pytest.raises(NotImplementedError):
        score_indicator("99.9", {})


def test_supported_indicators_cover_round2():
    supported = set(list_supported_indicators())
    assert set(load_methodology()) <= supported


def test_classifier_routes_round2_categories():
    from classifier import classify_indicator

    # 3.1 phrases derive from "Foreign equity limits in sectors relevant to
    # digital trade" — a law about foreign equity caps must route there.
    matched = classify_indicator(
        "Foreign equity limits apply to digital trade platforms: foreign "
        "investors may hold no more than 49 per cent of the equity."
    )
    assert "3.1" in matched
