from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from providers.base import ExtractionError
from workflows.registry import get_executor, list_node_types
from workflows.schemas import (
    NodeRunRequest,
    NodeTypesResponse,
    WorkflowContext,
    WorkflowNode,
    WorkflowRunEvent,
)

router = APIRouter(prefix="/api/workflows")


@router.get("/node-types", response_model=NodeTypesResponse)
def workflow_node_types() -> NodeTypesResponse:
    return NodeTypesResponse(node_types=list_node_types())


@router.post("/nodes/{node_type}/run")
async def run_workflow_node(node_type: str, req: NodeRunRequest):
    executor = _executor_or_404(node_type)
    node, context = _node_and_context(node_type, req)
    try:
        return await executor.run(node=node, inputs=req.inputs, context=context)
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/nodes/{node_type}/run/stream")
async def stream_workflow_node(node_type: str, req: NodeRunRequest):
    executor = _executor_or_404(node_type)
    node, context = _node_and_context(node_type, req)

    async def _events():
        try:
            async for event in executor.stream(node=node, inputs=req.inputs, context=context):
                yield event.to_sse()
        except ValidationError as exc:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="error",
                status="failed",
                payload={"detail": exc.errors(include_context=False)},
            ).to_sse()
        except ValueError as exc:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="error",
                status="failed",
                payload={"detail": str(exc)},
            ).to_sse()
        except HTTPException as exc:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="error",
                status="failed",
                payload={"detail": exc.detail},
            ).to_sse()
        except ExtractionError as exc:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="error",
                status="failed",
                payload={"detail": str(exc)},
            ).to_sse()

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _executor_or_404(node_type: str):
    try:
        return get_executor(node_type)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_node_type",
                "message": f"Unknown workflow node type: {node_type}",
            },
        )


def _node_and_context(node_type: str, req: NodeRunRequest) -> tuple[WorkflowNode, WorkflowContext]:
    node = WorkflowNode(
        id=req.node_id or node_type,
        type=node_type,
        config=req.config,
    )
    context = WorkflowContext(
        workflow_id=req.workflow_id,
        run_id=req.run_id,
        runtime=req.runtime,
    )
    return node, context
