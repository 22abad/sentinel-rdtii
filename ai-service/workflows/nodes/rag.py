from __future__ import annotations

import asyncio
import re
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
        answer, reasoning = await _complete(req, retrieved_context)
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs={
                "answer": answer,
                "reasoning": reasoning,
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


# User-selectable response formats → the instruction handed to the model.
# Text formats only (the model emits them directly); binary/download formats
# (xlsx/pdf) are a separate writer-registry job, deliberately out of scope here.
_FORMAT_INSTRUCTIONS = {
    "markdown": "Format your response using clear Markdown — headings, bold, and lists where they aid readability.",
    "plain": "Respond in plain prose only. Do not use Markdown, tables, bullet points, or code fences.",
    "json": "Respond with a SINGLE valid JSON object and nothing else — no prose, no Markdown, no code fences.",
    "table": "Present your response as a Markdown table with a clear header row. Add a short sentence before it only if context is essential.",
    "bullets": "Present your response as a concise Markdown bulleted list — one point per line, no long paragraphs.",
}


def _format_instruction(output_format: str) -> str:
    return _FORMAT_INSTRUCTIONS.get((output_format or "").strip().lower(), "")


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
    # Format instruction goes LAST so recency keeps it salient at generation.
    if instruction := _format_instruction(req.output_format):
        parts.append(f"Response format: {instruction}")
    return "\n\n".join(parts)


def _client() -> OpenAI:
    from api.system import _OLLAMA_BASE

    return OpenAI(base_url=_OLLAMA_BASE, api_key="ollama")


def _provider_name() -> str:
    from api.system import _OLLAMA_MODEL

    return f"ollama/{_OLLAMA_MODEL}"


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _split_reasoning(message) -> tuple[str, str]:
    """Separate the answer from any reasoning trace.

    Reasoning-capable Ollama models expose the chain-of-thought in a distinct
    ``reasoning_content`` field; some instead inline it in ``<think>…</think>``
    tags. Return ``(answer, reasoning)`` with reasoning empty for plain models.
    """
    content = message.content or ""
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning is None and getattr(message, "model_extra", None):
        reasoning = message.model_extra.get("reasoning_content")
    if not reasoning and (m := _THINK_RE.search(content)):
        reasoning = m.group(1)
        content = _THINK_RE.sub("", content)
    return content.strip(), (reasoning or "").strip()


async def _complete(req: RAGQueryRequest, retrieved_context: str = "") -> tuple[str, str]:
    from api.system import _OLLAMA_MODEL, _RDTII_SYSTEM_PROMPT

    # think=true asks a reasoning model to emit its trace; harmless kwarg only
    # sent when requested so plain models aren't handed an option they reject.
    extra_body = {"think": True} if req.deep_thinking else {}
    response = await asyncio.to_thread(
        _client().chat.completions.create,
        model=_OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _RDTII_SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(req, retrieved_context)},
        ],
        stream=False,
        temperature=0.3,
        extra_body=extra_body,
    )
    return _split_reasoning(response.choices[0].message)


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
