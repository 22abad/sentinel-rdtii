from __future__ import annotations

import uuid

from schemas import ExtractionResponse, RunUsageSummary
from telemetry import UsageCollector


async def run_extraction(text: str, llm_provider, pdf_metadata: dict | None = None) -> ExtractionResponse:
    from agents.orchestrator import MASOrchestrator

    collector = UsageCollector(run_id=f"extract-{uuid.uuid4().hex}")
    orchestrator = MASOrchestrator(llm_provider)
    if hasattr(llm_provider, "usage_collection"):
        with llm_provider.usage_collection(collector):
            response = await orchestrator.run_pipeline(text, pdf_metadata=pdf_metadata)
    else:
        response = await orchestrator.run_pipeline(text, pdf_metadata=pdf_metadata)
    collector.finish()
    return response.model_copy(
        update={
            "usage": RunUsageSummary(
                run_id=collector.run_id,
                **collector.summary(),
            )
        }
    )
