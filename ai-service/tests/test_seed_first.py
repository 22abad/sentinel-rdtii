"""Tests for the seed-first hybrid retrieval path.

``run_seed_first`` composes two existing passes: the reproducible local-library
seed (``run_library``) followed by live ``discover_and_extract`` as a fallback.
The contract we lock in here:

    * seed rows are kept as-is and come first,
    * a discovery row whose source URL a seed already covered is dropped
      (canonical-URL comparison, so trailing-slash / tracking-param variants
      still collide), and
    * the merged meta reports how the two passes contributed.

A real crawl/LLM is out of scope for a unit test, so both underlying passes are
monkeypatched to return canned (rows, meta). ``run_seed_first`` only reads
``row.source_url``, so lightweight stand-ins suffice.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from submission import pipeline


def _row(url: str) -> SimpleNamespace:
    return SimpleNamespace(source_url=url)


@pytest.mark.anyio
async def test_seed_first_drops_discovery_rows_already_covered_by_a_seed(monkeypatch):
    seed_rows = [_row("https://sso.agc.gov.sg/Act/PDPA2012")]

    async def fake_run_library(economy, pillar, **kwargs):
        return seed_rows, {
            "provider": "fake", "laws_available": 1,
            "documents_processed": 1, "warnings": ["seed-warn"],
        }

    # Same law as the seed (trailing slash — must still be treated as covered)
    # plus a genuinely new discovery URL that should survive.
    disc_rows = [
        _row("https://sso.agc.gov.sg/Act/PDPA2012/"),
        _row("https://sso.agc.gov.sg/SL/PDPA2012-S63-2021"),
    ]

    async def fake_discover(economy, pillar, **kwargs):
        return disc_rows, {
            "provider": "fake", "candidates_found": 5,
            "documents_processed": 2, "warnings": ["disc-warn"],
        }

    monkeypatch.setattr(pipeline, "run_library", fake_run_library)
    monkeypatch.setattr(pipeline, "discover_and_extract", fake_discover)

    rows, meta = await pipeline.run_seed_first("Singapore", 6)

    # Seed first, then only the fresh discovery URL.
    assert [r.source_url for r in rows] == [
        "https://sso.agc.gov.sg/Act/PDPA2012",
        "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021",
    ]
    assert meta["retrieval_strategy"] == "seed_first"
    assert meta["seed_provisions"] == 1
    assert meta["discovery_provisions"] == 1
    assert meta["discovery_duplicates_dropped"] == 1
    assert meta["provisions_mapped"] == 2
    assert meta["documents_processed"] == 3  # 1 seed + 2 discovery
    # Warnings from both passes are preserved.
    assert meta["warnings"] == ["seed-warn", "disc-warn"]


@pytest.mark.anyio
async def test_seed_first_with_no_seed_falls_back_to_pure_discovery(monkeypatch):
    async def empty_library(economy, pillar, **kwargs):
        return [], {"provider": "fake", "laws_available": 0,
                    "documents_processed": 0, "warnings": []}

    disc_rows = [_row("https://example.gov/a"), _row("https://example.gov/b")]

    async def fake_discover(economy, pillar, **kwargs):
        return disc_rows, {"provider": "fake", "candidates_found": 2,
                           "documents_processed": 2, "warnings": []}

    monkeypatch.setattr(pipeline, "run_library", empty_library)
    monkeypatch.setattr(pipeline, "discover_and_extract", fake_discover)

    rows, meta = await pipeline.run_seed_first("Malaysia", 7)

    assert [r.source_url for r in rows] == ["https://example.gov/a", "https://example.gov/b"]
    assert meta["seed_provisions"] == 0
    assert meta["discovery_provisions"] == 2
    assert meta["discovery_duplicates_dropped"] == 0
