"""Deep-Thinking reasoning capture for the rag.query node.

_split_reasoning is the pure seam: it separates a reasoning trace from the
answer whether the model exposes it as a distinct field or inlines it in
<think>…</think>. Pinned here without an Ollama server.
"""

from __future__ import annotations

from types import SimpleNamespace

from workflows.nodes.rag import _split_reasoning


def _msg(content, *, reasoning_content=None, model_extra=None):
    m = SimpleNamespace(content=content)
    if reasoning_content is not None:
        m.reasoning_content = reasoning_content
    if model_extra is not None:
        m.model_extra = model_extra
    return m


def test_plain_model_has_no_reasoning():
    answer, reasoning = _split_reasoning(_msg("The answer is 42."))
    assert answer == "The answer is 42."
    assert reasoning == ""


def test_reasoning_content_field():
    answer, reasoning = _split_reasoning(
        _msg("Final answer.", reasoning_content="  step one, step two  ")
    )
    assert answer == "Final answer."
    assert reasoning == "step one, step two"


def test_reasoning_from_model_extra_fallback():
    # openai client stashes unknown fields on model_extra rather than an attr.
    answer, reasoning = _split_reasoning(
        _msg("Answer.", model_extra={"reasoning_content": "hidden trace"})
    )
    assert answer == "Answer."
    assert reasoning == "hidden trace"


def test_inline_think_tags_are_split_out():
    answer, reasoning = _split_reasoning(
        _msg("<think>weigh the statute\nthen decide</think>\n\nData localization applies.")
    )
    assert answer == "Data localization applies."
    assert reasoning == "weigh the statute\nthen decide"


def test_reasoning_content_wins_over_inline_tags():
    answer, reasoning = _split_reasoning(
        _msg("<think>inline</think>Answer.", reasoning_content="field wins")
    )
    assert reasoning == "field wins"
    # The inline tag is left untouched when the field already carried reasoning.
    assert "Answer." in answer
