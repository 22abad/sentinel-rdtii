from __future__ import annotations

import providers
from providers.fallback import FallbackProvider


class _Fake:
    """Minimal provider stand-in that counts calls and can be made to fail."""

    def __init__(self, name, *, fail=False, answer="ok"):
        self.name = name
        self.fail = fail
        self.answer = answer
        self.calls = 0
        self.collector = None

    def query(self, prompt, system=""):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return f"{self.answer}:{prompt}"

    def extract_features(self, article_text, indicator_id, feature_spec):
        self.calls += 1
        if self.fail:
            raise ConnectionError(f"{self.name} unreachable")
        return {"provider": self.name, "indicator": indicator_id}

    def estimate_cost_usd(self, i, o):
        return 0.0

    def set_usage_collector(self, collector):
        self.collector = collector


def test_healthy_primary_never_touches_fallback():
    primary, fallback = _Fake("ollama"), _Fake("deepseek")
    fp = FallbackProvider(primary, fallback)
    assert fp.query("hi") == "ok:hi"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert fp.primary_dead is False


def test_failover_and_latch():
    primary = _Fake("ollama", fail=True)
    fallback = _Fake("deepseek", answer="ds")
    fp = FallbackProvider(primary, fallback)

    # First call: primary fails, fallback answers, wrapper latches.
    assert fp.query("a") == "ds:a"
    assert primary.calls == 1 and fallback.calls == 1
    assert fp.primary_dead is True

    # Second call: primary is not retried (latched to fallback).
    assert fp.extract_features("txt", "6.4", {}) == {"provider": "deepseek", "indicator": "6.4"}
    assert primary.calls == 1  # unchanged — not re-attempted
    assert fallback.calls == 2


def test_set_usage_collector_propagates_to_both():
    primary, fallback = _Fake("ollama"), _Fake("deepseek")
    fp = FallbackProvider(primary, fallback)
    fp.set_usage_collector("collector-token")
    assert primary.collector == "collector-token"
    assert fallback.collector == "collector-token"


def test_resolve_provider_no_fallback_env_returns_bare(monkeypatch):
    monkeypatch.setattr(providers, "get_provider", lambda name, model=None: _Fake(name))
    monkeypatch.delenv("RDTII_LLM_FALLBACK_PROVIDER", raising=False)
    monkeypatch.setenv("RDTII_LLM_PROVIDER", "ollama")
    prov = providers.resolve_provider()
    assert isinstance(prov, _Fake)  # not wrapped


def test_resolve_provider_wraps_when_distinct_fallback_configured(monkeypatch):
    monkeypatch.setattr(providers, "get_provider", lambda name, model=None: _Fake(name))
    monkeypatch.setenv("RDTII_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("RDTII_LLM_FALLBACK_PROVIDER", "deepseek")
    prov = providers.resolve_provider()
    assert isinstance(prov, FallbackProvider)
    assert prov.name == "ollama->deepseek"


def test_resolve_provider_same_primary_and_fallback_not_wrapped(monkeypatch):
    monkeypatch.setattr(providers, "get_provider", lambda name, model=None: _Fake(name))
    monkeypatch.setenv("RDTII_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("RDTII_LLM_FALLBACK_PROVIDER", "deepseek")
    prov = providers.resolve_provider()
    assert isinstance(prov, _Fake)  # identical -> no pointless wrap
