"""pytest configuration for the ai-service.

Adds the ai-service directory to sys.path so test files can do bare
imports like `from chunker import ...` without each test file having to
mutate sys.path itself. Equivalent to setting `pythonpath = ["."]` in
pytest config, but plays nicer with editors that don't read pytest.ini.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

_AI_SERVICE = Path(__file__).resolve().parent
if str(_AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(_AI_SERVICE))

os.environ["DISCOVERY_REGISTRY_BACKEND"] = "file"
# Don't let the search-engine per-host politeness delay slow the test suite.
os.environ.setdefault("DISCOVERY_SEARCH_MIN_INTERVAL", "0")
# Trajectory logging is ON by default in the pipeline, so a test run would
# append fixture candidates ("fake-provider", "fake-liar") to the same file real
# extractions write to. That file is the input to the review-join dataset — a
# reader cannot tell a fixture row from a real one, so the contamination is
# silent and permanent. Tests that exercise the writer set their own tmp path.
os.environ["RDTII_TRAJECTORY_LOG"] = "off"


@pytest.fixture(autouse=True)
def _disable_extraction_cache(monkeypatch):
    """Keep the extract node hermetic: never read/write the real extraction
    cache (a live DB) during tests. Without this, a stream/run test would write
    its content to the cache on the first run and then reuse it on the next,
    silently skipping the LLM path it means to exercise. Tests that specifically
    assert cache behaviour override these with their own monkeypatch (which
    wins, being applied inside the test body)."""
    try:
        import workflows.nodes.extract as extract_node

        monkeypatch.setattr(extract_node, "_cache_get", lambda text: None, raising=False)
        monkeypatch.setattr(extract_node, "_cache_put", lambda *a, **k: None, raising=False)
    except Exception:  # noqa: BLE001 — the module may not import in every test env
        pass
