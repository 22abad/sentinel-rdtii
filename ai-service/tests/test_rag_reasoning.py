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


# ── output_format wiring ────────────────────────────────────────────────
from schemas import RAGQueryRequest
from workflows.nodes.rag import _prompt, _format_instruction


def test_no_format_selected_adds_no_instruction():
    p = _prompt(RAGQueryRequest(question="Does SGP localize data?"))
    assert "Response format:" not in p


def test_each_known_format_injects_its_instruction():
    for fmt, needle in [
        ("json", "valid JSON object"),
        ("table", "Markdown table"),
        ("bullets", "bulleted list"),
        ("plain", "plain prose"),
        ("markdown", "clear Markdown"),
    ]:
        p = _prompt(RAGQueryRequest(question="q", output_format=fmt))
        assert "Response format:" in p
        assert needle in p


def test_format_is_case_insensitive_and_trimmed():
    assert _format_instruction("  JSON ") == _format_instruction("json")
    assert _format_instruction("json")


def test_unknown_format_is_ignored():
    assert _format_instruction("xml") == ""
    p = _prompt(RAGQueryRequest(question="q", output_format="xml"))
    assert "Response format:" not in p


def test_format_instruction_is_last_for_recency():
    p = _prompt(RAGQueryRequest(question="q", output_format="table"))
    assert p.rstrip().endswith("only if context is essential.")


# ── deep_thinking graceful fallback (plain model rejects think=true) ──────
import asyncio as _asyncio
import types as _types

from workflows.nodes import rag as _rag


class _FakeCompletions:
    def __init__(self, fail_on_think):
        self.fail_on_think = fail_on_think
        self.calls = []

    def create(self, *, model, messages, stream, temperature, extra_body):
        self.calls.append(extra_body)
        if self.fail_on_think and extra_body.get("think"):
            raise RuntimeError('"qwen2.5:3b" does not support thinking')
        msg = SimpleNamespace(content="Localization is required.")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _patch_ollama(monkeypatch, fail_on_think):
    fake = _types.SimpleNamespace(chat=_types.SimpleNamespace(completions=_FakeCompletions(fail_on_think)))
    monkeypatch.setattr(_rag, "_client", lambda: fake)
    import api.system as sysmod
    monkeypatch.setattr(sysmod, "_OLLAMA_MODEL", "qwen2.5:3b", raising=False)
    monkeypatch.setattr(sysmod, "_RDTII_SYSTEM_PROMPT", "sys", raising=False)
    return fake.chat.completions


def test_deep_thinking_falls_back_when_model_rejects_thinking(monkeypatch):
    comp = _patch_ollama(monkeypatch, fail_on_think=True)
    req = RAGQueryRequest(question="Does SGP localize data?", deep_thinking=True)
    answer, reasoning = _asyncio.run(_rag._complete(req))
    assert answer == "Localization is required."
    assert reasoning == ""  # plain model → no trace, but NO crash
    # It tried think first, then retried without it.
    assert comp.calls == [{"think": True}, {}]


def test_no_deep_thinking_never_sends_think(monkeypatch):
    comp = _patch_ollama(monkeypatch, fail_on_think=True)
    req = RAGQueryRequest(question="q", deep_thinking=False)
    _asyncio.run(_rag._complete(req))
    assert comp.calls == [{}]


def test_unrelated_error_is_not_swallowed(monkeypatch):
    class _Boom:
        calls = []
        def create(self, **kw):
            self.calls.append(kw.get("extra_body"))
            raise RuntimeError("connection refused")
    fake = _types.SimpleNamespace(chat=_types.SimpleNamespace(completions=_Boom()))
    monkeypatch.setattr(_rag, "_client", lambda: fake)
    import api.system as sysmod
    monkeypatch.setattr(sysmod, "_OLLAMA_MODEL", "m", raising=False)
    monkeypatch.setattr(sysmod, "_RDTII_SYSTEM_PROMPT", "s", raising=False)
    req = RAGQueryRequest(question="q", deep_thinking=True)
    try:
        _asyncio.run(_rag._complete(req))
        assert False, "should have raised"
    except RuntimeError as e:
        assert "connection refused" in str(e)  # only thinking errors fall back
