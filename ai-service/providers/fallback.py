"""Provider failover — a judge-safety net.

If the primary model is unavailable in a reviewer's environment (e.g. local
Ollama is not installed, or a request errors/times out), calls transparently fail
over to a configured fallback provider (e.g. DeepSeek behind the team's API key).
The whole multi-agent pipeline is model-agnostic, so "run it on DeepSeek instead"
needs no code change — only this wrapper to switch on failure.

After the first primary failure the wrapper **latches** to the fallback for the
rest of the run, so a dead primary is not re-attempted on every call. Telemetry
is unaffected: usage is bound through a contextvar in ``usage_collection`` (base
class), which the delegated child provider reads directly.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import LLMProvider

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    """Delegate to ``primary``; on any error, fail over to ``fallback``."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self._primary = primary
        self._fallback = fallback
        self._primary_dead = False
        self.name = f"{getattr(primary, 'name', '?')}->{getattr(fallback, 'name', '?')}"

    @property
    def primary_dead(self) -> bool:
        return self._primary_dead

    def _dispatch(self, method: str, *args, **kwargs):
        if not self._primary_dead:
            try:
                return getattr(self._primary, method)(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — any primary failure triggers failover
                logger.warning(
                    "primary provider %s failed on %s (%s: %s); failing over to %s "
                    "for the rest of this run",
                    getattr(self._primary, "name", "?"), method,
                    type(exc).__name__, exc, getattr(self._fallback, "name", "?"),
                )
                self._primary_dead = True
        return getattr(self._fallback, method)(*args, **kwargs)

    # --- network-facing methods: try primary, fall over to fallback ---
    def query(self, prompt: str, system: str = "") -> str:
        return self._dispatch("query", prompt, system)

    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        return self._dispatch("extract_features", article_text, indicator_id, feature_spec)

    def extract_batch(self, *args, **kwargs):
        return self._dispatch("extract_batch", *args, **kwargs)

    def repair_extraction(self, *args, **kwargs):
        return self._dispatch("repair_extraction", *args, **kwargs)

    # --- non-network helpers: use the currently-active provider ---
    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        active = self._fallback if self._primary_dead else self._primary
        return active.estimate_cost_usd(input_tokens, output_tokens)

    def set_usage_collector(self, collector) -> None:
        # Propagate to both children so direct-collector telemetry works whichever runs.
        self._primary.set_usage_collector(collector)
        self._fallback.set_usage_collector(collector)
