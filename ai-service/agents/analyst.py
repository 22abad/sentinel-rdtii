"""Analyst Agent implementation.

Generates high-quality, multi-paragraph legal analysis explaining the digital
trade implications and justifying the score for a given mapping.
"""

from __future__ import annotations

import asyncio
from typing import Any
from agents.base import Agent
from providers.base import LLMProvider


class AnalystAgent(Agent):
    """Agent specialized in writing multi-paragraph legal impact/comment analysis."""

    def __init__(self, provider: LLMProvider):
        system_prompt = (
            "You are a senior UN ESCAP legal and digital trade policy analyst. Your job is to draft "
            "a comprehensive, multi-paragraph 'Impact or comments' analysis explaining the digital trade "
            "implications of the legal measures and justifying the scoring for the RDTII 2.1 framework."
        )
        super().__init__(
            role="analyst",
            system_prompt=system_prompt,
            provider=provider,
        )

    async def run(
        self,
        chunk_text: str,
        indicator_id: str,
        extracted_data: dict[str, Any],
        evidence_spans: dict[str, list[str]] | None = None,
    ) -> str:
        """Draft a grounded rationale only after eligibility has been accepted."""
        prompt = f"""Draft a concise professional legal mapping rationale for:
- Indicator: {indicator_id}
- Source Law: {extracted_data.get('source_legislation', 'Unknown Law')} ({extracted_data.get('article_clause', 'Unknown Clause')})
- Verbatim Quote: "{extracted_data.get('verbatim_quote', '')}"
- Extracted Features: {extracted_data}
- Independently verified evidence spans: {evidence_spans or {}}

Explain only the legal subject, action, object, conditions/exceptions and why the
verified language belongs to this indicator. Do not mention or justify an assigned
numeric score. Do not infer facts outside the quote. Return 2-3 sentences only,
with no markdown or prefix/suffix chatter.
"""
        try:
            with self.provider.usage_operation("analyst_comment", (indicator_id,)):
                return await asyncio.to_thread(
                    self.provider.query,
                    prompt,
                    system=self.system_prompt,
                )
        except Exception:
            # Fallback to the basic impact provided by the extractor or a default message
            default_impact = extracted_data.get("impact") or extracted_data.get("policy_description") or ""
            if not default_impact:
                default_impact = f"RDTII 2.1 indicator {indicator_id} mapping for {extracted_data.get('source_legislation', 'legal provision')}."
            return default_impact
