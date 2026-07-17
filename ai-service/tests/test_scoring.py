"""Tests for the deterministic scoring functions (Pillars 6 & 7).

Each indicator gets at least 3 cases covering:
    - the high-score path (1.0)
    - a mid-score path where applicable (0.5 / 0.25)
    - the low-score / "no requirement" path (0.0)
    - the government-data exclusion where applicable

Indicator IDs are exercised both via the per-indicator function and via
the top-level `score_indicator` dispatcher to verify wiring.
"""

from __future__ import annotations

import pytest

from scoring import score_indicator as _score_indicator
from scoring.pillar_6 import (
    score_6_1 as _score_6_1,
    score_6_2 as _score_6_2,
    score_6_3 as _score_6_3,
    score_6_4 as _score_6_4,
    score_6_5 as _score_6_5,
)
from scoring.pillar_7 import (
    score_7_1 as _score_7_1,
    score_7_2 as _score_7_2,
    score_7_3 as _score_7_3,
    score_7_4 as _score_7_4,
    score_7_5 as _score_7_5,
)


# Score-only adapters. Commit 1394980 changed every per-indicator scorer
# to return (Score, justification: str) so the deterministic
# rule-explanation could replace the LLM-hallucinated "impact" field in
# /api/extract output. The numeric assertions below pre-date that change
# and only care about the score; we strip the justification here so the
# whole suite stays one-liners. Tests that want to lock the
# justification text should call the underlying _score_X_Y functions
# directly.
def _strip(fn):
    return lambda features: fn(features)[0]


score_indicator = lambda iid, f: _score_indicator(iid, f)[0]
score_6_1 = _strip(_score_6_1)
score_6_2 = _strip(_score_6_2)
score_6_3 = _strip(_score_6_3)
score_6_4 = _strip(_score_6_4)
score_6_5 = _strip(_score_6_5)
score_7_1 = _strip(_score_7_1)
score_7_2 = _strip(_score_7_2)
score_7_3 = _strip(_score_7_3)
score_7_4 = _strip(_score_7_4)
score_7_5 = _strip(_score_7_5)


# ──────────────────────────────────────────────────────────────────────────
# Pillar 6
# ──────────────────────────────────────────────────────────────────────────


class TestIndicator6_1:
    """Ban & local processing requirements."""

    def test_personal_data_without_requirement_scores_zero(self):
        # A pure privacy law that mentions personal data but imposes no
        # ban / local-processing requirement must NOT trigger 6.1.
        # Per RDTII 2.1 guide: "score 0 when the data is permitted to be
        # transferred freely without any requirement."
        assert score_6_1({"personal_data": True}) == 0.0

    def test_personal_data_with_ban_scores_1(self):
        assert score_6_1({"personal_data": True, "has_ban": True}) == 1.0

    def test_personal_data_with_local_processing_scores_1(self):
        assert (
            score_6_1({"personal_data": True, "has_local_processing": True}) == 1.0
        )

    def test_horizontal_scope_without_requirement_scores_zero(self):
        # Same gate logic as personal_data: no ban + no local processing -> 0.
        assert score_6_1({"horizontal_scope": True}) == 0.0

    def test_horizontal_scope_with_local_processing_scores_1(self):
        assert (
            score_6_1({"horizontal_scope": True, "has_local_processing": True}) == 1.0
        )

    def test_two_economies_affected_scores_1(self):
        assert (
            score_6_1(
                {
                    "has_ban": True,
                    "num_economies_affected": 2,
                    "personal_data": False,
                    "horizontal_scope": False,
                }
            )
            == 1.0
        )

    def test_non_personal_specific_sector_scores_half(self):
        assert (
            score_6_1(
                {
                    "has_local_processing": True,
                    "personal_data": False,
                    "horizontal_scope": False,
                    "num_economies_affected": 1,
                }
            )
            == 0.5
        )

    def test_no_requirement_scores_zero(self):
        assert (
            score_6_1({"has_ban": False, "has_local_processing": False}) == 0.0
        )

    def test_government_data_only_excluded(self):
        # Even with personal data + ban, gov-only excludes the indicator.
        assert (
            score_6_1(
                {
                    "applies_to_government_data_only": True,
                    "personal_data": True,
                    "has_ban": True,
                }
            )
            == 0.0
        )

    def test_empty_features_scores_zero(self):
        assert score_6_1({}) == 0.0

    def test_non_integer_num_economies_does_not_crash(self):
        # LLMs occasionally emit non-numeric strings for count fields.
        # The scorer should default to 0, not raise ValueError.
        for garbage in ("2+", "unknown", "", None, "many", "N/A"):
            assert (
                score_6_1(
                    {
                        "has_ban": True,
                        "num_economies_affected": garbage,
                    }
                )
                == 0.5
            ), f"Failed on num_economies_affected={garbage!r}"

    def test_string_integer_num_economies_parsed(self):
        # JSON sometimes carries integers as strings; honor them.
        assert (
            score_6_1(
                {
                    "has_ban": True,
                    "num_economies_affected": "3",
                }
            )
            == 1.0
        )


class TestIndicator6_2:
    """Local storage requirements."""

    def test_personal_data_with_storage_scores_1(self):
        assert score_6_2({"personal_data": True, "has_local_storage": True}) == 1.0

    def test_horizontal_scope_with_storage_scores_1(self):
        assert (
            score_6_2({"horizontal_scope": True, "has_local_storage": True}) == 1.0
        )

    def test_sectoral_non_personal_scores_half(self):
        assert (
            score_6_2(
                {
                    "has_local_storage": True,
                    "personal_data": False,
                    "horizontal_scope": False,
                }
            )
            == 0.5
        )

    def test_no_storage_requirement_scores_zero(self):
        assert score_6_2({"has_local_storage": False, "personal_data": True}) == 0.0

    def test_government_data_only_excluded(self):
        assert (
            score_6_2(
                {
                    "applies_to_government_data_only": True,
                    "has_local_storage": True,
                    "personal_data": True,
                }
            )
            == 0.0
        )


class TestIndicator6_3:
    """Infrastructure requirements (binary)."""

    def test_with_infrastructure_scores_1(self):
        assert score_6_3({"has_infrastructure_req": True}) == 1.0

    def test_without_infrastructure_scores_zero(self):
        assert score_6_3({"has_infrastructure_req": False}) == 0.0

    def test_government_data_only_excluded(self):
        assert (
            score_6_3(
                {
                    "applies_to_government_data_only": True,
                    "has_infrastructure_req": True,
                }
            )
            == 0.0
        )

    def test_empty_features_scores_zero(self):
        assert score_6_3({}) == 0.0


class TestIndicator6_4:
    """Conditional flow regimes."""

    def test_personal_data_with_condition_scores_1(self):
        assert (
            score_6_4({"personal_data": True, "has_conditional_flow": True}) == 1.0
        )

    def test_horizontal_scope_with_condition_scores_1(self):
        assert (
            score_6_4({"horizontal_scope": True, "has_conditional_flow": True}) == 1.0
        )

    def test_sectoral_non_personal_scores_half(self):
        assert (
            score_6_4(
                {
                    "has_conditional_flow": True,
                    "personal_data": False,
                    "horizontal_scope": False,
                }
            )
            == 0.5
        )

    def test_no_condition_scores_zero(self):
        assert (
            score_6_4({"has_conditional_flow": False, "personal_data": True}) == 0.0
        )


class TestIndicator6_5:
    """Not in agreement with binding commitments (inverted score)."""

    def test_no_binding_agreement_scores_1(self):
        assert score_6_5({"has_binding_agreement": False}) == 1.0

    def test_has_binding_agreement_scores_zero(self):
        assert score_6_5({"has_binding_agreement": True}) == 0.0

    def test_missing_feature_defaults_to_no_agreement(self):
        # Missing => falsy => "no agreement signed" => high score (gap).
        assert score_6_5({}) == 1.0


# ──────────────────────────────────────────────────────────────────────────
# Pillar 7
# ──────────────────────────────────────────────────────────────────────────


class TestIndicator7_1:
    """Lack of comprehensive data protection framework."""

    def test_comprehensive_framework_scores_zero(self):
        assert score_7_1({"has_comprehensive_framework": True}) == 0.0

    def test_sectoral_only_scores_half(self):
        assert (
            score_7_1(
                {
                    "has_comprehensive_framework": False,
                    "has_sectoral_framework_only": True,
                }
            )
            == 0.5
        )

    def test_no_framework_scores_1(self):
        assert (
            score_7_1(
                {
                    "has_comprehensive_framework": False,
                    "has_sectoral_framework_only": False,
                }
            )
            == 1.0
        )

    def test_comprehensive_takes_precedence_over_sectoral(self):
        # If both flags are True, comprehensive wins (0).
        assert (
            score_7_1(
                {
                    "has_comprehensive_framework": True,
                    "has_sectoral_framework_only": True,
                }
            )
            == 0.0
        )


class TestIndicator7_2:
    """Lack of dedicated cybersecurity framework."""

    def test_dedicated_law_scores_zero(self):
        assert score_7_2({"has_dedicated_cybersecurity_law": True}) == 0.0

    def test_sectoral_only_scores_half(self):
        assert (
            score_7_2(
                {
                    "has_dedicated_cybersecurity_law": False,
                    "has_sectoral_cybersecurity_only": True,
                }
            )
            == 0.5
        )

    def test_no_law_scores_1(self):
        assert (
            score_7_2(
                {
                    "has_dedicated_cybersecurity_law": False,
                    "has_sectoral_cybersecurity_only": False,
                }
            )
            == 1.0
        )


class TestIndicator7_3:
    """Minimum data retention period."""

    def test_minimum_period_scores_1(self):
        assert score_7_3({"has_minimum_retention_period": True}) == 1.0

    def test_no_minimum_period_scores_zero(self):
        assert score_7_3({"has_minimum_retention_period": False}) == 0.0

    def test_government_data_only_excluded(self):
        assert (
            score_7_3(
                {
                    "applies_to_government_data_only": True,
                    "has_minimum_retention_period": True,
                }
            )
            == 0.0
        )


class TestIndicator7_4:
    """DPIA / DPO requirements."""

    def test_horizontal_dpo_scores_1(self):
        assert (
            score_7_4({"has_dpo_requirement": True, "horizontal_scope": True}) == 1.0
        )

    def test_horizontal_dpo_with_dpia_scores_1(self):
        assert (
            score_7_4(
                {
                    "has_dpo_requirement": True,
                    "has_dpia_requirement": True,
                    "horizontal_scope": True,
                }
            )
            == 1.0
        )

    def test_sectoral_dpo_scores_half(self):
        assert (
            score_7_4({"has_dpo_requirement": True, "horizontal_scope": False}) == 0.5
        )

    def test_sectoral_dpo_with_dpia_scores_half(self):
        assert (
            score_7_4(
                {
                    "has_dpo_requirement": True,
                    "has_dpia_requirement": True,
                    "horizontal_scope": False,
                }
            )
            == 0.5
        )

    def test_only_dpia_scores_zero(self):
        # The official 7.4 scale is strictly DPO-based (1 / 0.5 / 0). A DPIA
        # requirement without a DPO is NOT a scored tier — it must not earn a
        # fabricated 0.25 (that value only exists officially for indicator 3.4).
        assert (
            score_7_4(
                {
                    "has_dpo_requirement": False,
                    "has_dpia_requirement": True,
                }
            )
            == 0.0
        )

    def test_no_requirement_scores_zero(self):
        assert score_7_4({}) == 0.0


class TestIndicator7_5:
    """Government access to personal data without judicial oversight."""

    def test_unrestricted_gov_access_scores_1(self):
        assert (
            score_7_5({"has_government_access_without_judicial_oversight": True})
            == 1.0
        )

    def test_no_unrestricted_access_scores_zero(self):
        assert (
            score_7_5({"has_government_access_without_judicial_oversight": False})
            == 0.0
        )

    def test_empty_features_scores_zero(self):
        assert score_7_5({}) == 0.0


class TestConsentGateVeto:
    """A consent-gated disclosure must not read as unfettered government access."""

    # PDPA 2012 s59(5) — the data-protection Commission's own consent-gated
    # disclosure, previously misread as "government access without oversight".
    _PDPA_S59 = (
        "the Commission may disclose, or authorise any specified person to "
        "disclose, any information relating to any matter referred to in "
        "subsection (1) in any of the following circumstances: (a) where the "
        "consent of the person to whom the information relates has been obtained"
    )
    # A genuine 7.5 provision — police access, not consent-based.
    _CPC_S39 = (
        "A police officer may access any computer and any data stored therein "
        "for the purposes of an investigation."
    )

    def test_detects_consent_gate(self):
        from scoring.pillar_7 import is_consent_gated_access

        assert is_consent_gated_access(self._PDPA_S59)
        assert is_consent_gated_access("disclosure with the consent of the individual")
        # real access powers and negated consent are NOT consent-gated
        assert not is_consent_gated_access(self._CPC_S39)
        assert not is_consent_gated_access(
            "the authority may access data without the individual's consent"
        )

    def test_veto_clears_feature_and_drops_score_to_zero(self):
        from scoring.pillar_7 import veto_consent_gated_government_access

        features = {"has_government_access_without_judicial_oversight": True}
        reasons = veto_consent_gated_government_access("7.5", self._PDPA_S59, features)
        assert reasons and "consent" in reasons[0].lower()
        assert features["has_government_access_without_judicial_oversight"] is False
        assert score_7_5(features) == 0.0

    def test_veto_leaves_real_government_access_untouched(self):
        from scoring.pillar_7 import veto_consent_gated_government_access

        features = {"has_government_access_without_judicial_oversight": True}
        reasons = veto_consent_gated_government_access("7.5", self._CPC_S39, features)
        assert reasons == []
        assert features["has_government_access_without_judicial_oversight"] is True
        assert score_7_5(features) == 1.0

    def test_veto_only_applies_to_7_5(self):
        from scoring.pillar_7 import veto_consent_gated_government_access

        features = {"has_government_access_without_judicial_oversight": True}
        assert veto_consent_gated_government_access("7.1", self._PDPA_S59, features) == []
        assert features["has_government_access_without_judicial_oversight"] is True

    # Australia Crimes Act 1914 s3LA — access requires a magistrate's order, so a
    # judicial lock is present: 7.5 → 0, not 1.
    _CRIMES_S3LA = (
        "A constable may apply to a magistrate for an order requiring a specified "
        "person to provide information or assistance to access data on a computer."
    )

    def test_judicial_warrant_vetoes_7_5(self):
        from scoring.pillar_7 import is_judicially_authorised_access, veto_consent_gated_government_access

        assert is_judicially_authorised_access(self._CRIMES_S3LA)
        assert is_judicially_authorised_access("access is permitted only under a search warrant")
        # genuine unfettered access is NOT judicially authorised
        assert not is_judicially_authorised_access(self._CPC_S39)
        assert not is_judicially_authorised_access(
            "the agency may access data without a warrant where security requires"
        )

        features = {"has_government_access_without_judicial_oversight": True}
        reasons = veto_consent_gated_government_access("7.5", self._CRIMES_S3LA, features)
        assert reasons and "judicial" in reasons[0].lower()
        assert score_7_5(features) == 0.0

    def test_warrantless_access_still_scores_one(self):
        from scoring.pillar_7 import veto_consent_gated_government_access

        features = {"has_government_access_without_judicial_oversight": True}
        assert veto_consent_gated_government_access("7.5", self._CPC_S39, features) == []
        assert score_7_5(features) == 1.0


class TestNoScoreHallucination:
    """Every P6/P7 scorer may only ever return an official methodology value.

    Enforces the standing rule: scores are hard-coded to the official scale, with
    no fabricated in-between tier (this is what the score_7_4 0.25 bug violated).
    """

    import itertools as _it

    # The boolean feature keys each bespoke scorer reads.
    _FEATURE_KEYS = {
        "6.1": ["has_ban", "has_local_processing", "horizontal_scope", "personal_data"],
        "6.2": ["has_local_storage", "horizontal_scope", "personal_data"],
        "6.3": ["has_infrastructure_req"],
        "6.4": ["has_conditional_flow", "horizontal_scope", "personal_data"],
        "7.1": ["has_comprehensive_framework", "has_sectoral_framework_only"],
        "7.2": ["has_dedicated_cybersecurity_law", "has_sectoral_cybersecurity_only"],
        "7.3": ["has_minimum_retention_period"],
        "7.4": ["has_dpo_requirement", "has_dpia_requirement", "horizontal_scope"],
        "7.5": ["has_government_access_without_judicial_oversight"],
    }

    def test_every_score_is_official(self):
        from scoring import OFFICIAL_ALLOWED_SCORES, score_indicator

        for ind, keys in self._FEATURE_KEYS.items():
            allowed = OFFICIAL_ALLOWED_SCORES[ind]
            for combo in self._it.product([True, False], repeat=len(keys)):
                features = dict(zip(keys, combo))
                score, _ = score_indicator(ind, features)
                assert score in allowed, (
                    f"{ind} returned off-spec {score} for {features}; "
                    f"official allows {sorted(allowed)}"
                )

    def test_guard_snaps_off_spec_score(self):
        # A fabricated tier (like the old 7.4 0.25) is snapped to an official value.
        from scoring import _enforce_official_score

        score, note = _enforce_official_score("7.4", 0.25, "x")
        assert score in {0.0, 0.5}
        assert "off-spec" in note

    def test_guard_passes_through_unknown_indicator(self):
        # Indicators without a hard-coded official set are untouched.
        from scoring import _enforce_official_score

        assert _enforce_official_score("3.1", 0.8, "x") == (0.8, "x")

    def test_no_official_indicator_uses_fabricated_tiers(self):
        from scoring import OFFICIAL_ALLOWED_SCORES

        for ind, allowed in OFFICIAL_ALLOWED_SCORES.items():
            assert allowed <= {0.0, 0.5, 1.0}, f"{ind} lists a non-R1 tier: {allowed}"


# ──────────────────────────────────────────────────────────────────────────
# Dispatcher wiring
# ──────────────────────────────────────────────────────────────────────────


class TestDispatcher:
    """Sanity check that score_indicator() routes correctly."""

    @pytest.mark.parametrize(
        "indicator_id,features,expected",
        [
            ("6.1", {"personal_data": True, "has_ban": True}, 1.0),
            ("2.1", {"procurement_preference": True}, 1.0),
            ("5.1", {"has_competition": True}, 0.0),
            ("6.2", {"has_local_storage": True, "personal_data": True}, 1.0),
            ("6.3", {"has_infrastructure_req": True}, 1.0),
            ("6.4", {"has_conditional_flow": True, "horizontal_scope": True}, 1.0),
            ("6.5", {"has_binding_agreement": False}, 1.0),
            ("7.1", {"has_comprehensive_framework": True}, 0.0),
            ("7.2", {"has_dedicated_cybersecurity_law": True}, 0.0),
            ("7.3", {"has_minimum_retention_period": True}, 1.0),
            (
                "7.4",
                {"has_dpo_requirement": True, "horizontal_scope": True},
                1.0,
            ),
            (
                "7.5",
                {"has_government_access_without_judicial_oversight": True},
                1.0,
            ),
        ],
    )
    def test_dispatcher_routes_correctly(self, indicator_id, features, expected):
        assert score_indicator(indicator_id, features) == expected

    def test_unsupported_indicator_raises(self):
        with pytest.raises(NotImplementedError):
            score_indicator("99.9", {})

    def test_known_but_unimplemented_indicator_raises(self):
        with pytest.raises(NotImplementedError):
            score_indicator("1.1", {"tariff_rate": 5})
