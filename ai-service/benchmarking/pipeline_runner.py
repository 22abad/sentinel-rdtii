"""Measured single-document runtime and API-cost benchmark."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

from providers import get_provider
from services.document_fetch import fetch_document_text
from services.extraction import run_extraction


async def run_document_benchmark(
    *,
    repo_root: Path,
    source_url: str,
    document_id: str,
    provider_name: str,
    model_name: str | None,
    output_path: Path,
    command: str,
) -> dict:
    started = time.perf_counter()
    fetched = await fetch_document_text(source_url)
    if not fetched.quality.should_extract:
        raise ValueError(
            "; ".join(fetched.quality.warnings)
            or f"crawl quality is {fetched.quality.status}"
        )

    provider = get_provider(provider_name, model_name)
    mapping_started = time.perf_counter()
    response = await run_extraction(
        fetched.text,
        provider,
        pdf_metadata=fetched.pdf_metadata,
    )
    mapping_seconds = time.perf_counter() - mapping_started
    usage = response.usage.model_dump() if response.usage is not None else None
    vision_records = (
        fetched.pdf_metadata.get("vision_usage", []) if fetched.pdf_metadata else []
    )
    ocr_usage = _ocr_usage(vision_records)
    costs = _costs(usage, ocr_usage)
    timing = {
        "discovery": 0.0,
        "fetch": fetched.timing_seconds.get("fetch", 0.0),
        "pdf_processing": fetched.timing_seconds.get("pdf_processing", 0.0),
        "mapping": round(mapping_seconds, 6),
        "total": round(time.perf_counter() - started, 6),
    }
    report = {
        "schema_version": "1.0",
        "metadata": {
            "commit_sha": _git_commit(repo_root),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": command,
            "hardware": {
                "system": platform.system(),
                "machine": platform.machine(),
                "processor": platform.processor() or "unavailable",
            },
        },
        "document": {
            "document_id": document_id,
            "source_url": source_url,
            "content_type": fetched.content_type,
            "pages": (fetched.pdf_metadata or {}).get("total_pages"),
            "source_file_sha256": (fetched.pdf_metadata or {}).get(
                "source_file_sha256"
            ),
            "extracted_text_sha256": hashlib.sha256(
                fetched.text.encode("utf-8")
            ).hexdigest(),
            "character_count": len(fetched.text),
        },
        "configuration": {
            "provider": provider_name,
            "model": getattr(provider, "model_name", model_name),
            "pipeline_mode": "direct-source-full",
            "ocr": fetched.pdf_metadata,
        },
        "result": {
            "mappings": len(response.mappings),
            "rejected_extractions": len(response.rejected),
        },
        "usage": usage,
        "ocr_usage": ocr_usage,
        "cost_usd": costs,
        "timing_seconds": timing,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output_path.with_suffix(".md").write_text(
        render_document_benchmark(report),
        encoding="utf-8",
    )
    return report


def render_document_benchmark(report: dict) -> str:
    document = report["document"]
    config = report["configuration"]
    usage = report["usage"] or {}
    costs = report["cost_usd"]
    timing = report["timing_seconds"]
    return "\n".join([
        "# Single-document pipeline benchmark",
        "",
        f"- Commit: `{report['metadata']['commit_sha']}`",
        f"- Document: `{document['document_id']}` ({document['pages'] or 'unknown'} pages)",
        f"- Provider/model: `{config['provider']}` / `{config['model'] or 'unknown'}`",
        f"- Source file SHA-256: `{document['source_file_sha256'] or 'unavailable'}`",
        "",
        "## Measured usage",
        "",
        f"- Mapping LLM calls: {usage.get('llm_calls', 0)}",
        f"- Mapping tokens: {_display(usage.get('input_tokens'))} input / "
        f"{_display(usage.get('output_tokens'))} output",
        f"- Vision OCR calls: {_display(report['ocr_usage']['vision_calls'])}",
        f"- Vision OCR tokens: {_display(report['ocr_usage']['input_tokens'])} input / "
        f"{_display(report['ocr_usage']['output_tokens'])} output",
        f"- Known Vision OCR token subtotal: "
        f"{_display(report['ocr_usage']['known_input_tokens'])} input / "
        f"{_display(report['ocr_usage']['known_output_tokens'])} output",
        f"- Vision calls with unavailable usage: "
        f"{report['ocr_usage']['calls_with_unknown_usage']}",
        f"- Mapping API cost: {_money(costs['llm'])}",
        f"- OCR API cost: {_money(costs['ocr'])}",
        f"- Known OCR API cost subtotal: "
        f"{_money(report['ocr_usage']['known_cost_usd'])}",
        f"- Total API cost: {_money(costs['total'])}",
        "",
        "## Stage timing",
        "",
        f"- Fetch: {timing['fetch']:.3f}s",
        f"- PDF processing/OCR: {timing['pdf_processing']:.3f}s",
        f"- Mapping: {timing['mapping']:.3f}s",
        f"- Total: {timing['total']:.3f}s",
        "",
        "> Local-provider API cost may be zero, but hardware and runtime are still reported. "
        "Unavailable provider usage or pricing is never converted to zero.",
        "",
    ])


def _ocr_usage(records: list[dict]) -> dict:
    input_known = all(record.get("input_tokens") is not None for record in records)
    output_known = all(record.get("output_tokens") is not None for record in records)
    cost_known = all(record.get("cost_usd") is not None for record in records)
    call_counts = [record.get("call_count", 1) for record in records]
    calls_known = all(count is not None for count in call_counts)
    return {
        "vision_calls": sum(call_counts) if calls_known else None,
        "input_tokens": sum(record["input_tokens"] for record in records) if input_known else None,
        "output_tokens": sum(record["output_tokens"] for record in records) if output_known else None,
        "cost_usd": (
            round(sum(record["cost_usd"] for record in records), 10)
            if cost_known else None
        ),
        "known_input_tokens": sum(
            record["input_tokens"]
            for record in records
            if record.get("input_tokens") is not None
        ),
        "known_output_tokens": sum(
            record["output_tokens"]
            for record in records
            if record.get("output_tokens") is not None
        ),
        "known_cost_usd": round(
            sum(
                record["cost_usd"]
                for record in records
                if record.get("cost_usd") is not None
            ),
            10,
        ),
        "unavailable_calls": sum(
            record.get("status") == "unavailable" for record in records
        ),
        "calls_with_unknown_usage": sum(
            record.get("input_tokens") is None or record.get("output_tokens") is None
            for record in records
        ),
        "calls": records,
    }


def _costs(usage: dict | None, ocr_usage: dict) -> dict:
    llm = usage.get("cost_usd") if usage else None
    ocr = ocr_usage.get("cost_usd")
    return {
        "llm": llm,
        "ocr": ocr,
        "search": 0.0,
        "total": round(llm + ocr, 10) if llm is not None and ocr is not None else None,
    }


def _display(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value:,}"


def _money(value: float | None) -> str:
    return "Unavailable" if value is None else f"${value:.6f}"


def _git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
