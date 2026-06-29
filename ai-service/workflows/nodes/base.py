from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from workflows.schemas import NodeResult, WorkflowContext, WorkflowNode, WorkflowRunEvent


class NodeExecutor(ABC):
    type: str

    @abstractmethod
    async def run(
        self,
        *,
        node: WorkflowNode,
        inputs: dict,
        context: WorkflowContext,
    ) -> NodeResult:
        ...

    async def stream(
        self,
        *,
        node: WorkflowNode,
        inputs: dict,
        context: WorkflowContext,
    ) -> AsyncIterator[WorkflowRunEvent]:
        yield WorkflowRunEvent(
            run_id=context.run_id,
            node_id=node.id,
            event="node_started",
            payload={"node_type": node.type},
        )
        result = await self.run(node=node, inputs=inputs, context=context)
        yield WorkflowRunEvent(
            run_id=context.run_id,
            node_id=node.id,
            event="node_output",
            status=result.status,
            payload=result.model_dump(),
        )
