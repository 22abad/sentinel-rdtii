from __future__ import annotations

from fastapi import HTTPException

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
        try:
            response = await self.service.search(request)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"No discovery sources configured for {request.country_code}.",
            )
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs=response.model_dump(),
        )
