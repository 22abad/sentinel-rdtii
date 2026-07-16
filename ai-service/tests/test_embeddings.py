"""Tests for the pluggable embedding backend."""

from __future__ import annotations

import math

import pytest

import services.embeddings as emb


def test_default_provider_is_local(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert emb.active_provider() == "local"
    # an unknown value also falls back to local (never crash on a typo)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "nope")
    assert emb.active_provider() == "local"


def test_provider_info_and_dim():
    assert emb.provider_info("local")["dim"] == 384
    assert emb.provider_info("gemini")["dim"] == 768
    assert emb.provider_info("local")["needs_key"] is False
    assert emb.provider_info("gemini")["offline"] is False


def test_local_embed_shape_and_normalisation():
    pytest.importorskip("sentence_transformers")  # docker/CI has it; eval venv may not
    vecs = emb.embed(["cross-border transfer of personal data", "data retention period"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 384
    # L2-normalised → unit length
    assert math.isclose(math.sqrt(sum(x * x for x in vecs[0])), 1.0, rel_tol=1e-4)


def test_empty_input_returns_empty():
    assert emb.embed([]) == []


def test_gemini_without_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Force the gemini path; whether the SDK is installed or not, it must raise a
    # descriptive RuntimeError (missing package OR missing key) — never a silent
    # or half-embedded result.
    with pytest.raises(RuntimeError) as e:
        emb.embed(["x"], provider="gemini")
    assert "gemini" in str(e.value).lower() or "GOOGLE_API_KEY" in str(e.value)


def test_gemini_batches_through_sdk(monkeypatch):
    """When the SDK + key are present, embed() routes each text through it."""
    calls = []

    class FakeGenAI:
        def configure(self, api_key=None):
            calls.append(("configure", api_key))

        def embed_content(self, model=None, content=None, task_type=None):
            calls.append(("embed", content))
            return {"embedding": [0.3, 0.4]}  # not unit-length → we check normalisation

    fake = FakeGenAI()
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setitem(__import__("sys").modules, "google.generativeai", fake)
    monkeypatch.setitem(__import__("sys").modules, "google", type("g", (), {"generativeai": fake}))

    vecs = emb.embed(["a", "b"], provider="gemini")
    assert len(vecs) == 2
    # [0.3,0.4] normalised → [0.6,0.8]
    assert math.isclose(vecs[0][0], 0.6, rel_tol=1e-3)
    assert math.isclose(vecs[0][1], 0.8, rel_tol=1e-3)
    assert ("configure", "test-key") in calls
