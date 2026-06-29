from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException
from providers.base import ExtractionError
from services.document_fetch import fetch_document_text
from services.extraction import run_extraction
from services.provider_config import configured_provider
from services.streaming_extraction import stream_extraction
from workflows.nodes.base import NodeExecutor
from workflows.schemas import NodeResult, WorkflowContext, WorkflowNode, WorkflowRunEvent


class ExtractMappingsExecutor(NodeExecutor):
    type = "extract.mappings"

    async def run(
        self,
        *,
        node: WorkflowNode,
        inputs: dict,
        context: WorkflowContext,
    ) -> NodeResult:
        text, pdf_metadata = await self._resolve_text(node, inputs)
        provider = configured_provider(
            node.config.get("provider") or context.runtime.get("provider"),
            node.config.get("model") or context.runtime.get("model"),
        )
        response = await run_extraction(text, provider, pdf_metadata=pdf_metadata)
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs=response.model_dump(),
        )

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
        try:
            text, pdf_metadata = await self._resolve_text(node, inputs)
            provider = configured_provider(
                node.config.get("provider") or context.runtime.get("provider"),
                node.config.get("model") or context.runtime.get("model"),
            )
        except (ValueError, ExtractionError, HTTPException) as exc:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="error",
                status="failed",
                payload={"detail": _error_detail(exc)},
            )
            return

        mappings: list[Any] = []
        rejected: list[Any] = []
        source_text = ""
        provider_name = getattr(provider, "name", "unknown")
        try:
            async for raw_event in stream_extraction(text, provider, pdf_metadata=pdf_metadata):
                event_name, payload = _parse_sse_event(raw_event)
                if event_name == "started" and isinstance(payload, dict):
                    source_text = str(payload.get("source_text") or "")
                elif event_name == "mapping":
                    mappings.append(payload)
                elif event_name == "rejected":
                    rejected.append(payload)
                elif event_name == "done" and isinstance(payload, dict):
                    provider_name = str(payload.get("provider") or provider_name)

                status = "success" if event_name == "done" else "running"
                yield WorkflowRunEvent(
                    run_id=context.run_id,
                    node_id=node.id,
                    event=event_name or "message",
                    status=status,
                    payload=payload,
                )
        except (ExtractionError, HTTPException) as exc:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="error",
                status="failed",
                payload={"detail": _error_detail(exc)},
            )
            return

        yield WorkflowRunEvent(
            run_id=context.run_id,
            node_id=node.id,
            event="node_output",
            status="success",
            payload=NodeResult(
                node_id=node.id,
                status="success",
                outputs={
                    "mappings": mappings,
                    "rejected": rejected,
                    "provider": provider_name,
                    "source_text": source_text or text,
                },
            ).model_dump(),
        )

    async def _resolve_text(self, node: WorkflowNode, inputs: dict) -> tuple[str, dict[str, Any] | None]:
        payload = {**inputs, **node.config}
        document = payload.get("document")
        if isinstance(document, dict):
            text = str(document.get("text") or "")
            pdf_metadata = document.get("pdf_metadata")
            if text.strip():
                return text, pdf_metadata if isinstance(pdf_metadata, dict) else None

        text = str(payload.get("text") or "")
        if text.strip():
            return text, None

        candidate = payload.get("candidate")
        source_url = payload.get("source_url") or payload.get("url")
        if not source_url and isinstance(candidate, dict):
            source_url = candidate.get("url")
        if source_url:
            document = await fetch_document_text(
                str(source_url),
                browser_mode=str(payload.get("browser_mode") or "auto"),
            )
            return document.text, document.pdf_metadata

        raise ValueError("extract.mappings requires document.text, text, or source_url.")


def _parse_sse_event(raw_event: str) -> tuple[str, Any]:
    event_name = ""
    data_lines: list[str] = []
    for line in raw_event.splitlines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ").strip()
        elif line.startswith("data: "):
            data_lines.append(line.removeprefix("data: "))
    raw_data = "\n".join(data_lines)
    if not raw_data:
        return event_name, {}
    try:
        return event_name, json.loads(raw_data)
    except json.JSONDecodeError:
        return event_name, raw_data


def _error_detail(exc: Exception) -> str | Any:
    if isinstance(exc, HTTPException):
        return exc.detail
    return str(exc)
