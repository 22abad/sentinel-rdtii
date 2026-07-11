"""Gemini provider — Google Generative AI."""

from __future__ import annotations

import os
import time
from contextvars import copy_context
from datetime import date
from typing import Any

from .base import ExtractionError, ExtractionUsage, LLMProvider


# Approximate prices per 1M tokens for Gemini 1.5 Flash (May 2025).
# Override via env if you use a different model.
_INPUT_USD_PER_MTOK = float(os.getenv("GEMINI_INPUT_USD_PER_MTOK", "0.075"))
_OUTPUT_USD_PER_MTOK = float(os.getenv("GEMINI_OUTPUT_USD_PER_MTOK", "0.30"))


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model_name: str | None = None, api_key: str | None = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ExtractionError(
                "GEMINI_API_KEY is not set. Set it in env or .env file."
            )
        try:
            from google import genai
        except ImportError as exc:
            raise ExtractionError(
                "google-genai is not installed. Install ai-service requirements."
            ) from exc

        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.name = self.model_name
        self._client = genai.Client(api_key=api_key)

    def _call_gemini(
        self,
        prompt: str,
        *,
        operation: str,
        indicator_ids: tuple[str, ...] = (),
        temperature: float = 0,
        json_response: bool = True,
    ) -> tuple[str, ExtractionUsage]:
        usage = ExtractionUsage()
        t0 = time.perf_counter()
        try:
            config: dict[str, Any] = {"temperature": temperature}
            if json_response:
                config["response_mime_type"] = "application/json"
            resp = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            usage.latency_ms = int((time.perf_counter() - t0) * 1000)
            self._record_usage(
                operation, usage, indicator_ids=indicator_ids,
                status="failed", error=e,
            )
            raise ExtractionError(f"Gemini API error: {e}") from e
        usage.latency_ms = int((time.perf_counter() - t0) * 1000)

        raw_text = getattr(resp, "text", "") or ""
        meta = getattr(resp, "usage_metadata", None)
        if meta is not None:
            usage.input_tokens = getattr(meta, "prompt_token_count", None)
            usage.output_tokens = getattr(meta, "candidates_token_count", None)
            if usage.input_tokens is not None and usage.output_tokens is not None:
                usage.cost_usd = self.estimate_cost_usd(
                    usage.input_tokens, usage.output_tokens
                )
        usage.raw_response = raw_text
        usage_known = usage.input_tokens is not None and usage.output_tokens is not None
        self._record_usage(
            operation,
            usage,
            indicator_ids=indicator_ids,
            cost_basis=(
                "actual_tokens_x_pricing_snapshot" if usage_known else "unavailable"
            ),
            pricing_date=date.today().isoformat() if usage_known else None,
            input_usd_per_million=_INPUT_USD_PER_MTOK if usage_known else None,
            output_usd_per_million=_OUTPUT_USD_PER_MTOK if usage_known else None,
        )
        return raw_text, usage

    def query(self, prompt: str, system: str = "") -> str:
        operation, indicator_ids = self._usage_context("query")
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        raw_text, _usage = self._call_gemini(
            full_prompt,
            operation=operation,
            indicator_ids=indicator_ids,
            temperature=0.3,
            json_response=False,
        )
        return raw_text

    def repair_extraction(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
        previous_output: dict[str, Any],
        validation_errors: list[str],
    ) -> dict[str, Any]:
        prompt = self.build_repair_prompt(
            article_text=article_text,
            indicator_id=indicator_id,
            feature_spec=feature_spec,
            previous_output=previous_output,
            validation_errors=validation_errors,
        )
        raw_text, _usage = self._call_gemini(
            prompt,
            operation="repair",
            indicator_ids=(indicator_id,),
        )
        return self.parse_json_response(raw_text)

    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        prompt = self.build_prompt(article_text, indicator_id, feature_spec)
        raw_text, _usage = self._call_gemini(
            prompt,
            operation="extract_single",
            indicator_ids=(indicator_id,),
        )
        return self.parse_json_response(raw_text)

    def extract_batch(
        self,
        chunk_text: str,
        indicators: list[tuple[str, dict[str, dict[str, str]]]],
    ) -> dict[str, dict[str, Any]]:
        import concurrent.futures
        batch: dict[str, dict[str, Any]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            fut = {
                pool.submit(
                    copy_context().run,
                    self.extract_features,
                    chunk_text,
                    ind_id,
                    spec,
                ): ind_id
                for ind_id, spec in indicators
            }
            for f in concurrent.futures.as_completed(fut):
                ind_id = fut[f]
                try:
                    data = f.result()
                    if isinstance(data, dict):
                        batch[ind_id] = data
                except ExtractionError:
                    pass
        return batch

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * _INPUT_USD_PER_MTOK / 1_000_000
            + output_tokens * _OUTPUT_USD_PER_MTOK / 1_000_000
        )
