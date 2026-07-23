"""Tests for the deterministic scope-override guards."""

from __future__ import annotations

from scoring.scope_overrides import apply_scope_override


def test_tobacco_law_dropped_for_online_advertising_indicator():
    # A Tobacco Control Act's ad ban is a health measure, not a 9.3 online-
    # advertising digital-trade restriction (official scored these 0).
    score, why = apply_scope_override(
        "9.3", "advertising of tobacco products is prohibited",
        "The Cigarettes and Other Tobacco Products (Prohibition of Advertisement) Act, 2003",
        1.0, "Matches criterion 1) Any restriction on online advertising",
    )
    assert score == 0.0
    assert "product-control" in why.lower()


def test_gambling_law_dropped_for_ecommerce_pillar():
    score, _ = apply_scope_override(
        "12.3", "online gambling is restricted", "Gambling Control Act", 1.0, "x"
    )
    assert score == 0.0


def test_9_1_illegal_content_exception():
    # 9.1 explicitly excludes blocking of child pornography / illegal content.
    score, why = apply_scope_override(
        "9.1", "blocking of child pornography and obscene material",
        "Pornography Law No. 44 of 2008", 1.0, "Matches criterion 1) Any blocking measure",
    )
    assert score == 0.0
    assert "9.1" in why


def test_product_law_NOT_dropped_for_data_pillar():
    # Pillars 6/7 are excluded — a tobacco law could still carry a real
    # data-retention clause, so we do not blanket-drop it there.
    score, _ = apply_scope_override(
        "7.3", "records shall be retained for at least 5 years",
        "Tobacco Control Act", 1.0, "5-year retention",
    )
    assert score == 1.0


def test_normal_online_advertising_law_survives():
    # A genuine digital-advertising regulation (not a product-control law) is
    # untouched.
    score, _ = apply_scope_override(
        "9.3", "online advertising must not be misleading",
        "Electronic Commerce Advertising Regulation", 1.0, "restriction",
    )
    assert score == 1.0


def test_zero_score_is_noop():
    score, why = apply_scope_override("9.3", "q", "Tobacco Act", 0.0, "no measure")
    assert score == 0.0 and why == "no measure"


def test_never_raises_a_score():
    # The guard only lowers; a non-matching case returns the input unchanged.
    score, _ = apply_scope_override("6.4", "cross-border transfer with consent",
                                    "Personal Data Protection Act", 0.5, "consent")
    assert score == 0.5


def test_product_term_detected_from_quote_when_law_name_empty():
    # In the eval/pipeline the law name may not be resolved at scoring time;
    # the product term in the verbatim must still trigger the guard.
    score, _ = apply_scope_override(
        "9.3", "No person shall advertise cigarettes or tobacco products.",
        "", 1.0, "Matches criterion 1) Any restriction on online advertising",
    )
    assert score == 0.0
