"""Selection, sampling, oracle and trajectory logging."""

from __future__ import annotations

import json

import pytest

from evaluation.models import GoldenCase
from rlvr.best_of_n import Candidate, select_best
from rlvr.oracle import (
    R_AVOIDED_NEGATIVE,
    R_MISSED_POSITIVE,
    R_NEGATIVE_CASE_HIT,
    score_against_case,
    score_case_decision,
)
from rlvr.sampling import (
    SamplingParams,
    best_of_n_from_env,
    derive_seed,
    sampling_ladder,
)
from rlvr.trajectory import TrajectoryWriter

CHUNK = (
    "(1) An organisation must not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with requirements "
    "prescribed under this Act."
)
QUOTE = (
    "An organisation must not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with requirements "
    "prescribed under this Act."
)


def _data(quote: str = QUOTE, **overrides) -> dict:
    data = {
        "verbatim_quote": quote,
        "article_clause": "Section 26",
        "source_legislation": "Personal Data Protection Act 2012",
        "source_url": "https://sso.agc.gov.sg/Act/PDPA2012",
        "last_update": "2025-12-05",
        "scope": "horizontal",
    }
    data.update(overrides)
    return data


def _candidate(quote: str, index: int) -> Candidate:
    return Candidate(data=_data(quote), sampling=sampling_ladder(4)[index])


# ── Sampling ────────────────────────────────────────────────────────────


def test_sample_zero_is_always_greedy():
    """The safety property: candidate 0 reproduces today's pipeline exactly."""
    ladder = sampling_ladder(4, document_id="doc", indicator_id="6.4")
    assert ladder[0].temperature == 0.0
    assert ladder[0].top_p == 1.0
    assert ladder[0].is_greedy
    assert all(not p.is_greedy for p in ladder[1:])


def test_ladder_of_one_is_the_current_pipeline():
    assert len(sampling_ladder(1)) == 1
    assert sampling_ladder(1)[0].is_greedy


def test_seeds_are_deterministic_across_processes():
    """A run a judge cannot reproduce is a run we cannot submit."""
    assert derive_seed("doc", 3, "6.4", 1) == derive_seed("doc", 3, "6.4", 1)
    assert derive_seed("doc", 3, "6.4", 1) != derive_seed("doc", 3, "6.4", 2)


def test_seeds_differ_per_sample_within_a_draw():
    ladder = sampling_ladder(4, document_id="d", chunk_index=1, indicator_id="7.3")
    assert len({p.seed for p in ladder}) == 4


def test_zero_samples_is_rejected():
    with pytest.raises(ValueError):
        sampling_ladder(0)


def test_best_of_n_env_defaults_to_single_shot(monkeypatch):
    monkeypatch.delenv("RDTII_BEST_OF_N", raising=False)
    assert best_of_n_from_env() == 1
    monkeypatch.setenv("RDTII_BEST_OF_N", "nonsense")
    assert best_of_n_from_env() == 1
    monkeypatch.setenv("RDTII_BEST_OF_N", "4")
    assert best_of_n_from_env() == 4


# ── Selection ───────────────────────────────────────────────────────────


def test_ties_keep_the_greedy_candidate():
    """Best-of-N must never regress the current output on a tie."""
    candidates = [_candidate(QUOTE, 0), _candidate(QUOTE, 1)]
    selection = select_best(candidates, chunk_text=CHUNK, indicator_id="6.4")
    assert selection.winner_index == 0
    assert not selection.upgraded


def test_a_strictly_better_sample_wins():
    bad = Candidate(data=_data("must not transfer"), sampling=sampling_ladder(2)[0])
    good = Candidate(data=_data(QUOTE), sampling=sampling_ladder(2)[1])
    selection = select_best([bad, good], chunk_text=CHUNK, indicator_id="6.4")
    assert selection.winner_index == 1
    assert selection.upgraded
    assert selection.margin > 0


def test_diversity_collapse_is_reported_not_swallowed():
    """k identical draws means k x spend for one candidate — say so."""
    candidates = [_candidate(QUOTE, i) for i in range(3)]
    selection = select_best(candidates, chunk_text=CHUNK, indicator_id="6.4")
    assert selection.diversity_collapsed
    assert selection.distinct_candidates == 1


def test_distinct_candidates_are_not_flagged_as_collapsed():
    candidates = [_candidate(QUOTE, 0), _candidate("must not transfer", 1)]
    selection = select_best(candidates, chunk_text=CHUNK, indicator_id="6.4")
    assert not selection.diversity_collapsed


def test_empty_candidate_list_is_an_error():
    with pytest.raises(ValueError):
        select_best([], chunk_text=CHUNK, indicator_id="6.4")


def test_selector_signature_cannot_accept_labels():
    """Structural guard: no route for a GoldenCase to reach selection."""
    import inspect

    params = set(inspect.signature(select_best).parameters)
    assert not params & {"case", "cases", "golden", "oracle", "label", "labels"}


# ── Oracle ──────────────────────────────────────────────────────────────


def _case(**overrides) -> GoldenCase:
    payload = {
        "case_id": "sgp-pdpa-6-4-section-26",
        "country_code": "SGP",
        "document_id": "sgp-pdpa-2012",
        "source_legislation": "Personal Data Protection Act 2012",
        "official_source_url": "https://sso.agc.gov.sg/Act/PDPA2012",
        "source_status": "in_force",
        "indicator_id": "6.4",
        "should_map": True,
        "article_clause": "Section 26",
        "verbatim_quote": QUOTE,
        "expected_scope": "horizontal",
        "coverage_detail": "Personal data",
        "expected_raw_score": 1.0,
        "expected_cat_score": 1.0,
        "legal_rationale": "A sufficiently detailed legal rationale.",
        "review": {
            "status": "approved",
            "reviewer_role": "Substantive Lead",
            "reviewed_at": "2026-07-13",
            "framework_version": "RDTII 2.1",
        },
    }
    payload.update(overrides)
    return GoldenCase(**payload)


def test_correct_candidate_scores_high():
    reward = score_against_case(
        _data(), _case(), document_text=CHUNK, raw_score=1.0
    )
    assert reward.matched
    assert reward.citation_exact
    assert reward.score_correct
    assert reward.total == pytest.approx(1.0)


def test_hitting_an_explicit_negative_case_is_the_only_negative():
    """The grader's 'not quite related, remove' failure mode."""
    reward = score_against_case(
        _data(),
        _case(should_map=False, expected_raw_score=0.0, expected_cat_score=0.0),
        document_text=CHUNK,
    )
    assert reward.negative_case_hit
    assert reward.total == R_NEGATIVE_CASE_HIT


def test_wrong_provision_scores_zero_not_negative():
    reward = score_against_case(
        _data("Some entirely unrelated sentence about tariffs on goods."),
        _case(),
        document_text=CHUNK,
    )
    assert not reward.matched
    assert reward.total == 0.0


def test_abstention_is_priced_so_silence_is_not_optimal():
    """20 of 29 cases expect 0.0; without this the policy learns to abstain."""
    assert score_case_decision(_case(), answered=False) == R_MISSED_POSITIVE
    negative = _case(should_map=False, expected_raw_score=0.0, expected_cat_score=0.0)
    assert score_case_decision(negative, answered=False) == R_AVOIDED_NEGATIVE
    assert score_case_decision(_case(), answered=True) == 0.0


# ── Trajectory ──────────────────────────────────────────────────────────


def test_trajectory_writes_one_json_line_per_candidate(tmp_path):
    path = tmp_path / "traj.jsonl"
    writer = TrajectoryWriter(path=path, run_id="run-1", provider="p", model="m")
    for i in range(3):
        writer.log_candidate(
            document_id="doc",
            chunk_index=0,
            indicator_id="6.4",
            sampling=SamplingParams(i, 0.0 if i == 0 else 0.7, 1.0).as_record(),
            candidate=_data(),
            proxy={"total": 0.9},
            selected=i == 0,
        )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert writer.records_written == 3
    first = json.loads(lines[0])
    assert first["indicator_id"] == "6.4"
    assert first["selected"] is True
    assert first["candidate"]["verbatim_quote"] == QUOTE


def test_trajectory_disabled_writes_nothing(tmp_path):
    path = tmp_path / "off.jsonl"
    writer = TrajectoryWriter(path=path, run_id="r", enabled=False)
    writer.log_candidate(
        document_id="d",
        chunk_index=0,
        indicator_id="6.4",
        sampling={},
        candidate=_data(),
        proxy={},
        selected=False,
    )
    assert not path.exists()
    assert writer.records_written == 0
