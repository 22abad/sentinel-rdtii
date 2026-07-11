"""Measured per-document cost reporting (hackathon sustainability rubric).

The judges require *measured* costs, not estimates. This module builds the cost
report from real signals captured during a run:

- token counts come from the provider's own usage accounting (``RunUsageSummary``);
- cost is the provider-reported ``cost_usd`` when available, otherwise the
  measured tokens priced at the published rates in ``PRICING`` (working shown);
- local/open-weight models (Ollama, llama-cpp) are recorded at $0 API cost.

The pure :func:`build_cost_report` takes already-measured inputs so it can be
unit-tested without any network or model.
"""

from __future__ import annotations

from typing import Any

# Published API prices in USD per 1,000,000 tokens. Update as vendors change
# pricing; the report records which basis was used so claims stay auditable.
# Local/open-weight models are $0 API cost (compute is the user's own hardware).
PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    # DeepSeek
    "deepseek-chat": {"in": 0.27, "out": 1.10},
    "deepseek-v4-flash": {"in": 0.27, "out": 1.10},
    # Anthropic
    "claude-sonnet-4-5-20250929": {"in": 3.00, "out": 15.00},
    # Google
    "gemini-3-flash-preview": {"in": 0.15, "out": 0.60},
    "gemini-2.0-flash": {"in": 0.15, "out": 0.60},
}

# Model-name substrings that mark a locally hosted, zero-API-cost model.
_LOCAL_MARKERS = ("ollama", "llama3", "llama-3", "qwen", "gemma", "mistral-local", "local", "gguf")


def is_local_model(model: str) -> bool:
    """True if the model name looks like a locally hosted open-weight model."""

    name = (model or "").lower()
    return any(marker in name for marker in _LOCAL_MARKERS)


def price_tokens(model: str, input_tokens: int, output_tokens: int) -> tuple[float | None, str]:
    """Return (cost_usd, basis) for measured tokens priced at published rates.

    ``basis`` explains how the number was derived so the report is auditable:
    "local ($0)", "published-rate", or "no-price" when the model is unknown.
    """

    if is_local_model(model):
        return 0.0, "local ($0 API)"
    price = PRICING.get(model)
    if price is None:
        return None, f"no published price configured for {model!r}"
    cost = input_tokens * price["in"] / 1_000_000 + output_tokens * price["out"] / 1_000_000
    return cost, "measured tokens × published rate"


def build_cost_report(
    *,
    document: str,
    measured_on: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    llm_calls: int,
    processing_time_seconds: float,
    provider_reported_cost_usd: float | None = None,
    ocr_engine: str = "none",
    ocr_pages: int = 0,
    ocr_cost_usd: float = 0.0,
    embedding_model: str = "none",
    embedding_tokens: int = 0,
    embedding_cost_usd: float = 0.0,
    crawling: str = "self-hosted",
) -> dict[str, Any]:
    """Assemble the measured cost report in the README template's shape (pure)."""

    if provider_reported_cost_usd is not None:
        llm_cost: float | None = provider_reported_cost_usd
        basis = "provider-reported"
    else:
        llm_cost, basis = price_tokens(model, input_tokens, output_tokens)

    known_costs = [c for c in (ocr_cost_usd, embedding_cost_usd, llm_cost) if c is not None]
    total = round(sum(known_costs), 6)

    return {
        "document": document,
        "measured_on": measured_on,
        "ocr": {"engine": ocr_engine, "pages": ocr_pages, "cost_usd": round(ocr_cost_usd, 6)},
        "embedding": {
            "model": embedding_model,
            "tokens": embedding_tokens,
            "cost_usd": round(embedding_cost_usd, 6),
        },
        "llm": {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "llm_calls": llm_calls,
            "cost_usd": None if llm_cost is None else round(llm_cost, 6),
            "cost_basis": basis,
        },
        "crawling": {"mode": crawling, "cost_usd": 0.0},
        "total_cost_usd": total,
        "processing_time_seconds": round(processing_time_seconds, 3),
        "notes": (
            "Token counts are measured from the provider's usage accounting. "
            "Costs are provider-reported when available, otherwise measured "
            "tokens priced at the rates in submission/cost.py::PRICING. Local "
            "open-weight models are recorded at $0 API cost."
        ),
    }
