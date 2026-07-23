"""Tests for economy-level score escalation (more-than-one-measure rule)."""
from scoring.aggregation import count_escalation_indicators, escalate_economy_score


def test_escalation_indicators_are_methodology_derived():
    esc = count_escalation_indicators()
    # 2.3's criterion 1 explicitly says "OR more than one measure under (2)".
    assert "2.3" in esc and "2.1" in esc
    # 7.3 (minimum retention) has no count-escalation.
    assert "7.3" not in esc


def test_two_half_measures_escalate_to_full():
    assert escalate_economy_score("2.3", [0.5, 0.5]) == 1.0


def test_single_half_measure_stays_half():
    assert escalate_economy_score("2.3", [0.5]) == 0.5


def test_any_full_measure_wins():
    assert escalate_economy_score("2.3", [1.0, 0.5]) == 1.0


def test_non_escalation_indicator_unchanged():
    # 7.3 is not an escalation indicator; two halves stay a half (the max).
    assert escalate_economy_score("7.3", [0.5, 0.5]) == 0.5


def test_empty_scores():
    assert escalate_economy_score("2.3", []) == 0.0


def test_zero_scores_do_not_escalate():
    assert escalate_economy_score("2.3", [0.0, 0.0]) == 0.0
