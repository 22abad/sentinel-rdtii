"""The RLVR lab pane, driven through Textual's Pilot.

Runs headless against a dead API port, like test_leader_key: the loader catches
httpx.HTTPError so an offline start is clean. `_load_rlvr` is a Textual worker,
so tests that need populated state call it directly with a stubbed client rather
than racing the worker.

What matters here is the wiring rather than the layout (rlvr_render owns that):
the pane mounts, it is reachable by key, it does NOT fetch until visited, and a
missing report reads as a normal empty state instead of an error.
"""

from __future__ import annotations

import asyncio

import httpx

from stn_cli import tui as tui_mod


def _app() -> tui_mod.SentinelTUI:
    return tui_mod.SentinelTUI(api="http://127.0.0.1:9", token="")


_REPORT = {
    "generated_at": "2026-08-01T00:40:00+00:00",
    "commit": "c7d2ce9" + "0" * 33,
    "mode": "synthetic-distractors+llm-eligibility",
    "llm_provider": "deepseek",
    "case_set_sha256": "4" * 64,
    "summary": {
        "hygiene_top1_rate": 0.9375,
        "full_top1_rate": 0.9375,
        "mean_reference_proxy": 0.8676,
        "candidate_sets": 16,
        "cases_skipped": 0,
        "total_pairs": 69,
    },
    "by_kind": {"page_dump": {"class": "hygiene", "pairs": 14, "win_rate": 0.9286}},
    "component_analysis": {},
    "reward_config": {},
    "cases": [
        {
            "case_id": "sgp-cpc-7-5-section-20",
            "country_code": "SGP",
            "indicator_id": "7.5",
            "hygiene_top1": False,
            "full_top1": False,
            "candidates": [
                {"kind": "reference", "is_reference": True, "proxy_total": 0.8333,
                 "proxy_gates_passed": True, "proxy": {"components": {}}}
            ],
            "pairs": [{"kind": "page_dump", "reference_wins": False, "delta": -0.0417}],
        }
    ],
}


_LIVE = {
    "runs": [{
        "run_id": "20260801T012511-1c07a227", "provider": "deepseek",
        "model": "deepseek-v4-flash", "records": 2, "documents": 1,
        "mean_proxy": 0.7, "gate_failures": 1, "indicators": ["6.4", "7.3"],
        "last_at": "2026-08-01T01:25:12+00:00",
    }],
    "records": [
        {"run_id": "20260801T012511-1c07a227", "provider": "deepseek",
         "model": "deepseek-v4-flash", "document_id": "884e2c79fc784faa",
         "chunk_index": 2, "indicator_id": "6.4", "quote_hash": "cb4b" + "0" * 60,
         "logged_at": "2026-08-01T01:25:12+00:00",
         "candidate": {"verbatim_quote": "An organisation must not transfer personal data",
                       "article_clause": "Section 26"},
         "proxy": {"total": 0.7636, "passed_gates": True, "components": {
             "citation_exactness": {"value": 1.0, "weight": 3.0, "detail": "strict substring"}}}},
        {"run_id": "20260801T012511-1c07a227", "provider": "deepseek",
         "model": "deepseek-v4-flash", "document_id": "884e2c79fc784faa",
         "chunk_index": 5, "indicator_id": "7.3", "quote_hash": "ffff" + "0" * 60,
         "logged_at": "2026-08-01T01:25:13+00:00",
         "candidate": {"verbatim_quote": "Records shall be retained"},
         "proxy": {"total": 0.0, "passed_gates": False,
                   "failed_gates": ["quote_not_a_page_dump"], "components": {}}},
    ],
    "total": 2, "matched": 2, "returned": 2,
    "path": "/repo/evaluation/trajectories/trajectory.jsonl",
    "note": "Live extraction candidates (k=1, greedy). Not the golden-set measurement.",
}


class _StubClient:
    """Minimal async-context httpx stand-in for the two endpoints used."""

    def __init__(self, report=_REPORT, status=200, live_status=200):
        self._report = report
        self._status = status
        self._live_status = live_status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        if url.endswith("/history"):
            return httpx.Response(
                200,
                json={"runs": [{"generated_at": "2026-07-31T23:10:36",
                                "hygiene_top1_rate": 0.8125}]},
                request=httpx.Request("GET", url),
            )
        if url.endswith("/trajectories"):
            return httpx.Response(
                self._live_status,
                json=_LIVE if self._live_status == 200 else {"detail": "nothing logged yet"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            self._status,
            json=self._report if self._status == 200 else {"detail": "no report yet"},
            request=httpx.Request("GET", url),
        )


def test_pane_exists_and_is_reachable_by_key():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            app.set_focus(None)
            await pilot.press("5")
            await pilot.pause()
            assert app.query_one("#switcher").current == "rlvr"
            assert app.query_one("#rlvr-cases") is not None

    asyncio.run(scenario())


def test_pane_is_listed_in_the_sidebar():
    assert ("rlvr", "RLVR lab") in tui_mod.PANES


def test_no_fetch_until_the_pane_is_visited(monkeypatch):
    """A debug view most sessions never open must not cost a request at startup.

    Spies on the loader rather than the HTTP client: patching `_client` would
    also capture the docs/status workers that run on mount, which is a different
    claim than the one under test.
    """
    calls: list = []

    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            def _fake_load():
                calls.append(1)
                app._rlvr_report = _REPORT  # a real load populates this

            monkeypatch.setattr(app, "_load_rlvr", _fake_load)
            await pilot.pause()
            assert calls == [], "startup must not touch the measurement endpoint"

            app.action_pane("rlvr")
            await pilot.pause()
            assert calls == [1], "first visit loads it"

            app.action_pane("docs")
            app.action_pane("rlvr")
            await pilot.pause()
            assert calls == [1], "re-visiting an already-loaded lab must not refetch"

    asyncio.run(scenario())


def test_report_populates_summary_and_case_rows(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            await pilot.pause()

            assert app._rlvr_report["commit"].startswith("c7d2ce9")
            assert len(app._rlvr_cases) == 1
            table = app.query_one("#rlvr-cases")
            assert table.row_count == 1
            body = str(app.query_one("#rlvr-summary").render())
            assert "93.75%" in body
            assert "deepseek" in body  # billed run is visibly marked

    asyncio.run(scenario())


def test_missing_report_is_an_empty_state_not_an_error(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient(status=404))
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            await pilot.pause()

            body = str(app.query_one("#rlvr-summary").render())
            assert "No measurement report yet" in body
            assert app._rlvr_cases == []

    asyncio.run(scenario())


def test_unreachable_backend_reports_rather_than_crashing():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            await pilot.pause()
            body = str(app.query_one("#rlvr-summary").render())
            assert "unreachable" in body

    asyncio.run(scenario())


def test_selecting_a_case_opens_the_drill_down(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            await pilot.pause()

            table = app.query_one("#rlvr-cases")
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui_mod.RlvrDetailScreen)
            assert "sgp-cpc-7-5-section-20" in str(
                app.screen.query_one("#rlvr-detail").render()
            )

    asyncio.run(scenario())


def test_detail_key_needs_a_loaded_report(monkeypatch):
    """`d` on an empty lab warns instead of opening a blank modal."""
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            app.action_pane("rlvr")
            await pilot.pause()
            app.action_rlvr_sections()
            await pilot.pause()
            assert not isinstance(app.screen, tui_mod.RlvrDetailScreen)

    asyncio.run(scenario())


def test_detail_key_is_ignored_outside_the_lab(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            app.action_pane("docs")
            await pilot.pause()
            app.action_rlvr_sections()
            await pilot.pause()
            assert not isinstance(app.screen, tui_mod.RlvrDetailScreen)

    asyncio.run(scenario())


def test_detail_screen_shows_every_section(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            await pilot.pause()
            app.action_rlvr_sections()
            await pilot.pause()

            assert isinstance(app.screen, tui_mod.RlvrDetailScreen)
            body = str(app.screen.query_one("#rlvr-detail").render())
            assert "Per distractor type" in body
            assert "Run history" in body

    asyncio.run(scenario())


# ── live runs view (the trajectory log) ──────────────────────────────────


def test_toggle_switches_to_live_runs(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            assert app._rlvr_view == "study"

            app.action_rlvr_toggle()
            await app._load_rlvr_live().wait()
            await pilot.pause()

            assert app._rlvr_view == "runs"
            assert len(app._rlvr_records) == 2
            body = str(app.query_one("#rlvr-summary").render())
            assert "live extraction candidates" in body
            assert "deepseek" in body

    asyncio.run(scenario())


def test_live_view_never_shows_a_golden_top1_rate(monkeypatch):
    """The two artifacts must stay distinguishable.

    Live candidates are a single greedy draw with no answer key; showing the
    study's 93.75% beside them would read as if they had been scored against one.
    """
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            app.action_rlvr_toggle()
            await app._load_rlvr_live().wait()
            await pilot.pause()

            body = str(app.query_one("#rlvr-summary").render())
            assert "93.75%" not in body
            assert "Hygiene top-1" not in body

    asyncio.run(scenario())


def test_toggle_rebuilds_the_columns(monkeypatch):
    """Both views share one table; stale headers would mislabel every cell."""
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            await pilot.pause()
            table = app.query_one("#rlvr-cases")
            study_cols = [str(c.label) for c in table.columns.values()]
            assert "Case" in study_cols

            app.action_rlvr_toggle()
            await app._load_rlvr_live().wait()
            await pilot.pause()
            live_cols = [str(c.label) for c in table.columns.values()]
            assert "Quote" in live_cols
            assert "Case" not in live_cols

    asyncio.run(scenario())


def test_toggle_back_restores_the_study(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            app.action_rlvr_toggle()
            await app._load_rlvr_live().wait()
            app.action_rlvr_toggle()
            await pilot.pause()

            assert app._rlvr_view == "study"
            body = str(app.query_one("#rlvr-summary").render())
            assert "93.75%" in body

    asyncio.run(scenario())


def test_selecting_a_live_candidate_opens_its_drill_down(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient())
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            app.action_rlvr_toggle()
            await app._load_rlvr_live().wait()
            await pilot.pause()

            table = app.query_one("#rlvr-cases")
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui_mod.RlvrDetailScreen)
            body = str(app.screen.query_one("#rlvr-detail").render())
            assert "quote_hash" in body  # the join key is visible for debugging

    asyncio.run(scenario())


def test_empty_trajectory_log_is_an_empty_state(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "_client", lambda **kw: _StubClient(live_status=404))
            app.action_pane("rlvr")
            await app._load_rlvr().wait()
            app.action_rlvr_toggle()
            await app._load_rlvr_live().wait()
            await pilot.pause()

            body = str(app.query_one("#rlvr-summary").render())
            assert "No extraction candidates logged yet" in body
            assert app._rlvr_records == []

    asyncio.run(scenario())


def test_toggle_is_ignored_outside_the_lab(monkeypatch):
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            app.action_pane("docs")
            await pilot.pause()
            app.action_rlvr_toggle()
            assert app._rlvr_view == "study"

    asyncio.run(scenario())
