"""OpenAI-compatible provider — covers OpenAI, DeepSeek, Together, Groq, Mistral, OpenRouter, etc.

Many vendors expose an OpenAI-compatible chat-completions API; the official
`openai` Python SDK can talk to all of them by overriding `base_url`. Instead
of writing one provider class per vendor, we have one OpenAICompatibleProvider
that subclasses configure per-vendor defaults (model name, base URL, pricing).

Add a new vendor in three lines:

    class GroqProvider(OpenAICompatibleProvider):
        default_model = "llama-3.3-70b-versatile"
        default_base_url = "https://api.groq.com/openai/v1"
        api_key_env = "GROQ_API_KEY"

Or instantiate ad-hoc:
    OpenAICompatibleProvider(model="...", base_url="...", api_key_env="...")
"""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, ClassVar

from .base import ExtractionError, ExtractionUsage, LLMProvider


def _price_from_env(env_key: str, default: float) -> float:
    raw = os.getenv(env_key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class OpenAICompatibleProvider(LLMProvider):
    #: Vendor-specific request extensions merged into every chat call
    #: (e.g. DeepSeek's thinking switch). Subclasses override.
    extra_request_body: dict = {}
    """Generic OpenAI-compatible chat provider.

    Subclass to lock in vendor-specific defaults, or pass kwargs to instantiate
    ad-hoc.
    """

    name: str = "openai-compatible"

    # Subclass overrides
    default_model: ClassVar[str] = ""
    default_base_url: ClassVar[str | None] = None
    api_key_env: ClassVar[str] = "OPENAI_API_KEY"
    input_price_env: ClassVar[str] = ""  # USD per 1M input tokens
    output_price_env: ClassVar[str] = ""  # USD per 1M output tokens
    #: USD per 1M input tokens the vendor served from its prefix cache. Left at
    #: 0.0 ("not configured") every input token is priced at the miss rate —
    #: today's behaviour, preserved by default. Set the env to bill honestly.
    cache_hit_price_env: ClassVar[str] = ""
    fallback_input_price: ClassVar[float] = 0.0
    fallback_output_price: ClassVar[float] = 0.0
    fallback_cache_hit_price: ClassVar[float] = 0.0

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
    ):
        try:
            from openai import OpenAI  # noqa: F401
        except ImportError as e:
            raise ExtractionError(
                "openai package not installed. `pip install openai`"
            ) from e

        env_var = api_key_env or self.api_key_env
        api_key = api_key or os.getenv(env_var)
        if not api_key:
            raise ExtractionError(
                f"{env_var} is not set. Export it or pass api_key=..."
            )

        self.model_name = model or os.getenv(f"{env_var.replace('_API_KEY', '')}_MODEL") or self.default_model
        if not self.model_name:
            raise ExtractionError(
                f"No model configured. Pass model=... or set {env_var.replace('_API_KEY', '')}_MODEL"
            )

        self.base_url = base_url or self.default_base_url
        # vendor display name = either subclass.name or derived from base url
        self.name = self.model_name

        from openai import OpenAI

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        # Explicit per-request timeout: the SDK default (600s x retries) lets a
        # throttled/hung connection occupy a concurrency slot for ~30 minutes,
        # which stalled full-economy evaluation runs. Fail fast; the repair /
        # fallback-provider layers handle the miss.
        client_kwargs["timeout"] = float(os.getenv("RDTII_LLM_TIMEOUT_SECONDS", "90"))
        client_kwargs["max_retries"] = int(os.getenv("RDTII_LLM_MAX_RETRIES", "1"))
        self._client = OpenAI(**client_kwargs)

        self._input_price = _price_from_env(self.input_price_env, self.fallback_input_price)
        self._output_price = _price_from_env(self.output_price_env, self.fallback_output_price)
        self._cache_hit_price = _price_from_env(
            self.cache_hit_price_env, self.fallback_cache_hit_price
        )

    def query(self, prompt: str, system: str = "") -> str:
        operation, indicator_ids = self._usage_context("query")
        usage = ExtractionUsage()
        t0 = time.perf_counter()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )
        except Exception as e:
            usage.latency_ms = int((time.perf_counter() - t0) * 1000)
            self._record_usage(
                operation,
                usage,
                indicator_ids=indicator_ids,
                status="failed",
                error=e,
            )
            raise ExtractionError(f"{self.model_name} API error: {e}") from e
        usage.latency_ms = int((time.perf_counter() - t0) * 1000)
        choice = resp.choices[0] if getattr(resp, "choices", None) else None
        usage.raw_response = choice.message.content if choice else ""
        self._populate_usage(usage, getattr(resp, "usage", None))
        self._record_priced_usage(operation, usage, indicator_ids=indicator_ids)
        return usage.raw_response

    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        prompt = self.build_prompt(article_text, indicator_id, feature_spec)
        return self._call_llm(
            prompt,
            operation="extract_single",
            indicator_ids=(indicator_id,),
        )

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
        return self._call_llm(
            prompt,
            operation="repair",
            indicator_ids=(indicator_id,),
        )

    def extract_batch(
        self,
        article_text: str,
        indicators: list[tuple[str, dict[str, dict[str, str]]]],
    ) -> dict[str, dict[str, Any]]:
        """One LLM call extracts ALL indicators from the same chunk.
        
        Args:
            article_text: The legal text chunk.
            indicators: List of (indicator_id, feature_spec) pairs.
        
        Returns:
            dict mapping indicator_id -> extracted features dict.
        """
        from .base import LLMProvider as _Base
        prompt = _Base.build_batch_prompt(article_text, indicators)
        raw = self._call_llm(
            prompt,
            max_tokens=8192,
            operation="extract_batch",
            indicator_ids=tuple(indicator_id for indicator_id, _spec in indicators),
        )
        # raw is {"6.1": {...}, "6.4": {...}, ...}
        result: dict[str, dict[str, Any]] = {}
        for indicator_id, _spec in indicators:
            if indicator_id in raw:
                result[indicator_id] = raw[indicator_id]
        return result

    def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 4096,
        *,
        operation: str,
        indicator_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        usage = ExtractionUsage()
        t0 = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Output ONLY valid JSON. No prose, no markdown fences.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body=self.extra_request_body or None,
            )
        except Exception as e:
            usage.latency_ms = int((time.perf_counter() - t0) * 1000)
            self._record_usage(
                operation,
                usage,
                indicator_ids=indicator_ids,
                status="failed",
                error=e,
            )
            raise ExtractionError(f"{self.model_name} API error: {e}") from e
        usage.latency_ms = int((time.perf_counter() - t0) * 1000)

        # Newer SDKs return objects; convert defensively.
        choice = resp.choices[0] if getattr(resp, "choices", None) else None
        usage.raw_response = choice.message.content if choice else ""

        self._populate_usage(usage, getattr(resp, "usage", None))
        self._record_priced_usage(operation, usage, indicator_ids=indicator_ids)
        return self.parse_json_response(usage.raw_response)

    @staticmethod
    def _cache_split(meta: Any, input_tokens: int | None) -> tuple[int | None, int | None]:
        """Vendor prefix-cache split of the billed input tokens, or (None, None).

        DeepSeek reports ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens``
        directly; OpenAI reports ``prompt_tokens_details.cached_tokens`` and
        leaves the miss side implied. None means "not reported" — never assume a
        silent provider had a 0% hit rate, that is exactly the reading that made
        our own cost numbers overstate the bill.
        """
        hit = getattr(meta, "prompt_cache_hit_tokens", None)
        miss = getattr(meta, "prompt_cache_miss_tokens", None)
        if hit is None and miss is None:
            details = getattr(meta, "prompt_tokens_details", None)
            cached = getattr(details, "cached_tokens", None) if details is not None else None
            if cached is None and isinstance(details, dict):
                cached = details.get("cached_tokens")
            if cached is not None:
                hit = int(cached)
        if hit is None and miss is None:
            return None, None
        if miss is None and input_tokens is not None:
            miss = max(0, input_tokens - int(hit or 0))
        if hit is None and input_tokens is not None and miss is not None:
            hit = max(0, input_tokens - int(miss))
        if hit is None or miss is None:
            # Half a split is worse than none: a (hit, None) pair reads as a
            # 100% cache rate downstream. Only report a split we can complete.
            return None, None
        return int(hit), int(miss)

    def _populate_usage(self, usage: ExtractionUsage, meta: Any) -> None:
        if meta is None:
            return
        usage.input_tokens = getattr(meta, "prompt_tokens", None)
        usage.output_tokens = getattr(meta, "completion_tokens", None)
        usage.cache_hit_tokens, usage.cache_miss_tokens = self._cache_split(
            meta, usage.input_tokens
        )
        pricing_known = self._input_price > 0 or self._output_price > 0
        if (
            pricing_known
            and usage.input_tokens is not None
            and usage.output_tokens is not None
        ):
            usage.cost_usd = self._priced_cost(usage)

    def _record_priced_usage(
        self,
        operation: str,
        usage: ExtractionUsage,
        *,
        indicator_ids: tuple[str, ...] = (),
    ) -> None:
        usage_known = usage.input_tokens is not None and usage.output_tokens is not None
        pricing_known = self._input_price > 0 or self._output_price > 0
        cache_hit_price = getattr(self, "_cache_hit_price", 0.0)
        self._record_usage(
            operation,
            usage,
            indicator_ids=indicator_ids,
            cost_basis=(
                "actual_tokens_x_pricing_snapshot"
                if usage_known and pricing_known
                else "unavailable"
            ),
            pricing_date=date.today().isoformat() if pricing_known else None,
            input_usd_per_million=self._input_price if pricing_known else None,
            output_usd_per_million=self._output_price if pricing_known else None,
            # Only when the rate was actually APPLIED. Recording it because it
            # is configured, on a call whose provider reported no split (so
            # _priced_cost billed everything at the miss rate), would put a rate
            # in the audit trail that this call's cost was not computed from.
            cache_hit_usd_per_million=(
                cache_hit_price
                if pricing_known and cache_hit_price > 0 and usage.cache_hit_tokens is not None
                else None
            ),
        )

    def _priced_cost(self, usage: ExtractionUsage) -> float:
        """Cost of one call, billing cache hits at the cache rate when known.

        Falls back to :meth:`estimate_cost_usd` (every input token at the miss
        rate) whenever the cache rate is unconfigured or the provider reported
        no split — so an unconfigured deployment produces exactly the number it
        produced before.
        """
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        # getattr: a provider built without __init__ (subclasses under test,
        # pickled instances) predates this attribute and must keep billing the
        # way it did before.
        cache_hit_price = getattr(self, "_cache_hit_price", 0.0)
        if cache_hit_price <= 0 or usage.cache_hit_tokens is None:
            return self.estimate_cost_usd(input_tokens, output_tokens)
        hit = usage.cache_hit_tokens
        miss = usage.cache_miss_tokens
        if miss is None:
            miss = max(0, input_tokens - hit)
        return (
            hit * cache_hit_price / 1_000_000
            + miss * self._input_price / 1_000_000
            + output_tokens * self._output_price / 1_000_000
        )

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self._input_price / 1_000_000
            + output_tokens * self._output_price / 1_000_000
        )


# ── Vendor presets ──────────────────────────────────────────────────────


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    default_model = "gpt-4o-mini"
    default_base_url = None  # default OpenAI host
    api_key_env = "OPENAI_API_KEY"
    input_price_env = "OPENAI_INPUT_USD_PER_MTOK"
    output_price_env = "OPENAI_OUTPUT_USD_PER_MTOK"
    cache_hit_price_env = "OPENAI_CACHE_HIT_USD_PER_MTOK"
    fallback_input_price = 0.15
    fallback_output_price = 0.60
    fallback_cache_hit_price = 0.0


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek — cheap reasoning-strong Chinese vendor.

    Endpoint:  https://api.deepseek.com/v1
    Models:    deepseek-v4-flash, deepseek-v4-pro
    Set DEEPSEEK_API_KEY (and optionally DEEPSEEK_MODEL).

    v4 models reason by default; for deterministic JSON extraction the
    reasoning budget starves the actual completion (empty content with
    finish_reason=length) and adds minutes of latency, so thinking is
    disabled unless RDTII_DEEPSEEK_THINKING=on.
    """

    extra_request_body = (
        {} if os.getenv("RDTII_DEEPSEEK_THINKING", "").lower() == "on"
        else {"thinking": {"type": "disabled"}}
    )

    name = "deepseek"
    default_model = "deepseek-v4-flash"
    default_base_url = "https://api.deepseek.com/v1"
    api_key_env = "DEEPSEEK_API_KEY"
    input_price_env = "DEEPSEEK_INPUT_USD_PER_MTOK"
    output_price_env = "DEEPSEEK_OUTPUT_USD_PER_MTOK"
    cache_hit_price_env = "DEEPSEEK_CACHE_HIT_USD_PER_MTOK"
    # ⚠ Fallbacks are a May-2025 list-price snapshot for an older model and are
    # NOT the current deepseek-v4-flash rate — a run reporting "measured cost"
    # off these numbers is reporting an estimate. Set the three envs from the
    # billing dashboard; they are what a cost claim should ever be based on.
    fallback_input_price = 0.27
    fallback_output_price = 1.10
    fallback_cache_hit_price = 0.0  # 0 = unconfigured; hits billed at the miss rate


class GroqProvider(OpenAICompatibleProvider):
    """Groq — fast inference of open-weight models (Llama 3.x, Mixtral, etc.).

    Doubles as a low-friction way to run Llama 3 without local GPU setup.
    """

    name = "groq"
    default_model = "llama-3.3-70b-versatile"
    default_base_url = "https://api.groq.com/openai/v1"
    api_key_env = "GROQ_API_KEY"
    input_price_env = "GROQ_INPUT_USD_PER_MTOK"
    output_price_env = "GROQ_OUTPUT_USD_PER_MTOK"
    fallback_input_price = 0.59
    fallback_output_price = 0.79


class TogetherProvider(OpenAICompatibleProvider):
    """Together AI — hosts many open-weight models with OpenAI-compatible API."""

    name = "together"
    default_model = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    default_base_url = "https://api.together.xyz/v1"
    api_key_env = "TOGETHER_API_KEY"
    input_price_env = "TOGETHER_INPUT_USD_PER_MTOK"
    output_price_env = "TOGETHER_OUTPUT_USD_PER_MTOK"
    fallback_input_price = 0.18
    fallback_output_price = 0.18


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter — meta-router across hundreds of models with one key."""

    name = "openrouter"
    default_model = "meta-llama/llama-3.1-8b-instruct"
    default_base_url = "https://openrouter.ai/api/v1"
    api_key_env = "OPENROUTER_API_KEY"
    input_price_env = "OPENROUTER_INPUT_USD_PER_MTOK"
    output_price_env = "OPENROUTER_OUTPUT_USD_PER_MTOK"
    fallback_input_price = 0.0  # varies per model
    fallback_output_price = 0.0


class MistralProvider(OpenAICompatibleProvider):
    """Mistral La Plateforme — OpenAI-compatible API for Mistral models."""

    name = "mistral"
    default_model = "mistral-small-latest"
    default_base_url = "https://api.mistral.ai/v1"
    api_key_env = "MISTRAL_API_KEY"
    input_price_env = "MISTRAL_INPUT_USD_PER_MTOK"
    output_price_env = "MISTRAL_OUTPUT_USD_PER_MTOK"
    fallback_input_price = 0.20
    fallback_output_price = 0.60
