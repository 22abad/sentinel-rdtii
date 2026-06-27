from __future__ import annotations

from schemas import ExtractionResponse


async def run_extraction(text: str, llm_provider, pdf_metadata: dict | None = None) -> ExtractionResponse:
    from agents.orchestrator import MASOrchestrator

    orchestrator = MASOrchestrator(llm_provider)
    return await orchestrator.run_pipeline(text, pdf_metadata=pdf_metadata)

