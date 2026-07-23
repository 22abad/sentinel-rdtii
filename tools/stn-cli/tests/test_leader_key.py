"""Integration tests for the LazyVim-style leader key, via Textual's Pilot.

The app runs headless against a dead API port (both load workers catch
httpx.HTTPError, so startup is clean offline). THEME_CONFIG is patched on the
module — on_key reads it dynamically, so no re-import is needed.
"""

from __future__ import annotations

import asyncio

from stn_cli import tui as tui_mod


def _leader_app(monkeypatch, leader: str = "space") -> tui_mod.SentinelTUI:
    monkeypatch.setattr(tui_mod.THEME_CONFIG, "leader", leader)
    monkeypatch.setattr(tui_mod.THEME_CONFIG, "leader_timeout", 5.0)
    monkeypatch.setattr(
        tui_mod.THEME_CONFIG, "key_map", {"d": "pane('docs')", "e": "pane('extract')"}
    )
    return tui_mod.SentinelTUI(api="http://127.0.0.1:9", token="")


def test_leader_sequence_runs_action(monkeypatch):
    async def scenario():
        app = _leader_app(monkeypatch)
        async with app.run_test() as pilot:
            # Chat input grabs focus on start — blur to leave "insert mode".
            app.set_focus(None)
            await pilot.press("space")
            assert app._leader_pending is True
            assert app.query("#leader-popup")  # which-key popup visible
            # flash.nvim-style jump label on the mapped sidebar pane
            nav = app.query_one("#nav-extract Label")
            assert " e " in str(nav.render())
            await pilot.press("e")
            await pilot.pause()
            assert app._leader_pending is False
            assert not app.query("#leader-popup")
            # jump label restored after dispatch
            assert " e " not in str(nav.render())
            assert app.query_one("#switcher").current == "extract"

    asyncio.run(scenario())


def test_unmapped_followup_just_clears(monkeypatch):
    async def scenario():
        app = _leader_app(monkeypatch)
        async with app.run_test() as pilot:
            app.set_focus(None)
            before = app.query_one("#switcher").current
            await pilot.press("space", "z")
            await pilot.pause()
            assert app._leader_pending is False
            assert app.query_one("#switcher").current == before

    asyncio.run(scenario())


def test_leader_never_fires_in_inputs(monkeypatch):
    async def scenario():
        app = _leader_app(monkeypatch)
        async with app.run_test() as pilot:
            app.action_pane("rag")
            await pilot.pause()
            rag_input = app.query_one("#rag-input")
            rag_input.focus()
            await pilot.press("space", "d")
            await pilot.pause()
            # Insert mode: the leader typed a real space, no pane switch.
            assert app._leader_pending is False
            assert rag_input.value == " d"
            assert app.query_one("#switcher").current == "rag"

    asyncio.run(scenario())


def test_leader_disabled_by_default(monkeypatch):
    async def scenario():
        monkeypatch.setattr(tui_mod.THEME_CONFIG, "leader", "")
        app = tui_mod.SentinelTUI(api="http://127.0.0.1:9", token="")
        async with app.run_test() as pilot:
            app.set_focus(None)
            await pilot.press("space")
            assert app._leader_pending is False

    asyncio.run(scenario())
