"""Execute page-level OCR paths and calculate measured CER."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

import fitz

from pdf_reader.non_ocr.pymupdf_extractor import _extract_page_filtered
from pdf_reader.ocr_service.tesseract_extractor import (
    _DPI,
    _ocr_array_with_conf,
    _render_page,
)
from pdf_reader.ocr_service.openai_fallback import ocr_vision_with_usage

from .cer import calculate_cer, summarize_cer
from .models import CerPageResult, OcrBenchmarkCase
from .ocr_reporting import render_ocr_markdown


def load_ocr_cases(path: Path) -> list[OcrBenchmarkCase]:
    cases: list[OcrBenchmarkCase] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            cases.append(OcrBenchmarkCase.model_validate_json(raw))
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate OCR case_id values")
    return cases


def run_ocr_benchmark(
    *,
    repo_root: Path,
    source_root: Path,
    cases_path: Path,
    output_path: Path,
    include_pending: bool = False,
    command: str = "scripts/benchmark_ocr.py",
) -> dict:
    started = time.perf_counter()
    all_cases = load_ocr_cases(cases_path)
    cases = [
        case for case in all_cases
        if include_pending or case.review.status == "approved"
    ]
    if not cases:
        raise ValueError(
            "No approved OCR cases are available. Human-correct references must be "
            "approved, or use --include-pending for development-only output."
        )

    results = [
        _run_case(case, repo_root=repo_root, source_root=source_root)
        for case in cases
    ]
    report = {
        "schema_version": "1.0",
        "metadata": {
            "commit_sha": _git_commit(repo_root),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": command,
            "case_set_sha256": _sha256(cases_path),
            "include_pending": include_pending,
            "hardware": {
                "system": platform.system(),
                "machine": platform.machine(),
                "processor": platform.processor() or "unavailable",
            },
        },
        "dataset": {
            "cases_loaded": len(all_cases),
            "cases_evaluated": len(cases),
            "normalization_policies": {
                case.case_id: case.normalization.model_dump() for case in cases
            },
            "excluded_cases": [
                {"case_id": case.case_id, "review_status": case.review.status}
                for case in all_cases if case not in cases
            ],
        },
        "summary": {
            **summarize_cer(results),
            **_usage_summary(results),
        },
        "pages": [result.model_dump() for result in results],
        "runtime_seconds": round(time.perf_counter() - started, 6),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output_path.with_suffix(".md").write_text(
        render_ocr_markdown(report),
        encoding="utf-8",
    )
    return report


def _run_case(
    case: OcrBenchmarkCase,
    *,
    repo_root: Path,
    source_root: Path,
) -> CerPageResult:
    source_path = _safe_resolve(source_root, case.source_file_path)
    reference_path = _safe_resolve(repo_root, case.reference_text_path)
    _require_hash(source_path, case.source_file_sha256)
    _require_hash(reference_path, case.reference_text_sha256)
    reference = reference_path.read_text(encoding="utf-8")

    started = time.perf_counter()
    doc = fitz.open(str(source_path))
    try:
        if case.page_number > len(doc):
            raise ValueError(
                f"case {case.case_id} requests page {case.page_number}, "
                f"but source has {len(doc)} pages"
            )
        page_index = case.page_number - 1
        confidence = None
        fallback_reason = None
        fallback_used = False
        if case.extraction_path == "pymupdf":
            candidate = _extract_page_filtered(doc[page_index])
            actual_path = "pymupdf"
        else:
            image = _render_page(doc, page_index, _DPI)
            if case.extraction_path == "tesseract":
                candidate, confidence = _ocr_array_with_conf(image, langs=case.language)
                actual_path = "tesseract"
            else:
                candidate, confidence = _ocr_array_with_conf(image, langs=case.language)
                actual_path = "tesseract"
                vision_usage = None
                if len(candidate) < 50:
                    fallback_reason = (
                        "Tesseract returned fewer than the configured minimum characters"
                    )
                    vision = ocr_vision_with_usage(image)
                    vision_usage = {
                        "provider": vision.provider,
                        "model": vision.model,
                        "status": vision.status,
                        "input_tokens": vision.input_tokens,
                        "output_tokens": vision.output_tokens,
                        "cost_usd": vision.cost_usd,
                        "pricing_date": vision.pricing_date,
                        "input_usd_per_million": vision.input_usd_per_million,
                        "output_usd_per_million": vision.output_usd_per_million,
                        "latency_ms": vision.latency_ms,
                        "error_type": vision.error_type,
                    }
                    if vision.text and len(vision.text) >= 50:
                        candidate = vision.text
                        actual_path = "openai"
                        confidence = 0.5
                        fallback_used = True
    finally:
        doc.close()
    metrics = calculate_cer(reference, candidate, case.normalization)
    return CerPageResult(
        case_id=case.case_id,
        document_id=case.document_id,
        page_number=case.page_number,
        language=case.language,
        requested_path=case.extraction_path,
        actual_path=actual_path,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        runtime_seconds=round(time.perf_counter() - started, 6),
        confidence=confidence,
        vision_usage=vision_usage if case.extraction_path == "tesseract_vision" else None,
        **metrics,
    )


def _safe_resolve(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"benchmark path escapes configured root: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _usage_summary(results: list[CerPageResult]) -> dict:
    vision = [page.vision_usage for page in results if page.vision_usage is not None]
    input_known = all(item.get("input_tokens") is not None for item in vision)
    output_known = all(item.get("output_tokens") is not None for item in vision)
    cost_known = all(item.get("cost_usd") is not None for item in vision)
    return {
        "pymupdf_pages": sum(page.actual_path == "pymupdf" for page in results),
        "tesseract_pages": sum(page.actual_path == "tesseract" for page in results),
        "vision_pages": sum(page.actual_path == "openai" for page in results),
        "vision_calls": len(vision),
        "vision_input_tokens": (
            sum(item["input_tokens"] for item in vision) if input_known else None
        ),
        "vision_output_tokens": (
            sum(item["output_tokens"] for item in vision) if output_known else None
        ),
        "vision_cost_usd": (
            round(sum(item["cost_usd"] for item in vision), 10)
            if cost_known else None
        ),
        "known_vision_cost_usd": round(
            sum(
                item["cost_usd"]
                for item in vision
                if item.get("cost_usd") is not None
            ),
            10,
        ),
        "known_vision_input_tokens": sum(
            item["input_tokens"]
            for item in vision
            if item.get("input_tokens") is not None
        ),
        "known_vision_output_tokens": sum(
            item["output_tokens"]
            for item in vision
            if item.get("output_tokens") is not None
        ),
        "vision_calls_with_unknown_usage": sum(
            item.get("input_tokens") is None or item.get("output_tokens") is None
            for item in vision
        ),
    }


def _require_hash(path: Path, expected: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
