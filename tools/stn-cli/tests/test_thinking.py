"""Tests for the TUI thinking animation (stn_cli.tui.thinking_meta).

The animation is a widget timer feeding a pure formatter; these pin the
formatter — frame cycling, phase progression, verb pinning, and the elapsed
tail — so the timer wiring stays a thin shell.
"""

from __future__ import annotations

from rich.text import Text

from stn_cli.tui import _SPINNER_FRAMES, _THINK_PHASES, thinking_meta


def _plain(markup: str) -> str:
    return Text.from_markup(markup).plain


def test_spinner_cycles_frames():
    frames = {_plain(thinking_meta(i, 0.0))[0] for i in range(len(_SPINNER_FRAMES))}
    assert frames == set(_SPINNER_FRAMES)
    # Wraps around rather than running off the end.
    assert thinking_meta(0, 0.0) == thinking_meta(len(_SPINNER_FRAMES), 0.0)


def test_phase_progression_with_elapsed():
    assert "thinking…" in thinking_meta(0, 0.0)
    assert "retrieving…" in thinking_meta(0, 3.5)
    assert "reranking…" in thinking_meta(0, 6.1)
    assert "drafting…" in thinking_meta(0, 9.2)
    # Holds on the last phase, never IndexErrors on long waits.
    assert "drafting…" in thinking_meta(0, 300.0)


def test_pinned_verb_overrides_phases():
    out = thinking_meta(3, 42.0, verb="ingesting law.pdf")
    assert "ingesting law.pdf…" in out
    for phase in _THINK_PHASES:
        assert phase not in out


def test_elapsed_tail_only_after_first_phase():
    assert "s[/]" not in thinking_meta(0, 1.0)  # early: no counter noise
    assert "· 7s" in thinking_meta(0, 7.4)


def test_meta_is_dim_markup():
    out = thinking_meta(1, 5.0)
    assert out.startswith("[dim]")
    assert out.endswith("[/]")
    # Valid Rich markup end-to-end.
    Text.from_markup(out)
