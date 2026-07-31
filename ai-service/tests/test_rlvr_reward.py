"""Proxy-reward behaviour — the gates, the bands, and the anti-hack terms."""

from __future__ import annotations

from rlvr.reward import (
    EXISTENCE_INDICATORS,
    QUOTE_DUMP_GATE_CHARS,
    score_candidate,
)

CHUNK = (
    "Section 26  Transfer of personal data outside Singapore\n\n"
    "(1) An organisation must not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with requirements "
    "prescribed under this Act to ensure that organisations provide a standard "
    "of protection to personal data so transferred that is comparable to the "
    "protection under this Act."
)

GOOD_QUOTE = (
    "An organisation must not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with requirements "
    "prescribed under this Act to ensure that organisations provide a standard "
    "of protection to personal data so transferred that is comparable to the "
    "protection under this Act."
)


def _candidate(**overrides) -> dict:
    data = {
        "verbatim_quote": GOOD_QUOTE,
        "article_clause": "Section 26",
        "source_legislation": "Personal Data Protection Act 2012",
        "source_url": "https://sso.agc.gov.sg/Act/PDPA2012",
        "last_update": "2025-12-05",
        "scope": "horizontal",
        # The extractor always emits its structured features alongside the
        # quote, and `eligibility_supported` reads them — a fixture without
        # them is not a realistic candidate.
        "has_conditional_flow": True,
    }
    data.update(overrides)
    return data


def test_clean_candidate_passes_every_gate():
    reward = score_candidate(_candidate(), chunk_text=CHUNK, indicator_id="6.4")
    assert reward.passed_gates
    assert reward.failed_gates == ()
    assert reward.total > 0.9


def test_empty_quote_scores_zero_without_crashing():
    reward = score_candidate(
        _candidate(verbatim_quote=""), chunk_text=CHUNK, indicator_id="6.4"
    )
    assert reward.total == 0.0
    assert "quote_present" in reward.failed_gates


def test_paraphrase_fails_the_offset_gate():
    """A reworded quote is not a verbatim — the submission cannot use it."""
    paraphrased = GOOD_QUOTE.replace("must not", "shall not")
    reward = score_candidate(
        _candidate(verbatim_quote=paraphrased), chunk_text=CHUNK, indicator_id="6.4"
    )
    assert reward.total == 0.0
    assert "offsets_recover_quote" in reward.failed_gates


def test_page_dump_is_gated_not_merely_penalised():
    """The classic reward hack: quote everything so containment is guaranteed."""
    dump = ("x " * (QUOTE_DUMP_GATE_CHARS // 2 + 200)).strip()
    reward = score_candidate(
        _candidate(verbatim_quote=dump), chunk_text=dump, indicator_id="6.4"
    )
    assert reward.total == 0.0
    assert "quote_not_a_page_dump" in reward.failed_gates


def test_longer_quote_never_outranks_the_pinpoint_one():
    """Regression for the first measurement run, where a dump won 10 of 11."""
    pinpoint = score_candidate(_candidate(), chunk_text=CHUNK, indicator_id="6.4")
    whole_chunk = score_candidate(
        _candidate(verbatim_quote=CHUNK.strip()), chunk_text=CHUNK, indicator_id="6.4"
    )
    assert pinpoint.total >= whole_chunk.total


def test_invented_score_tier_fails_the_gate():
    """0.75 is not an allowed tier for 6.4 — no fabricated tiers."""
    reward = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="6.4", raw_score=0.75
    )
    assert "score_in_allowed_tiers" in reward.failed_gates
    assert reward.total == 0.0


def test_official_score_tier_passes():
    reward = score_candidate(
        _candidate(), chunk_text=CHUNK, indicator_id="6.4", raw_score=1.0
    )
    assert "score_in_allowed_tiers" not in reward.failed_gates


def test_missing_metadata_lowers_but_does_not_zero():
    """Metadata is a graded term, not a gate — a real quote still has value."""
    reward = score_candidate(
        _candidate(source_url="", last_update=""),
        chunk_text=CHUNK,
        indicator_id="6.4",
    )
    full = score_candidate(_candidate(), chunk_text=CHUNK, indicator_id="6.4")
    assert 0.0 < reward.total < full.total


class TestExistenceIndicators:
    """7.1/7.2 evidence the EXISTENCE of a framework — a title is valid.

    The reviewed golden fixtures cite 'Privacy Act 1988' (16 chars) for 7.1.
    An operative-provision prior scores that as boilerplate and ranks it below
    a manufactured page-dump, which is what the first measurement run found.
    """

    CHUNK = "Privacy Act 1988\n\nAn Act to make provision to protect the privacy of individuals."

    def test_bare_title_is_not_punished_for_7_1(self):
        reward = score_candidate(
            {
                "verbatim_quote": "Privacy Act 1988",
                "article_clause": "Australian Privacy Principle 8.1",
                "source_legislation": "Privacy Act 1988",
                "source_url": "https://example.gov.au/privacy",
                "last_update": "2024-12-01",
                "scope": "horizontal",
                "has_comprehensive_framework": True,
            },
            chunk_text=self.CHUNK,
            indicator_id="7.1",
        )
        assert reward.passed_gates
        assert reward.total > 0.9

    def test_same_title_is_punished_for_a_measure_indicator(self):
        """The exemption is scoped to existence indicators, not global.

        Asserts the RELATIVE invariants rather than an absolute floor. The
        reward is a ranking signal — its absolute level is not calibrated, and
        pinning a magic threshold here would just break on every reweight.
        A bare title on 6.1 currently scores ~0.83, high enough that this
        reward must not be used as a pass/fail filter (see the measurement
        report's rank-agreement number).
        """
        title = {
            "verbatim_quote": "Privacy Act 1988",
            "article_clause": "Australian Privacy Principle 8.1",
            "source_legislation": "Privacy Act 1988",
            "source_url": "https://example.gov.au/privacy",
            "last_update": "2024-12-01",
            "scope": "horizontal",
            "has_comprehensive_framework": True,
        }
        as_measure = score_candidate(title, chunk_text=self.CHUNK, indicator_id="6.1")
        as_existence = score_candidate(title, chunk_text=self.CHUNK, indicator_id="7.1")

        assert as_measure.total < as_existence.total

        # The mechanism, not just the totals: a framework title carries no
        # transfer ban or domestic-processing requirement, so the eligibility
        # gate refuses it for 6.1 while accepting it for 7.1.
        def _eligibility_value(reward):
            return next(
                c.value for c in reward.components if c.name == "eligibility_supported"
            )

        assert _eligibility_value(as_measure) == 0.0
        assert _eligibility_value(as_existence) == 1.0

    def test_exemption_set_is_explicit(self):
        assert EXISTENCE_INDICATORS == frozenset({"7.1", "7.2"})


def test_principle_style_citation_counts_as_pinpoint():
    """'Australian Privacy Principle 8.1' is a real pinpoint cite."""
    with_principle = score_candidate(
        _candidate(article_clause="Australian Privacy Principle 8.1"),
        chunk_text=CHUNK,
        indicator_id="6.4",
    )
    without = score_candidate(
        _candidate(article_clause="the Act"), chunk_text=CHUNK, indicator_id="6.4"
    )
    assert with_principle.total > without.total
