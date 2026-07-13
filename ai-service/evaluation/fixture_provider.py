"""Deterministic provider responses for offline pipeline evaluation."""

from __future__ import annotations

from typing import Any

from providers.base import ExtractionError, LLMProvider


class OfflineFixtureProvider(LLMProvider):
    """Drives the real extraction pipeline without network or model calls.

    Responses are loaded from a file separate from the golden labels. This is
    deliberate: expected answers must never be copied into predictions.
    """

    name = "offline-fixture"
    model_name = "offline-fixture-v1"

    def __init__(self, responses: dict[str, dict[str, Any] | None]):
        self._responses = responses
        # The evaluation's scope is the set of pillars the fixture configures.
        # Round 2 widened the classifier to all 12 pillars, so golden documents
        # now also get queried for out-of-scope indicators; those answer
        # "NO MATCH" silently. Within a configured pillar the guardrail stays
        # loud: a missing indicator outcome is a fixture bug, not a shrug.
        self._scope_pillars = {iid.split(".")[0] for iid in responses}
        self.missing_indicators: set[str] = set()

    def _in_scope(self, indicator_id: str) -> bool:
        return indicator_id.split(".")[0] in self._scope_pillars

    def query(self, prompt: str, system: str = "") -> str:
        return "Offline fixture analysis; no external model was called."

    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        if indicator_id not in self._responses:
            if not self._in_scope(indicator_id):
                return {"verbatim_quote": "NO MATCH"}
            self.missing_indicators.add(indicator_id)
            raise ExtractionError(
                f"No offline response configured for indicator {indicator_id}"
            )
        response = self._responses[indicator_id]
        if response is None:
            return {"verbatim_quote": "NO MATCH"}
        return self._offline_payload(response)

    def extract_batch(
        self,
        chunk_text: str,
        indicators: list[tuple[str, dict[str, dict[str, str]]]],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for indicator_id, _spec in indicators:
            if indicator_id not in self._responses:
                if not self._in_scope(indicator_id):
                    result[indicator_id] = {"verbatim_quote": "NO MATCH"}
                else:
                    self.missing_indicators.add(indicator_id)
                continue
            response = self._responses[indicator_id]
            result[indicator_id] = (
                {"verbatim_quote": "NO MATCH"}
                if response is None
                else self._offline_payload(response)
            )
        return result

    def repair_extraction(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
        previous_output: dict[str, Any],
        validation_errors: list[str],
    ) -> dict[str, Any]:
        """Keep offline runs deterministic; repair must never call free-form query()."""
        return dict(previous_output)

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0

    @staticmethod
    def _offline_payload(response: dict[str, Any]) -> dict[str, Any]:
        payload = dict(response)
        # The production pipeline verifies supplied dates against live sources.
        # Offline evaluation deliberately omits the date so no crawler/network
        # path can be reached; source dates remain in the golden document data.
        payload["last_update"] = ""
        return payload
