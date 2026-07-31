"""The reject -> prompt feedback loop, end to end.

This loop was designed but severed in three independent places, all of which
failed silently:

  1. ``api/review.py`` inserted into ``audit_trail`` WITHOUT ``reviewer_notes``.
  2. ``providers/base._get_recent_corrections`` required that same column to be
     non-empty, so it could never match a row.
  3. That reader hardcoded ``host=postgres, port=5432``, ignoring
     ``DATABASE_URL`` — from the host it could not even resolve, and a bare
     ``except: return ""`` hid it.

Each test below pins one of those breaks. They are cheap and DB-free; the point
is that a regression in any one of them silently disables human feedback again.
"""

from __future__ import annotations

import logging
import sys
import types

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────


class _RecordingCursor:
    """Captures SQL + params, replays a canned result set."""

    def __init__(self, rows, sink):
        self._rows = rows
        self._sink = sink

    def execute(self, sql, params=None):
        self._sink.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return ("00000000-0000-0000-0000-000000000000",)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _RecordingConn:
    def __init__(self, rows, sink):
        self._rows = rows
        self._sink = sink

    def cursor(self):
        return _RecordingCursor(self._rows, self._sink)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_psycopg2(rows, sink, connect_calls=None, boom=None):
    """A stand-in psycopg2 module, injected via sys.modules.

    ``_get_recent_corrections`` imports psycopg2 *inside* its try block (so the
    DB-free judge CLI keeps working), which means patching sys.modules is the
    only seam available.
    """

    mod = types.ModuleType("psycopg2")

    def connect(*args, **kwargs):
        if connect_calls is not None:
            connect_calls.append((args, kwargs))
        if boom is not None:
            raise boom
        return _RecordingConn(rows, sink)

    mod.connect = connect  # type: ignore[attr-defined]
    return mod


@pytest.fixture
def corrections_env(monkeypatch):
    """Isolate the DB env vars these tests assert on."""
    for var in (
        "DATABASE_URL", "POSTGRES_DB", "POSTGRES_USER",
        "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT",
    ):
        monkeypatch.delenv(var, raising=False)


# ── break #2: a rejection is the signal; the note is optional ────────────────


def test_rejection_without_notes_still_becomes_a_correction(monkeypatch, corrections_env):
    """The regression that made the whole loop dead code.

    No UI collects reviewer notes, so if an empty note disqualifies a row, every
    row is disqualified and the loop is permanently silent.
    """
    from providers.base import LLMProvider

    sink: list = []
    rows = [("Companies Act s125 requires records be kept.", None)]
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(rows, sink))

    out = LLMProvider._get_recent_corrections()

    assert "RECENT HUMAN AUDITOR CORRECTIONS" in out
    assert "Companies Act s125" in out
    # No note supplied -> no empty "Human Feedback" line dangling in the prompt.
    assert "Human Feedback" not in out
    assert "Do NOT extract or map this type of content" in out


def test_query_does_not_filter_on_reviewer_notes(monkeypatch, corrections_env):
    from providers.base import LLMProvider

    sink: list = []
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2([], sink))

    LLMProvider._get_recent_corrections()

    assert len(sink) == 1
    sql, _ = sink[0]
    assert "reviewer_notes IS NOT NULL" not in sql, (
        "requiring a note re-severs the loop — nothing writes one"
    )
    assert "compliance_status = 'non-compliant'" in sql


def test_note_is_included_when_a_reviewer_supplied_one(monkeypatch, corrections_env):
    from providers.base import LLMProvider

    sink: list = []
    rows = [("MAS Guidelines on outsourcing.", "  Not quite related to 7.3, remove.  ")]
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(rows, sink))

    out = LLMProvider._get_recent_corrections()

    assert 'Human Feedback: "Not quite related to 7.3, remove."' in out


def test_no_rejections_yields_empty_string(monkeypatch, corrections_env):
    from providers.base import LLMProvider

    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2([], []))
    assert LLMProvider._get_recent_corrections() == ""


# ── break #3: connect where the writer actually wrote ────────────────────────


def test_database_url_is_preferred_over_postgres_vars(monkeypatch, corrections_env):
    """The writer uses auth._db_connect (DATABASE_URL first). The reader must agree."""
    from providers.base import LLMProvider

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5433/rdtii")
    calls: list = []
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2([], [], connect_calls=calls))

    LLMProvider._get_recent_corrections()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "postgresql://u:p@localhost:5433/rdtii"
    assert "host" not in kwargs


def test_fallback_host_is_not_the_docker_internal_name(monkeypatch, corrections_env):
    """host=postgres:5432 is unreachable from the host; auth falls back to localhost:5433."""
    from providers.base import LLMProvider

    calls: list = []
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2([], [], connect_calls=calls))

    LLMProvider._get_recent_corrections()

    _, kwargs = calls[0]
    assert kwargs["host"] == "localhost"
    assert str(kwargs["port"]) == "5433"


# ── the silence that hid all of it ───────────────────────────────────────────


def test_db_failure_is_logged_loudly_not_swallowed(monkeypatch, caplog, corrections_env):
    from providers.base import LLMProvider

    monkeypatch.setitem(
        sys.modules, "psycopg2",
        _fake_psycopg2([], [], boom=RuntimeError("could not translate host name")),
    )

    with caplog.at_level(logging.WARNING, logger="providers.base"):
        assert LLMProvider._get_recent_corrections() == ""

    assert any(
        "NOT contributing" in r.getMessage() for r in caplog.records
    ), "a dead feedback loop must announce itself, not return '' like a healthy one"


def test_missing_psycopg2_still_degrades_quietly_enough_to_run(monkeypatch, corrections_env):
    """The judge CLI ships no psycopg2 — extraction must survive, not crash."""
    from providers.base import LLMProvider

    monkeypatch.setitem(sys.modules, "psycopg2", None)  # import -> ImportError
    assert LLMProvider._get_recent_corrections() == ""


# ── break #1: the writer must persist the column the reader reads ────────────


def test_review_endpoint_persists_reviewer_notes():
    from schemas import IndicatorMapping, ReviewRequest
    import api.review as review

    sink: list = []
    mapping = IndicatorMapping(
        pillar=7,
        indicator="7.3",
        score=0.0,
        verbatim_quote="Records shall be retained as long as necessary.",
        quote_start=0,
        quote_end=46,
        source_legislation="Companies Act",
        source_url="https://example.gov/companies-act",
    )
    req = ReviewRequest(
        decision="rejected",
        country_code="SGP",
        mapping=mapping,
        reviewer_notes="s125 did not mention the minimum 7 years.",
    )

    original = review._db_connect
    review._db_connect = lambda: _RecordingConn([], sink)  # type: ignore[assignment]
    try:
        review.review_mapping(req)
    finally:
        review._db_connect = original  # type: ignore[assignment]

    audit = [(sql, params) for sql, params in sink if "INSERT INTO audit_trail" in sql]
    assert len(audit) == 1, "review must write exactly one audit_trail row"
    sql, params = audit[0]
    assert "reviewer_notes" in sql, (
        "omitting this column is what made _get_recent_corrections dead code"
    )
    assert "s125 did not mention the minimum 7 years." in params


def test_blank_reviewer_notes_persist_as_null_not_empty_string():
    """So the column stays honest: absent means NULL, not ''."""
    from schemas import IndicatorMapping, ReviewRequest
    import api.review as review

    sink: list = []
    mapping = IndicatorMapping(
        pillar=6,
        indicator="6.2",
        score=1.0,
        verbatim_quote="Data shall be stored within the territory.",
        quote_start=0,
        quote_end=42,
        source_legislation="ITA",
        source_url="https://example.gov/ita",
    )
    req = ReviewRequest(
        decision="rejected", country_code="MYS", mapping=mapping, reviewer_notes="   ",
    )

    original = review._db_connect
    review._db_connect = lambda: _RecordingConn([], sink)  # type: ignore[assignment]
    try:
        review.review_mapping(req)
    finally:
        review._db_connect = original  # type: ignore[assignment]

    sql, params = next((s, p) for s, p in sink if "INSERT INTO audit_trail" in s)
    assert params[-1] is None
