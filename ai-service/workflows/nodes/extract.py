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

        # Reuse: if we've already extracted this exact content, serve it from the
        # cache and skip the LLM entirely ("干过的活不重跑"). A force_refresh flag
        # skips the read (but still re-caches) so a demo can re-extract on demand.
        cached = None if _force_refresh(node, inputs) else _cache_get(text)
        if cached is not None:
            _log_reuse(text, cached)
            cached = {**cached, "reused": True}
            return NodeResult(node_id=node.id, status="success", outputs=cached)

        provider = configured_provider(
            node.config.get("provider") or context.runtime.get("provider"),
            node.config.get("model") or context.runtime.get("model"),
        )
        response = await run_extraction(text, provider, pdf_metadata=pdf_metadata)
        outputs = response.model_dump()
        _cache_put(text, outputs, provider=getattr(provider, "name", None))
        return NodeResult(
            node_id=node.id,
            status="success",
            outputs=outputs,
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

        # Reuse: replay a cached extraction as events and skip the LLM.
        cached = None if _force_refresh(node, inputs) else _cache_get(text)
        if cached is not None:
            _log_reuse(text, cached)
            # Replay must look like a real run: without this `started` event
            # the client never receives the source text, so the audit panel's
            # quote-highlight view has nothing to highlight into (a document
            # went "dead" the moment it became a cache hit).
            yield WorkflowRunEvent(
                run_id=context.run_id, node_id=node.id,
                event="started", status="running",
                payload={"source_text": str(cached.get("source_text") or text)},
            )
            for mapping in cached.get("mappings", []) or []:
                yield WorkflowRunEvent(
                    run_id=context.run_id, node_id=node.id,
                    event="mapping", status="running", payload=mapping,
                )
            # The rejected log is evidence too — the audit panel shows WHY
            # non-qualifying provisions never reached the output. A replay
            # that drops it makes the tool look like it never filtered.
            for rejected in cached.get("rejected", []) or []:
                yield WorkflowRunEvent(
                    run_id=context.run_id, node_id=node.id,
                    event="rejected", status="running", payload=rejected,
                )
            yield WorkflowRunEvent(
                run_id=context.run_id, node_id=node.id,
                event="node_output", status="success",
                payload=NodeResult(
                    node_id=node.id, status="success",
                    outputs={**cached, "reused": True},
                ).model_dump(),
            )
            return

        mappings: list[Any] = []
        rejected: list[Any] = []
        source_text = ""
        provider_name = getattr(provider, "name", "unknown")
        usage: dict[str, Any] | None = None
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
                    if isinstance(payload.get("usage"), dict):
                        usage = payload["usage"]

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

        outputs = {
            "mappings": mappings,
            "rejected": rejected,
            "provider": provider_name,
            "source_text": source_text or text,
            "usage": usage,
        }
        _cache_put(text, outputs, provider=provider_name)
        yield WorkflowRunEvent(
            run_id=context.run_id,
            node_id=node.id,
            event="node_output",
            status="success",
            payload=NodeResult(
                node_id=node.id,
                status="success",
                outputs=outputs,
            ).model_dump(),
        )

    async def _resolve_text(self, node: WorkflowNode, inputs: dict) -> tuple[str, dict[str, Any] | None]:
        payload = {**inputs, **node.config}

        # Know the source URL up front so the local-corpus fallback applies to
        # EVERY path — including Discovery, which pre-fetches the candidate and
        # hands us its text directly. A blocked anti-bot portal returns a
        # ~107-char "Trusted websites" banner, which is non-empty, so without
        # this the short banner would be extracted instead of the downloaded
        # statute (0 tokens, every row rejected).
        candidate = payload.get("candidate")
        source_url = payload.get("source_url") or payload.get("url")
        if not source_url and isinstance(candidate, dict):
            source_url = candidate.get("url")

        def _fallback_if_short(text: str, meta: dict[str, Any] | None):
            """Return the local-corpus text when `text` is too short to be a
            real statute body and we know its official URL; else keep `text`."""
            if len(text.strip()) < 400 and source_url:
                cached = _cached_text_for_url(str(source_url))
                if cached:
                    return cached, None
            return text, meta

        document = payload.get("document")
        if isinstance(document, dict):
            text = str(document.get("text") or "")
            pdf_metadata = document.get("pdf_metadata")
            meta = pdf_metadata if isinstance(pdf_metadata, dict) else None
            if text.strip():
                return _fallback_if_short(text, meta)

        text = str(payload.get("text") or "")
        if text.strip():
            return _fallback_if_short(text, None)

        if source_url:
            document = await fetch_document_text(
                str(source_url),
                browser_mode=str(payload.get("browser_mode") or "auto"),
            )
            return _fallback_if_short(document.text or "", document.pdf_metadata)

        raise ValueError("extract.mappings requires document.text, text, or source_url.")


def _cached_text_for_url(url: str) -> str | None:
    """Local KNOWN-baseline corpus text for this official URL, or None.

    Best-effort: any failure (no corpus, unmapped URL) just returns None and
    the caller keeps the live (short) text."""
    try:
        from services.known_corpus_cache import cached_text_for_url

        return cached_text_for_url(url)
    except Exception:  # noqa: BLE001 — the fallback must never break extraction
        return None


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


def _force_refresh(node: WorkflowNode, inputs: dict) -> bool:
    """True when the caller explicitly asks to bypass the cache read."""
    val = node.config.get("force_refresh")
    if val is None:
        val = inputs.get("force_refresh")
    return bool(val)


def _cache_get(text: str) -> dict[str, Any] | None:
    try:
        from services.extraction_cache import get_cached

        return get_cached(text)
    except Exception:  # noqa: BLE001 — cache must never break extraction
        return None


def _cache_put(text: str, outputs: dict[str, Any], *, provider: str | None) -> None:
    try:
        from services.extraction_cache import put_cached

        put_cached(text, outputs, provider=provider)
    except Exception:  # noqa: BLE001
        pass


def _log_reuse(text: str, cached: dict[str, Any]) -> None:
    """Record a reuse hit so the activity timeline shows the LLM was skipped."""
    try:
        from services.activity_log import record_activity
        from services.extraction_cache import source_hash

        n = len(cached.get("mappings", []) or [])
        record_activity(
            "reuse",
            target_type="document",
            target_id=source_hash(text)[:16],
            summary=f"Reused cached extraction ({n} mapping(s)) — LLM skipped",
            detail={"mappings": n, "source": "extraction_cache"},
        )
    except Exception:  # noqa: BLE001 — logging must never break extraction
        pass
