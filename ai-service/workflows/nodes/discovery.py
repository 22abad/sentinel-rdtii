from __future__ import annotations

from discovery import DiscoverySearchRequest, DiscoveryService
from workflows.nodes.base import NodeExecutor
from workflows.schemas import NodeResult, WorkflowContext, WorkflowNode


class DiscoverySearchExecutor(NodeExecutor):
    type = "discovery.search"

    def __init__(self, service: DiscoveryService | None = None) -> None:
        self.service = service or DiscoveryService()

    async def run(
        self,
        *,
        node: WorkflowNode,
        inputs: dict,
        context: WorkflowContext,
    ) -> NodeResult:
        payload = {**inputs, **node.config}
        if "request" in payload and isinstance(payload["request"], dict):
            payload = {**payload["request"], **node.config}
        request = DiscoverySearchRequest(**payload)
        response = await self.service.search(request)
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs=response.model_dump(),
        )
