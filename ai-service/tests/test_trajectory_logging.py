"""Trajectory logging: the write-only half of the review loop.

Three properties matter, in this order:

1. **It never breaks an extraction.** This is a logging side-channel bolted onto
   the pipeline. A bad path, a missing module, an unserialisable value — all of
   them must cost a log line, never a row of output.
2. **The join key matches the review side.** ``quote_hash`` uses the same
   function ``verified_evidence`` stores, so a researcher's approve/reject can
   be reunited with the candidate it judged. If these ever drift, the loop is
   silently open and nothing tells you.
3. **It changes no output.** A run with logging on must return byte-identical
   mappings to a run with it off.
"""

from __future__ import annotations

import json

from rlvr.trajectory import SCHEMA_VERSION, TrajectoryWriter
from submission.novelty import normalized_quote_hash

_QUOTE = (
    "An organisation must not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with requirements "
    "prescribed under this Act."
)


def _writer(tmp_path, **kw):
    return TrajectoryWriter(
        path=tmp_path / "traj.jsonl", run_id="test-run", provider="p", model="m", **kw
    )


def _log(writer, quote=_QUOTE, **overrides):
    payload = {
        "document_id": "doc-1",
        "chunk_index": 2,
        "indicator_id": "6.4",
        "sampling": {"temperature": 0, "k": 1},
        "candidate": {"verbatim_quote": quote, "article_clause": "Section 26"},
        "proxy": {"total": 0.76, "components": {}},
        "selected": True,
    }
    payload.update(overrides)
    writer.log_candidate(**payload)


def _rows(tmp_path):
    return [
        json.loads(line)
        for line in (tmp_path / "traj.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]


# ── the join key ─────────────────────────────────────────────────────────


def test_quote_hash_equals_what_the_review_side_stores(tmp_path):
    """The whole loop hangs on this equality.

    verified_evidence.quote_hash is written by save_evidence via
    normalized_quote_hash. If the trajectory ever computes it differently, a
    verdict can never be joined to the candidate and nothing raises.
    """
    w = _writer(tmp_path)
    _log(w)
    assert _rows(tmp_path)[0]["quote_hash"] == normalized_quote_hash(_QUOTE)


def test_join_key_is_stable_under_whitespace_and_case(tmp_path):
    """A researcher re-typing or a re-fetch reflowing the text must still join."""
    w = _writer(tmp_path)
    _log(w, quote=_QUOTE)
    _log(w, quote="  " + _QUOTE.replace(" ", "   ").upper() + "\n")
    rows = _rows(tmp_path)
    assert rows[0]["quote_hash"] == rows[1]["quote_hash"]


def test_fingerprint_is_not_reused_as_the_join_key(tmp_path):
    """fingerprint is raw+truncated: 16 chars, whitespace-sensitive. Distinct field."""
    w = _writer(tmp_path)
    _log(w, fingerprint="deadbeefdeadbeef")
    row = _rows(tmp_path)[0]
    assert row["fingerprint"] == "deadbeefdeadbeef"
    assert len(row["quote_hash"]) == 64
    assert row["quote_hash"] != row["fingerprint"]


def test_schema_version_records_the_join_key_addition(tmp_path):
    w = _writer(tmp_path)
    _log(w)
    assert _rows(tmp_path)[0]["schema_version"] == SCHEMA_VERSION >= 2


def test_empty_quote_yields_empty_hash_not_a_hash_of_nothing(tmp_path):
    """An unjoinable record is honest; a hash of "" that collides is not."""
    w = _writer(tmp_path)
    _log(w, quote="")
    assert _rows(tmp_path)[0]["quote_hash"] == ""


# ── provenance ───────────────────────────────────────────────────────────


def test_record_carries_the_chunk_identity(tmp_path):
    w = _writer(tmp_path)
    _log(w)
    row = _rows(tmp_path)[0]
    assert row["document_id"] == "doc-1"
    assert row["chunk_index"] == 2
    assert row["indicator_id"] == "6.4"


def test_disabled_writer_writes_nothing(tmp_path):
    w = _writer(tmp_path, enabled=False)
    _log(w)
    assert not (tmp_path / "traj.jsonl").exists()
    assert w.records_written == 0


def test_appends_rather_than_truncating(tmp_path):
    w = _writer(tmp_path)
    _log(w)
    _log(w, indicator_id="7.3")
    assert len(_rows(tmp_path)) == 2
    assert w.records_written == 2


# ── the orchestrator seam: logging must never break a run ────────────────


def test_orchestrator_log_helper_swallows_a_broken_writer():
    """A writer that raises must not propagate into extraction."""
    from agents.orchestrator import MASOrchestrator
    from schemas import IndicatorMapping

    class _Boom:
        def log_candidate(self, **kw):
            raise RuntimeError("disk full")

    class _Provider:
        name = "fake"
        model_name = "fake-1"

    orch = MASOrchestrator.__new__(MASOrchestrator)  # skip __init__/agent wiring
    orch._trajectory = _Boom()

    mapping = IndicatorMapping(
        pillar=6, indicator="6.4", score=1.0,
        verbatim_quote=_QUOTE, quote_start=0, quote_end=len(_QUOTE),
        source_legislation="PDPA", source_url="https://example.gov/pdpa",
    )
    # Must return normally — the assertion is the absence of an exception.
    orch._log_trajectory(
        document_id="d", chunk_index=0, chunk_text=_QUOTE,
        indicator_id="6.4", mapping=mapping, raw_score=1.0,
    )


def test_orchestrator_log_helper_is_a_noop_when_disabled():
    from agents.orchestrator import MASOrchestrator
    from schemas import IndicatorMapping

    orch = MASOrchestrator.__new__(MASOrchestrator)
    orch._trajectory = None
    mapping = IndicatorMapping(
        pillar=6, indicator="6.4", score=1.0,
        verbatim_quote=_QUOTE, quote_start=0, quote_end=len(_QUOTE),
    )
    orch._log_trajectory(
        document_id="d", chunk_index=0, chunk_text=_QUOTE,
        indicator_id="6.4", mapping=mapping, raw_score=1.0,
    )


def test_writer_factory_respects_the_off_switch(monkeypatch):
    from agents.orchestrator import _make_trajectory_writer

    class _Provider:
        name = "fake"
        model_name = "fake-1"

    for value in ("off", "0", "false", "NO"):
        monkeypatch.setenv("RDTII_TRAJECTORY_LOG", value)
        assert _make_trajectory_writer(_Provider()) is None


def test_writer_factory_honours_an_explicit_path(monkeypatch, tmp_path):
    from agents.orchestrator import _make_trajectory_writer

    class _Provider:
        name = "deepseek"
        model_name = "deepseek-v4-flash"

    target = tmp_path / "custom" / "t.jsonl"
    monkeypatch.setenv("RDTII_TRAJECTORY_LOG", str(target))
    writer = _make_trajectory_writer(_Provider())
    assert writer is not None
    assert writer.path == target
    assert writer.provider == "deepseek"
    assert writer.model == "deepseek-v4-flash"


def test_writer_factory_is_on_by_default(monkeypatch):
    from agents.orchestrator import _make_trajectory_writer

    class _Provider:
        name = "fake"
        model_name = "fake-1"

    monkeypatch.delenv("RDTII_TRAJECTORY_LOG", raising=False)
    assert _make_trajectory_writer(_Provider()) is not None
