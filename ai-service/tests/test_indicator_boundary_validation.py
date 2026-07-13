"""Exact-quote checks for the RDTII 6.1/6.4 boundary."""

from __future__ import annotations

from validation import validate_mapping


def _validate_6_1(quote: str):
    return validate_mapping(
        None,
        quote=quote,
        chunk_text=quote,
        indicator_id="6.1",
        features={},
        include_semantic_check=False,
        track_cross_reference=False,
    )


def test_conditional_transfer_quote_is_rejected_for_6_1():
    quote = (
        "An organisation must not transfer personal data outside Singapore except "
        "in accordance with requirements that ensure a comparable standard of protection."
    )
    result = _validate_6_1(quote)
    assert result.level == "reject"
    assert "indicator 6.4" in result.reasons[0]


def test_unrelated_subject_to_language_does_not_trigger_boundary_rule():
    result = _validate_6_1(
        "The licence is subject to annual renewal by the telecommunications authority."
    )
    assert result.level != "reject"


def test_separate_absolute_ban_survives_other_conditional_clause():
    quote = (
        "Health records shall not be transferred outside Australia. "
        "Other administrative information may be transferred subject to consent."
    )
    assert _validate_6_1(quote).level != "reject"


def test_local_processing_requirement_survives_conditional_language():
    quote = (
        "Personal data must be processed locally, and overseas transfer is subject "
        "to an adequate standard of protection."
    )
    assert _validate_6_1(quote).level != "reject"


def test_chinese_conditional_transfer_quote_is_rejected_for_6_1():
    quote = "个人信息处理者向境外提供个人信息，应当通过安全评估并符合规定条件。"
    result = _validate_6_1(quote)
    assert result.level == "reject"
    assert "indicator 6.4" in result.reasons[0]


def test_chinese_absolute_transfer_ban_remains_6_1():
    quote = "关键信息基础设施运营者严禁向境外提供受管制数据。"
    assert _validate_6_1(quote).level != "reject"


def test_chinese_separate_ban_survives_other_conditional_clause():
    quote = (
        "核心健康记录不得传输至境外。"
        "其他个人信息向境外提供时，应当取得个人单独同意。"
    )
    assert _validate_6_1(quote).level != "reject"
