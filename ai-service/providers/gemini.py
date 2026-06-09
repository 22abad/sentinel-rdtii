"""Gemini provider — Google Generative AI."""

from __future__ import annotations

import os
import time
from typing import Any

import google.generativeai as genai

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
        genai.configure(api_key=api_key)
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.name = self.model_name
        self._model = genai.GenerativeModel(self.model_name)

    def _call_gemini(self, prompt: str) -> tuple[str, ExtractionUsage]:
        usage = ExtractionUsage()
        t0 = time.perf_counter()
        try:
            resp = self._model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
        except Exception as e:
            raise ExtractionError(f"Gemini API error: {e}") from e
        finally:
            usage.latency_ms = int((time.perf_counter() - t0) * 1000)

        raw_text = getattr(resp, "text", "") or ""
        meta = getattr(resp, "usage_metadata", None)
        if meta is not None:
            usage.input_tokens = getattr(meta, "prompt_token_count", 0) or 0
            usage.output_tokens = getattr(meta, "candidates_token_count", 0) or 0
            usage.cost_usd = self.estimate_cost_usd(
                usage.input_tokens, usage.output_tokens
            )
        usage.raw_response = raw_text
        self.last_usage = usage
        return raw_text, usage

    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        prompt = self.build_prompt(article_text, indicator_id, feature_spec)
        raw_text, usage = self._call_gemini(prompt)
        return self.parse_json_response(raw_text)

    def extract_batch(
        self,
        chunk_text: str,
        indicators: list[tuple[str, dict[str, dict[str, str]]]],
    ) -> dict[str, dict[str, Any]]:
        from .base import LLMProvider as _Base
        prompt = _Base.build_batch_prompt(chunk_text, indicators)
        raw_text, _ = self._call_gemini(prompt)
        raw = self.parse_json_response(raw_text)
        result: dict[str, dict[str, Any]] = {}
        for indicator_id, feature_spec in indicators:
            extracted = raw.get(indicator_id)
            if extracted and isinstance(extracted, dict):
                result[indicator_id] = extracted
            else:
                defaults: dict[str, Any] = {"verbatim_quote": ""}
                for fname, fmeta in feature_spec.items():
                    ftype = fmeta.get("type", "bool")
                    if ftype == "bool":
                        defaults[fname] = False
                    elif ftype == "float":
                        defaults[fname] = 0.0
                    else:
                        defaults[fname] = ""
                result[indicator_id] = defaults
        return result

    def query(self, prompt: str, system: str = "") -> str:
        """Free-form text completion — used by the RAG query endpoint."""
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        usage = ExtractionUsage()
        t0 = time.perf_counter()
        try:
            resp = self._model.generate_content(full_prompt, generation_config=genai.types.GenerationConfig(temperature=0))
        except Exception as e:
            raise ExtractionError(f"Gemini API error: {e}") from e
        finally:
            usage.latency_ms = int((time.perf_counter() - t0) * 1000)
        raw_text = getattr(resp, "text", "") or ""
        usage.raw_response = raw_text
        self.last_usage = usage
        return raw_text

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * _INPUT_USD_PER_MTOK / 1_000_000
            + output_tokens * _OUTPUT_USD_PER_MTOK / 1_000_000
        )
