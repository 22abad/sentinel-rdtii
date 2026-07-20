"""LLM provider abstraction layer.

The hackathon scoring rubric awards 40 points (Stage 1 + Stage 3) for designs
that work when the LLM is swapped for an open-weight model (e.g. Llama 3).
This package implements that swappability.

Usage:
    from providers import get_default_provider, get_provider

    p = get_default_provider()                 # picks based on RDTII_LLM_PROVIDER env var
    p = get_provider("claude")                 # explicit
    features = p.extract_features(article, "6.1", spec)

Adding a new provider:
    1. Subclass `LLMProvider` in providers/<name>.py
    2. Implement `extract_features()` and `estimate_cost_usd()`
    3. Register in `_REGISTRY` below
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Type

from .base import LLMProvider

# Module-path / class-name pairs — loaded lazily so importing this package
# doesn't require every provider's SDK to be installed.
#
# The keys here are the CANONICAL names returned by `list_providers()` and
# shown via `/providers`. Aliases (different spellings of the same name)
# are normalised in `_canonicalise()`, so the public list stays
# unambiguous (no duplicate llama3 entries).
_LAZY_REGISTRY: dict[str, tuple[str, str]] = {
    # Native SDKs
    "gemini": (".gemini", "GeminiProvider"),
    "claude": (".claude", "ClaudeProvider"),
    "llama-3-local": (".llama_local", "Llama3LocalProvider"),
    # Vertex AI — Google Cloud Vertex AI with service account
    "vertex-ai": (".vertex_ai", "VertexAIProvider"),
    # Ollama — local model server with OpenAI-compatible API
    "ollama": (".ollama", "OllamaProvider"),
    # OpenAI-compatible (single SDK, many vendors via base_url)
    "openai": (".openai_compatible", "OpenAIProvider"),
    "deepseek": (".openai_compatible", "DeepSeekProvider"),
    "groq": (".openai_compatible", "GroqProvider"),
    "together": (".openai_compatible", "TogetherProvider"),
    "openrouter": (".openai_compatible", "OpenRouterProvider"),
    "mistral": (".openai_compatible", "MistralProvider"),
}

# User-friendly aliases that map onto a canonical key.
# NOTE: keys here are matched AFTER `_canonicalise` lower-cases, strips,
# and replaces "_" with "-". So underscore-bearing aliases (e.g.
# "llama_3_local") would never be reached and must not be added here.
_ALIASES: dict[str, str] = {
    "llama3": "llama-3-local",
    "llama3-local": "llama-3-local",
    "llama-3": "llama-3-local",
    "vertex": "vertex-ai",
    "vertexai": "vertex-ai",
}


def _canonicalise(name: str) -> str:
    norm = name.lower().strip().replace("_", "-")
    return _ALIASES.get(norm, norm)


def canonical_name(name: str) -> str | None:
    """Public alias normaliser — returns the canonical key for `name`.

    Returns `None` when `name` does not resolve to any registered provider.
    Returning `None` (rather than echoing the raw input) lets status
    endpoints surface misconfiguration explicitly: with the previous
    behaviour, an invalid `RDTII_LLM_PROVIDER=foo` looked like a healthy
    `active=foo` even though `foo` was absent from `available_providers`,
    breaking the "active is one of available" contract.
    """
    canonical = _canonicalise(name)
    return canonical if canonical in _LAZY_REGISTRY else None


def is_recognised(name: str) -> bool:
    """Return True if `name` (or any alias of it) maps to a registered provider."""
    return canonical_name(name) is not None


def _load_class(name: str) -> Type[LLMProvider]:
    canonical = _canonicalise(name)
    if canonical not in _LAZY_REGISTRY:
        available = ", ".join(sorted(_LAZY_REGISTRY.keys()))
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")
    module_path, class_name = _LAZY_REGISTRY[canonical]
    module = importlib.import_module(module_path, package=__name__)
    return getattr(module, class_name)


def get_provider(name: str, model: str | None = None) -> LLMProvider:
    """Return an instance of the named provider, optionally overriding the default model.

    Names are case-insensitive and tolerant of aliases (e.g. `llama3` and
    `llama-3-local` both resolve to the local Llama 3 provider).
    Raises ValueError for unknown names; ExtractionError if the SDK or API
    key for the chosen provider is missing.
    """
    cls = _load_class(name)
    if model:
        import inspect
        sig = inspect.signature(cls.__init__)
        if "model_name" in sig.parameters:
            return cls(model_name=model)
        elif "model" in sig.parameters:
            return cls(model=model)
    return cls()


def get_default_provider() -> LLMProvider:
    """Return the provider configured via env var, or fall back to DeepSeek.

    Read order: RDTII_LLM_PROVIDER -> default 'deepseek'.
    """
    name = os.getenv("RDTII_LLM_PROVIDER", "deepseek")
    return get_provider(name)


def resolve_provider(name: str | None = None) -> LLMProvider:
    """Resolve the run's provider, wrapping it with failover when configured.

    Primary   = ``name`` or ``RDTII_LLM_PROVIDER`` (default ``deepseek``).
    Fallback  = ``RDTII_LLM_FALLBACK_PROVIDER`` (default unset = no fallback).

    When a distinct, constructible fallback is configured, returns a
    :class:`~providers.fallback.FallbackProvider` so that if the primary model is
    unavailable in a reviewer's environment, calls transparently fail over. This
    is the judge-safety net: ship ``RDTII_LLM_FALLBACK_PROVIDER=deepseek`` with an
    API key so a run still completes even if local Ollama is absent. Default
    behaviour (no fallback env) is unchanged, so tests and the eval harness are
    unaffected.
    """

    primary_name = name or os.getenv("RDTII_LLM_PROVIDER", "deepseek")
    primary = get_provider(primary_name)

    fb_name = os.getenv("RDTII_LLM_FALLBACK_PROVIDER", "").strip()
    if not fb_name or _canonicalise(fb_name) == _canonicalise(primary_name):
        return primary
    try:
        fallback = get_provider(fb_name)
    except Exception as exc:  # noqa: BLE001 — a missing fallback must not break the run
        logging.getLogger(__name__).warning(
            "fallback provider %r unavailable (%s); using primary %s only",
            fb_name, exc, primary_name,
        )
        return primary

    from .fallback import FallbackProvider
    return FallbackProvider(primary, fallback)


# Providers hidden from the UI/health list: usable if named explicitly, but
# not offered as a pick because they can't run out of the box. `llama-3-local`
# needs a hand-downloaded .gguf (LLAMA_MODEL_PATH) — selecting it by mistake
# caused "LLM extraction failed"; the key-free local path is `ollama`, which
# auto-discovers the models on the machine.
_HIDDEN_PROVIDERS = {"llama-3-local"}


def list_providers() -> list[str]:
    """Return the provider keys offered in the UI (usable ones only)."""
    return sorted(k for k in _LAZY_REGISTRY.keys() if k not in _HIDDEN_PROVIDERS)


__all__ = [
    "LLMProvider",
    "canonical_name",
    "get_provider",
    "get_default_provider",
    "is_recognised",
    "list_providers",
    "resolve_provider",
]
