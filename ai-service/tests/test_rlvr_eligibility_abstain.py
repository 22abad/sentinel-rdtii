"""Eligibility must not punish a candidate for the verifier's own failures.

Both behaviours here were found by the --with-llm measurement at 708976b, where
every one of the three hygiene losses was a page_dump beating the real
provision:

  * ``sgp-cpc-7-5-section-20`` — the verifier raised (ExtractionError). The
    error was scored as "ineligible" (0.0) against the REFERENCE, while the
    page_dump got a clean 1.0. A transient API failure decided the comparison.
  * ``sgp-cybersecurity-7-2-framework`` — 7.2 is an existence indicator. The LLM
    called the correct title-style evidence "a statement of legislative purpose,
    not a provision-level measure" and blessed the surrounding dump instead.

Both are the same underlying mistake: treating an eligibility signal as
authoritative in a situation the term was never valid for.
"""

from __future__ import annotations

from rlvr.reward import score_candidate

CHUNK = (
    "Section 20. The Public Prosecutor may by written order require a person "
    "to produce any document or thing relevant to an investigation without "
    "prior application to a court."
)
QUOTE = (
    "The Public Prosecutor may by written order require a person to produce "
    "any document or thing relevant to an investigation"
)


def _candidate(**overrides):
    data = {
        "verbatim_quote": QUOTE,
        "article_clause": "Section 20",
        "source_legislation": "Criminal Procedure Code",
        "source_url": "https://sso.agc.gov.sg/Act/CPC2010",
        "last_update": "2010",
        "scope": "horizontal",
        "score": 1.0,
    }
    data.update(overrides)
    return data


def _components(reward) -> dict[str, float]:
    return {c.name: c.value for c in reward.components}


# ── a verifier that raised is not a verdict ──────────────────────────────────


def test_verifier_failure_drops_the_term_instead_of_scoring_zero():
    failed = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(None, "VERIFIER ERROR: ExtractionError"),
    )
    assert "eligibility_supported" not in _components(failed), (
        "an errored verifier must abstain — scoring 0.0 penalises whichever "
        "candidate happened to hit the failure"
    )


def test_abstaining_scores_higher_than_being_judged_ineligible():
    """The whole point: an error must not cost the candidate anything."""
    abstained = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(None, "VERIFIER ERROR: ExtractionError"),
    )
    judged_no = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(0.0, "[independent_llm] not supported"),
    )
    assert abstained.total > judged_no.total


def test_abstaining_does_not_silently_award_credit():
    """Dropped from the denominator, not softened to a neutral 1.0."""
    abstained = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(None, "VERIFIER ERROR: ExtractionError"),
    )
    judged_yes = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(1.0, "[independent_llm] eligible for this indicator"),
    )
    assert abstained.total <= judged_yes.total


def test_abstention_is_recorded_in_the_notes():
    reward = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(None, "VERIFIER ERROR: ExtractionError"),
    )
    assert any("no judgement" in n for n in reward.notes), (
        "a dropped term must be visible in the record, not silently absent"
    )


def test_a_real_negative_verdict_is_still_scored():
    """Abstention must not become a way to launder genuine ineligibility."""
    reward = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(0.0, "[independent_llm] not supported"),
    )
    assert _components(reward)["eligibility_supported"] == 0.0


# ── existence indicators under the LLM arm ───────────────────────────────────

TITLE_CHUNK = "An Act to provide for the oversight and maintenance of national cybersecurity."
TITLE_QUOTE = "An Act to provide for the oversight and maintenance of national cybersecurity"


def _title_candidate():
    return {
        "verbatim_quote": TITLE_QUOTE,
        "article_clause": "",
        "source_legislation": "Cybersecurity Act 2018",
        "source_url": "https://sso.agc.gov.sg/Act/CA2018",
        "last_update": "2018",
        "scope": "horizontal",
        "score": 1.0,
    }


def test_existence_indicator_drops_eligibility_under_an_external_verdict():
    reward = score_candidate(
        _title_candidate(), chunk_text=TITLE_CHUNK, indicator_id="7.2",
        eligibility_override=(0.0, "[independent_llm] statement of legislative purpose"),
    )
    assert "eligibility_supported" not in _components(reward), (
        "the LLM arm rejects title-style evidence, which IS the valid answer "
        "for an existence indicator"
    )
    assert "single_provision" not in _components(reward)


def test_existence_indicator_keeps_eligibility_on_the_deterministic_arm():
    """The original exemption reasoning holds when no override is supplied."""
    reward = score_candidate(
        _title_candidate(), chunk_text=TITLE_CHUNK, indicator_id="7.2",
    )
    assert "eligibility_supported" in _components(reward), (
        "the deterministic 7.1/7.2 branches are feature-driven and do not "
        "penalise a bare title — dropping the term there would lose signal"
    )


def test_non_existence_indicator_keeps_eligibility_under_an_override():
    reward = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="7.5",
        eligibility_override=(0.0, "[independent_llm] not supported"),
    )
    assert "eligibility_supported" in _components(reward)
