from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from openai import OpenAI

from schemas import RAGQueryRequest
from workflows.nodes.base import NodeExecutor
from workflows.schemas import NodeResult, WorkflowContext, WorkflowNode, WorkflowRunEvent


class RagQueryExecutor(NodeExecutor):
    type = "rag.query"

    async def run(
        self,
        *,
        node: WorkflowNode,
        inputs: dict,
        context: WorkflowContext,
    ) -> NodeResult:
        req = _request_from(node.config, inputs, context.runtime)
        hits, retrieved_context = await _retrieve(req)
        answer = await _complete(req, retrieved_context)
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs={
                "answer": answer,
                "provider": _provider_name(),
                "retrieved_chunks": [h.text for h in hits],
                "retrieval_count": len(hits),
            },
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
        req = _request_from(node.config, inputs, context.runtime)
        hits, retrieved_context = await _retrieve(req)
        answer = ""
        provider = _provider_name()
        failed = False
        async for event in _stream_complete(req, retrieved_context):
            if event["event"] == "token":
                answer += str(event.get("payload") or "")
            elif event["event"] == "done" and isinstance(event.get("payload"), dict):
                payload = event["payload"]
                answer = str(payload.get("answer") or answer)
                provider = str(payload.get("provider") or provider)
            elif event["event"] == "error":
                failed = True
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event=event["event"],
                status=event.get("status", "running"),
                payload=event.get("payload", {}),
            )
        if not failed:
            yield WorkflowRunEvent(
                run_id=context.run_id,
                node_id=node.id,
                event="node_output",
                status="success",
                payload=NodeResult(
                    node_id=node.id,
                    status="success",
                    outputs={
                        "answer": answer,
                        "provider": provider,
                        "retrieved_chunks": [h.text for h in hits],
                        "retrieval_count": len(hits),
                    },
                ).model_dump(),
            )


def _request_from(config: dict, inputs: dict, runtime: dict) -> RAGQueryRequest:
    payload = {**inputs, **config}
    document = payload.get("document")
    if isinstance(document, dict) and not payload.get("source_text"):
        payload["source_text"] = document.get("text", "")
    return RAGQueryRequest(**payload)


async def _retrieve(req: RAGQueryRequest):
    """Vector-retrieve the chunks most relevant to the question.

    Mirrors /api/rag/query: embedding + DB are blocking, so run them off the
    event loop. Returns (hits, context_block); both are empty when nothing is
    retrieved, which the system prompt requires the model to admit rather than
    quote from memory.
    """
    from rag.rag import build_context, retrieve

    hits = await asyncio.to_thread(
        retrieve,
        req.question,
        country_code=req.country_code or None,
        document_ids=req.document_ids or None,
    )
    return hits, build_context(hits)


def _prompt(req: RAGQueryRequest, retrieved_context: str = "") -> str:
    parts = [f"Question: {req.question}"]
    if req.role:
        parts.insert(0, f"Your role: {req.role}")
    if req.context:
        parts.append(f"Additional context: {req.context}")
    if req.country_code:
        parts.append(f"Country / Economy under review: {req.country_code}")
    if retrieved_context:
        parts.append(f"Retrieved legal text (most relevant first):\n{retrieved_context}")
    else:
        parts.append(
            "Retrieved legal text: NONE — no source text was retrieved for this "
            "question. Do not quote or cite any legal provision."
        )
    if req.source_text:
        parts.append(f"Legal text being analyzed:\n\"\"\"\n{req.source_text}\n\"\"\"")
    return "\n\n".join(parts)


def _client() -> OpenAI:
    from api.system import _OLLAMA_BASE

    return OpenAI(base_url=_OLLAMA_BASE, api_key="ollama")


def _provider_name() -> str:
    from api.system import _OLLAMA_MODEL

    return f"ollama/{_OLLAMA_MODEL}"


async def _complete(req: RAGQueryRequest, retrieved_context: str = "") -> str:
    from api.system import _OLLAMA_MODEL, _RDTII_SYSTEM_PROMPT

    response = await asyncio.to_thread(
        _client().chat.completions.create,
        model=_OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _RDTII_SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(req, retrieved_context)},
        ],
        stream=False,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


async def _stream_complete(
    req: RAGQueryRequest, retrieved_context: str = ""
) -> AsyncIterator[dict]:
    from api.system import _OLLAMA_MODEL, _RDTII_SYSTEM_PROMPT

    full_answer = ""
    try:
        stream = _client().chat.completions.create(
            model=_OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _RDTII_SYSTEM_PROMPT},
                {"role": "user", "content": _prompt(req, retrieved_context)},
            ],
            stream=True,
            temperature=0.3,
        )
        for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                full_answer += content
                yield {"event": "token", "payload": content}

        yield {
            "event": "done",
            "status": "success",
            "payload": {"answer": full_answer, "provider": _provider_name()},
        }
    except Exception as exc:
        yield {
            "event": "error",
            "status": "failed",
            "payload": {"detail": str(exc)},
        }
