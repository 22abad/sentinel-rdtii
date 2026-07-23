"""Tests for the terminal RAG-answer renderer (stn_cli.rag_render).

These assert the Rich markup we emit; `_plain` strips markup back to visible
text so we can also check the human-readable result. Markup-injection safety
(stray `[`/`]` in model text must not become Rich tags) is the load-bearing
case — the whole point of routing through this module instead of raw display.
"""

from __future__ import annotations

from rich.text import Text

from stn_cli.rag_render import inline, render_answer


def _plain(markup: str) -> str:
    """Visible text with all Rich markup tags removed."""
    return Text.from_markup(markup).plain


def test_bold_and_italic():
    out = inline("this is **bold** and *slanted*")
    assert "[bold]bold[/]" in out
    assert "[italic]slanted[/]" in out
    assert _plain(out) == "this is bold and slanted"


def test_underscore_identifier_not_italicised():
    # A field name with underscores must survive intact.
    out = inline("field source_file_sha256 stays literal")
    assert "[italic]" not in out
    assert _plain(out) == "field source_file_sha256 stays literal"


def test_indicator_and_pillar_highlight():
    out = inline("Pillar P6 indicator 7.3 restricts transfers")
    assert f"[bold #34d399]P6[/]" in out
    assert f"[bold #34d399]7.3[/]" in out
    # a score-shaped decimal is NOT an indicator ref
    assert "[bold #34d399]0.5[/]" not in inline("score of 0.5 applies")


def test_link_and_bare_url():
    out = inline("see [the act](https://ex.gov/a) or https://ex.gov/b")
    assert "the act" in _plain(out)
    assert "https://ex.gov/a" in _plain(out)
    assert "https://ex.gov/b" in _plain(out)


def test_markup_injection_is_neutralised():
    # Model text containing Rich-looking tags must render literally, never as
    # actual styling — this is the safety guarantee over raw display.
    raw = "danger [bold red]not styled[/] and [link=x]nope[/]"
    out = render_answer(raw)
    assert _plain(out) == raw  # brackets survive as visible characters
    assert "[bold red]" not in out.replace("\\[bold red]", "")  # only escaped form


def test_headings_bullets_and_blockquote():
    md = "## Findings\n\n- first point\n- second\n\n> quoted clause\n\n1. step one"
    out = render_answer(md)
    plain = _plain(out)
    assert "Findings" in plain
    assert "• first point" in plain
    assert "• second" in plain
    assert "▏ quoted clause" in plain
    assert "1. step one" in plain


def test_horizontal_rule():
    out = render_answer("above\n\n---\n\nbelow")
    plain = _plain(out)
    assert "above" in plain and "below" in plain
    assert "─" in plain  # rule rendered as a box-drawing line


def test_code_fence_body_preserved_fences_dropped():
    out = render_answer("```\ns125 verbatim\n```")
    plain = _plain(out)
    assert "s125 verbatim" in plain
    assert "```" not in plain


def test_inline_code():
    out = inline("call `retrieve()` first")
    assert "retrieve()" in _plain(out)


def test_empty_and_whitespace():
    assert render_answer("") == ""
    assert render_answer("   \n  \n") == ""
