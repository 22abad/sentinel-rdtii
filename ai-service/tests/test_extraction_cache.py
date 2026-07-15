"""Tests for the extraction cache — never run the LLM twice on the same content.

No live database required: the DB layer is monkeypatched, so these prove the
cache logic and the extract node's reuse/skip behaviour in isolation.
"""

from __future__ import annotations

import asyncio

import services.extraction_cache as ec
from workflows.nodes.extract import ExtractMappingsExecutor
from workflows.schemas import WorkflowContext, WorkflowNode

_TEXT = "An organisation must not transfer personal data outside Singapore unless ..."
_RESPONSE = {
    "mappings": [{"pillar": 6, "indicator": "6.4", "score": 1.0, "verbatim_quote": "must not transfer"}],
    "rejected": [],
    "provider": "deepseek",
}


def test_source_hash_is_stable_and_whitespace_normalised():
    # Trailing whitespace / blank-line differences hash to the same fingerprint.
    a = ec.source_hash("line one\nline two")
    assert isinstance(a, str) and len(a) == 64
    # Leading/trailing whitespace and trailing blank lines are normalised away.
    assert ec.source_hash("  line one\nline two  \n\n") == a
    # But a leading space *inside* a line is content — it must change the hash.
    assert ec.source_hash("line one\n line two") != a


def test_get_and_put_are_noops_without_database(monkeypatch):
    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr(ec, "_db_connect", boom)
    # Both degrade gracefully: miss returns None, write returns False. No raise.
    assert ec.get_cached(_TEXT) is None
    assert ec.put_cached(_TEXT, _RESPONSE) is False


def test_empty_text_never_hits_the_database(monkeypatch):
    called = {"n": 0}

    def spy():
        called["n"] += 1
        raise AssertionError("should not connect for empty text")

    monkeypatch.setattr(ec, "_db_connect", spy)
    assert ec.get_cached("   ") is None
    assert ec.put_cached("", _RESPONSE) is False
    assert called["n"] == 0


def test_node_reuses_cache_and_skips_the_llm(monkeypatch):
    """On a cache hit the extract node returns the cached mappings and never
    calls run_extraction (the LLM). This is the 'don't redo work' guarantee."""
    import workflows.nodes.extract as node_mod

    monkeypatch.setattr(node_mod, "_cache_get", lambda text: dict(_RESPONSE))

    async def forbidden_extraction(*args, **kwargs):
        raise AssertionError("run_extraction must not be called on a cache hit")

    monkeypatch.setattr(node_mod, "run_extraction", forbidden_extraction)
    logged: list = []
    monkeypatch.setattr(node_mod, "_log_reuse", lambda text, cached: logged.append(cached))

    node = WorkflowNode(id="n1", type="extract.mappings", config={"text": _TEXT})
    ctx = WorkflowContext(run_id="r1", runtime={})
    result = asyncio.run(ExtractMappingsExecutor().run(node=node, inputs={"text": _TEXT}, context=ctx))

    assert result.status == "success"
    assert result.outputs.get("reused") is True
    assert result.outputs["mappings"][0]["indicator"] == "6.4"
    assert logged, "a reuse hit should be logged"


def test_node_extracts_then_caches_on_miss(monkeypatch):
    """On a cache miss the node runs extraction and writes the result to the
    cache so the next identical run can reuse it."""
    import workflows.nodes.extract as node_mod

    class _Resp:
        def model_dump(self):
            return dict(_RESPONSE)

    class _Provider:
        name = "deepseek"

    monkeypatch.setattr(node_mod, "_cache_get", lambda text: None)
    monkeypatch.setattr(node_mod, "configured_provider", lambda *a, **k: _Provider())

    async def fake_extraction(text, provider, **kwargs):
        return _Resp()

    monkeypatch.setattr(node_mod, "run_extraction", fake_extraction)
    written: list = []
    monkeypatch.setattr(node_mod, "_cache_put", lambda text, outputs, provider=None: written.append((text, provider)))

    node = WorkflowNode(id="n1", type="extract.mappings", config={"text": _TEXT})
    ctx = WorkflowContext(run_id="r1", runtime={})
    result = asyncio.run(ExtractMappingsExecutor().run(node=node, inputs={"text": _TEXT}, context=ctx))

    assert result.status == "success"
    assert "reused" not in result.outputs  # a fresh extraction is not tagged reused
    assert written and written[0][1] == "deepseek", "the fresh extraction should be cached"
