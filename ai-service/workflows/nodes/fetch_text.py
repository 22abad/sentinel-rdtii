from __future__ import annotations

from services.document_fetch import fetch_document_text
from workflows.nodes.base import NodeExecutor
from workflows.schemas import NodeResult, WorkflowContext, WorkflowNode


class FetchTextExecutor(NodeExecutor):
    type = "source.fetch_text"

    async def run(
        self,
        *,
        node: WorkflowNode,
        inputs: dict,
        context: WorkflowContext,
    ) -> NodeResult:
        payload = {**inputs, **node.config}
        candidate = payload.get("candidate")
        source_url = payload.get("source_url") or payload.get("url")
        if not source_url and isinstance(candidate, dict):
            source_url = candidate.get("url")
        document = await fetch_document_text(
            str(source_url or ""),
            browser_mode=str(payload.get("browser_mode") or "auto"),
        )
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs={"document": document.model_dump()},
        )
