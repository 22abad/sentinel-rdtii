"""Load, validate, and execute golden-set evaluation modes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal, TypeVar

import httpx
import requests
from pydantic import BaseModel

from discovery import DiscoverySearchRequest, DiscoveryService
from discovery.schemas import SUPPORTED_INDICATORS
from providers import get_provider
from services.document_fetch import fetch_document_text
from services.extraction import run_extraction

from .fixture_provider import OfflineFixtureProvider
from .metrics import evaluate_predictions, normalize_evidence, prediction_matches_case
from .models import (
    GoldenCase,
    GoldenDocument,
    OfflineProviderResponse,
    PredictionRecord,
)
from .reporting import render_markdown


EvaluationMode = Literal["offline", "live-discovery", "full"]
ModelT = TypeVar("ModelT", bound=BaseModel)
DISCOVERY_TIMEOUT_SECONDS = 120.0
FETCH_TIMEOUT_SECONDS = 120.0
EXTRACTION_TIMEOUT_SECONDS = 300.0


def load_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    records: list[ModelT] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            records.append(model.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return records


def load_dataset(
    *,
    repo_root: Path,
    cases_path: Path,
    documents_path: Path,
) -> tuple[list[GoldenCase], dict[str, tuple[GoldenDocument, str]]]:
    cases = load_jsonl(cases_path, GoldenCase)
    document_records = load_jsonl(documents_path, GoldenDocument)
    _require_unique((case.case_id for case in cases), "case_id")
    _require_unique((document.document_id for document in document_records), "document_id")

    documents: dict[str, tuple[GoldenDocument, str]] = {}
    for document in document_records:
        text_path = (repo_root / document.reference_text_path).resolve()
        if repo_root.resolve() not in text_path.parents:
            raise ValueError(
                f"reference_text_path escapes repository: {document.reference_text_path}"
            )
        text = text_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != document.reference_text_sha256:
            raise ValueError(
                f"reference text hash mismatch for {document.document_id}: "
                f"expected {document.reference_text_sha256}, got {digest}"
            )
        documents[document.document_id] = (document, text)

    for case in cases:
        entry = documents.get(case.document_id)
        if entry is None:
            raise ValueError(
                f"case {case.case_id} references unknown document {case.document_id}"
            )
        document, text = entry
        if case.country_code != document.country_code:
            raise ValueError(f"country mismatch for case {case.case_id}")
        if case.source_legislation != document.source_legislation:
            raise ValueError(f"source title mismatch for case {case.case_id}")
        if normalize_evidence(case.verbatim_quote) not in normalize_evidence(text):
            raise ValueError(
                f"verbatim_quote for {case.case_id} is absent from reference text"
            )
    return cases, documents


async def run_evaluation(
    *,
    repo_root: Path,
    mode: EvaluationMode,
    cases_path: Path,
    documents_path: Path,
    output_path: Path,
    provider_name: str | None = None,
    model_name: str | None = None,
    offline_responses_path: Path | None = None,
    countries: set[str] | None = None,
    include_pending: bool = False,
    command: str = "scripts/evaluate_golden_set.py",
) -> dict:
    started = time.perf_counter()
    timing_seconds: dict[str, float] = defaultdict(float)
    dataset_started = time.perf_counter()
    all_cases, all_documents = load_dataset(
        repo_root=repo_root,
        cases_path=cases_path,
        documents_path=documents_path,
    )
    timing_seconds["dataset_load"] += time.perf_counter() - dataset_started
    normalized_countries = {country.upper() for country in countries or set()}
    if normalized_countries:
        all_cases = [
            case for case in all_cases if case.country_code in normalized_countries
        ]
        selected_document_ids = {case.document_id for case in all_cases}
        all_documents = {
            key: value
            for key, value in all_documents.items()
            if key in selected_document_ids
        }

    evaluated_cases = [
        case
        for case in all_cases
        if include_pending or case.review.status == "approved"
    ]
    excluded_cases = [
        {
            "case_id": case.case_id,
            "reason": f"review status is {case.review.status}",
        }
        for case in all_cases
        if case not in evaluated_cases
    ]
    if not evaluated_cases:
        raise ValueError(
            "No approved golden cases are available. Obtain substantive review or "
            "use --include-pending for development-only output."
        )

    evaluated_document_ids = {case.document_id for case in evaluated_cases}
    evaluation_documents = {
        document_id: entry
        for document_id, entry in all_documents.items()
        if document_id in evaluated_document_ids
    }

    predictions: list[PredictionRecord] = []
    usage_summaries: list[dict] = []
    ocr_usage_records: list[dict] = []
    discovery_result: dict | None = None
    source_failures: list[dict] = []
    actual_provider = provider_name or "none"
    actual_model = model_name

    if mode == "offline":
        if offline_responses_path is None:
            raise ValueError("offline mode requires --offline-responses")
        response_records = load_jsonl(
            offline_responses_path,
            OfflineProviderResponse,
        )
        by_document: dict[str, dict[str, dict | None]] = defaultdict(dict)
        for record in response_records:
            if record.indicator_id in by_document[record.document_id]:
                raise ValueError(
                    f"duplicate offline response for {record.document_id}/{record.indicator_id}"
                )
            by_document[record.document_id][record.indicator_id] = (
                None if record.no_mapping else record.response
            )
        actual_provider = "offline-fixture"
        actual_model = OfflineFixtureProvider.model_name
        for document_id, (document, text) in evaluation_documents.items():
            provider = OfflineFixtureProvider(by_document.get(document_id, {}))
            extraction_started = time.perf_counter()
            try:
                response = await _with_timeout(
                    run_extraction(text, provider),
                    timeout_seconds=_timeout_from_env(
                        "RDTII_EVALUATION_EXTRACTION_TIMEOUT_SECONDS",
                        EXTRACTION_TIMEOUT_SECONDS,
                    ),
                    operation=f"offline extraction for {document_id}",
                )
            except Exception as exc:
                source_failures.append(_source_failure(
                    document_id=document_id,
                    stage="extraction",
                    reason=str(exc),
                    url=document.official_source_url,
                    mode=mode,
                ))
                continue
            finally:
                timing_seconds["mapping"] += time.perf_counter() - extraction_started
            if provider.missing_indicators:
                source_failures.append(_source_failure(
                    document_id=document_id,
                    stage="fixture_configuration",
                    reason=(
                        "missing explicit fixture outcome for indicator(s): "
                        f"{sorted(provider.missing_indicators)}"
                    ),
                    url=document.official_source_url,
                    mode=mode,
                ))
            predictions.extend(
                _prediction_records(document, response.mappings)
            )
            if response.usage is not None:
                usage_summaries.append(response.usage.model_dump())
    else:
        discovery_started = time.perf_counter()
        discovery_result = await _run_live_discovery(
            evaluated_cases,
            evaluation_documents,
        )
        timing_seconds["discovery"] += time.perf_counter() - discovery_started
        if mode == "full":
            if not provider_name:
                raise ValueError("full mode requires --provider")
            provider = get_provider(provider_name, model_name)
            actual_provider = provider_name
            actual_model = getattr(provider, "model_name", None)
            discovered_urls = discovery_result["matched_urls"]
            for document_id, (document, _fixture_text) in evaluation_documents.items():
                source_url = discovered_urls.get(document_id)
                if not source_url:
                    source_failures.append(_source_failure(
                        document_id=document_id,
                        stage="discovery",
                        reason="expected document was not found in live discovery",
                        mode=mode,
                    ))
                    continue
                try:
                    fetched = await _retry_transient(
                        lambda: fetch_document_text(source_url),
                        timeout_seconds=_timeout_from_env(
                            "RDTII_EVALUATION_FETCH_TIMEOUT_SECONDS",
                            FETCH_TIMEOUT_SECONDS,
                        ),
                        operation=f"document fetch for {document_id}",
                    )
                    timing_seconds["fetch"] += fetched.timing_seconds.get("fetch", 0.0)
                    timing_seconds["pdf_processing"] += fetched.timing_seconds.get(
                        "pdf_processing", 0.0
                    )
                    if fetched.pdf_metadata:
                        ocr_usage_records.extend(
                            fetched.pdf_metadata.get("vision_usage", [])
                        )
                    if not fetched.quality.should_extract:
                        raise ValueError(
                            "; ".join(fetched.quality.warnings)
                            or f"crawl quality is {fetched.quality.status}"
                        )
                    mapping_started = time.perf_counter()
                    try:
                        response = await _with_timeout(
                            run_extraction(
                                fetched.text,
                                provider,
                                pdf_metadata=fetched.pdf_metadata,
                            ),
                            timeout_seconds=_timeout_from_env(
                                "RDTII_EVALUATION_EXTRACTION_TIMEOUT_SECONDS",
                                EXTRACTION_TIMEOUT_SECONDS,
                            ),
                            operation=f"live extraction for {document_id}",
                        )
                    finally:
                        timing_seconds["mapping"] += time.perf_counter() - mapping_started
                except Exception as exc:
                    source_failures.append(_source_failure(
                        document_id=document_id,
                        stage="fetch_or_extraction",
                        reason=str(exc),
                        url=source_url,
                        mode=mode,
                    ))
                    continue
                predictions.extend(_prediction_records(document, response.mappings))
                if response.usage is not None:
                    usage_summaries.append(response.usage.model_dump())

    excluded_predictions: list[dict] = []
    if mode != "live-discovery" and excluded_cases:
        scored_predictions: list[PredictionRecord] = []
        ignored_cases = [case for case in all_cases if case not in evaluated_cases]
        for prediction in predictions:
            matches_evaluated = any(
                prediction_matches_case(case, prediction) for case in evaluated_cases
            )
            matched_excluded = [
                case.case_id
                for case in ignored_cases
                if prediction_matches_case(case, prediction)
            ]
            if matched_excluded and not matches_evaluated:
                excluded_predictions.append({
                    "prediction_id": prediction.prediction_id,
                    "matched_excluded_case_ids": matched_excluded,
                    "reason": "prediction matches a case excluded by review status",
                })
            else:
                scored_predictions.append(prediction)
        predictions = scored_predictions

    mapping_evaluation = None
    if mode != "live-discovery":
        mapping_evaluation = evaluate_predictions(
            evaluated_cases,
            predictions,
            evaluation_documents,
        )

    llm_usage = _aggregate_usage(usage_summaries)
    ocr_usage = _aggregate_ocr_usage(ocr_usage_records)
    report = {
        "schema_version": "1.0",
        "metadata": {
            "commit_sha": _git_commit(repo_root),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "timezone": str(datetime.now().astimezone().tzinfo),
            "mode": mode,
            "provider": actual_provider,
            "model": actual_model,
            "command": command,
            "case_set_sha256": _file_hash(cases_path),
            "document_set_sha256": _file_hash(documents_path),
            "include_pending": include_pending,
        },
        "dataset": {
            "cases_loaded": len(all_cases),
            "cases_evaluated": len(evaluated_cases),
            "documents_evaluated": len(evaluation_documents),
            "countries": sorted({case.country_code for case in evaluated_cases}),
            "indicators": sorted({case.indicator_id for case in evaluated_cases}),
            "excluded_cases": excluded_cases,
            "excluded_predictions": excluded_predictions,
        },
        "discovery": discovery_result,
        "mapping_evaluation": mapping_evaluation,
        "source_failures": source_failures,
        "usage": llm_usage,
        "ocr_usage": ocr_usage,
        "cost_usd": _combined_cost(llm_usage, ocr_usage, mode=mode),
        "timing_seconds": {
            **{
                stage: round(timing_seconds.get(stage, 0.0), 6)
                for stage in (
                    "dataset_load",
                    "discovery",
                    "fetch",
                    "pdf_processing",
                    "mapping",
                )
            },
            "total": round(time.perf_counter() - started, 6),
        },
        "runtime_seconds": round(time.perf_counter() - started, 6),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = output_path.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


async def _run_live_discovery(
    cases: list[GoldenCase],
    documents: dict[str, tuple[GoldenDocument, str]],
) -> dict:
    unsupported = sorted({
        case.indicator_id for case in cases
        if case.indicator_id not in SUPPORTED_INDICATORS
    })
    if unsupported:
        raise ValueError(
            "live discovery supports only RDTII pillar 6/7 indicators; "
            f"unsupported indicator(s): {unsupported}"
        )
    service = DiscoveryService()
    matched_urls: dict[str, str] = {}
    matched_url_ranks: dict[str, tuple] = {}
    failures: list[dict] = []
    requests: dict[tuple[str, str], set[str]] = defaultdict(set)
    for case in cases:
        requests[(case.country_code, case.indicator_id)].add(case.document_id)

    accepted_candidates = 0
    official_candidates = 0
    valid_candidates = 0
    retrieval_modes: dict[str, int] = defaultdict(int)
    for (country_code, indicator_id), document_ids in sorted(requests.items()):
        try:
            request = DiscoverySearchRequest(
                country_code=country_code,
                pillars=[int(indicator_id.split(".", 1)[0])],
                indicators=[indicator_id],
                source_mode="official_only",
                include_secondary_leads=False,
                browser_mode="auto",
            )
            response = await _retry_transient(
                lambda: service.search(request),
                timeout_seconds=_timeout_from_env(
                    "RDTII_EVALUATION_DISCOVERY_TIMEOUT_SECONDS",
                    DISCOVERY_TIMEOUT_SECONDS,
                ),
                operation=f"discovery for {country_code}/{indicator_id}",
            )
        except Exception as exc:
            for document_id in document_ids:
                failures.append({
                    "document_id": document_id,
                    "country_code": country_code,
                    "indicator_id": indicator_id,
                    "reason": f"discovery failed: {exc}",
                })
            continue
        accepted_candidates += len(response.candidates)
        official_candidates += sum(
            candidate.source_grade == "primary" for candidate in response.candidates
        )
        valid_candidates += sum(
            candidate.validation_status == "verified" for candidate in response.candidates
        )
        for retrieval_mode, count in response.diagnostics.get("retrieval_modes", {}).items():
            retrieval_modes[retrieval_mode] += int(count)
        for document_id in document_ids:
            document = documents[document_id][0]
            candidate = _find_document_candidate(document, response.candidates)
            if candidate is None:
                failures.append({
                    "document_id": document_id,
                    "country_code": country_code,
                    "indicator_id": indicator_id,
                    "reason": "expected official document not found",
                })
            else:
                rank = _candidate_rank(candidate)
                if rank > matched_url_ranks.get(document_id, ()):
                    matched_urls[document_id] = candidate.url
                    matched_url_ranks[document_id] = rank

    expected_documents = len({case.document_id for case in cases})
    return {
        "expected_documents": expected_documents,
        "documents_found": len(matched_urls),
        "document_recall": len(matched_urls) / expected_documents if expected_documents else 1.0,
        "accepted_candidates": accepted_candidates,
        "official_source_rate": official_candidates / accepted_candidates if accepted_candidates else None,
        "valid_url_rate": valid_candidates / accepted_candidates if accepted_candidates else None,
        "matched_urls": matched_urls,
        "retrieval_modes": dict(sorted(retrieval_modes.items())),
        "fallback_used": bool(
            retrieval_modes.get("fixture") or retrieval_modes.get("fallback")
        ),
        "failures": failures,
    }


def _find_document_candidate(document: GoldenDocument, candidates: list):
    expected_title = normalize_evidence(document.source_legislation)
    matches = []
    for candidate in candidates:
        title = normalize_evidence(candidate.title)
        if expected_title in title or title in expected_title:
            matches.append(candidate)
    return max(matches, key=_candidate_rank, default=None)


def _candidate_rank(candidate) -> tuple:
    validation_rank = {
        "verified": 3,
        "weak": 2,
        "unverified": 1,
        "failed": 0,
    }
    source_rank = {"primary": 2, "secondary": 1, "unknown": 0}
    retrieval_rank = {"live": 2, "fallback": 1, "fixture": 0}
    return (
        validation_rank.get(candidate.validation_status, 0),
        source_rank.get(candidate.source_grade, 0),
        retrieval_rank.get(candidate.retrieval_mode, 0),
        float(candidate.rank_score),
        float(candidate.confidence),
    )


def _prediction_records(document: GoldenDocument, mappings: list) -> list[PredictionRecord]:
    return [
        PredictionRecord(
            prediction_id=f"{document.document_id}-prediction-{index}",
            country_code=document.country_code,
            document_id=document.document_id,
            indicator_id=mapping.indicator,
            article_clause=mapping.article_clause,
            verbatim_quote=mapping.verbatim_quote,
            quote_start=mapping.quote_start,
            quote_end=mapping.quote_end,
            raw_score=mapping.score,
            scope=mapping.scope,
            requires_human_review=mapping.requires_human_review,
            source_legislation=mapping.source_legislation,
            source_url=mapping.source_url,
            extraction_provider=mapping.extraction_provider,
        )
        for index, mapping in enumerate(mappings, start=1)
    ]


def _aggregate_usage(summaries: list[dict]) -> dict | None:
    if not summaries:
        return None
    all_tokens_known = all(summary["input_tokens"] is not None for summary in summaries)
    all_outputs_known = all(summary["output_tokens"] is not None for summary in summaries)
    all_costs_known = all(summary["cost_usd"] is not None for summary in summaries)
    operations: dict[str, int] = defaultdict(int)
    for summary in summaries:
        for operation, count in summary["operations"].items():
            operations[operation] += count
    return {
        "llm_calls": sum(summary["llm_calls"] for summary in summaries),
        "successful_calls": sum(summary["successful_calls"] for summary in summaries),
        "failed_calls": sum(summary["failed_calls"] for summary in summaries),
        "calls_with_unknown_usage": sum(
            summary["calls_with_unknown_usage"] for summary in summaries
        ),
        "input_tokens": (
            sum(summary["input_tokens"] for summary in summaries)
            if all_tokens_known else None
        ),
        "output_tokens": (
            sum(summary["output_tokens"] for summary in summaries)
            if all_outputs_known else None
        ),
        "known_input_tokens": sum(summary["known_input_tokens"] for summary in summaries),
        "known_output_tokens": sum(summary["known_output_tokens"] for summary in summaries),
        "cost_usd": (
            round(sum(summary["cost_usd"] for summary in summaries), 10)
            if all_costs_known else None
        ),
        "known_cost_usd": round(
            sum(summary["known_cost_usd"] for summary in summaries), 10
        ),
        "latency_sum_ms": sum(summary["latency_sum_ms"] for summary in summaries),
        "wall_clock_ms": sum(summary["wall_clock_ms"] for summary in summaries),
        "operations": dict(sorted(operations.items())),
    }


def _aggregate_ocr_usage(records: list[dict]) -> dict:
    input_known = all(record.get("input_tokens") is not None for record in records)
    output_known = all(record.get("output_tokens") is not None for record in records)
    cost_known = all(record.get("cost_usd") is not None for record in records)
    call_counts = [record.get("call_count", 1) for record in records]
    calls_known = all(count is not None for count in call_counts)
    return {
        "vision_calls": sum(call_counts) if calls_known else None,
        "successful_calls": sum(record.get("status") == "success" for record in records),
        "failed_calls": sum(record.get("status") == "failed" for record in records),
        "unavailable_calls": sum(
            record.get("status") == "unavailable" for record in records
        ),
        "input_tokens": (
            sum(record["input_tokens"] for record in records) if input_known else None
        ),
        "output_tokens": (
            sum(record["output_tokens"] for record in records) if output_known else None
        ),
        "cost_usd": (
            round(sum(record["cost_usd"] for record in records), 10)
            if cost_known else None
        ),
        "known_cost_usd": round(
            sum(
                record["cost_usd"]
                for record in records
                if record.get("cost_usd") is not None
            ),
            10,
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
        "calls_with_unknown_usage": sum(
            record.get("input_tokens") is None or record.get("output_tokens") is None
            for record in records
        ),
        "calls": records,
    }


def _combined_cost(
    llm_usage: dict | None,
    ocr_usage: dict,
    *,
    mode: EvaluationMode,
) -> dict:
    llm_cost = (
        llm_usage.get("cost_usd")
        if llm_usage is not None
        else 0.0
        if mode == "offline"
        else None
    )
    ocr_cost = ocr_usage.get("cost_usd")
    search_cost = 0.0 if mode == "offline" else None
    known_subtotal = (
        round(llm_cost + ocr_cost, 10)
        if llm_cost is not None and ocr_cost is not None
        else None
    )
    return {
        "llm": llm_cost,
        "ocr": ocr_cost,
        "search": search_cost,
        "known_llm_ocr_subtotal": known_subtotal,
        "total": (
            round(known_subtotal + search_cost, 10)
            if known_subtotal is not None and search_cost is not None
            else None
        ),
    }


async def _with_timeout(awaitable, *, timeout_seconds: float, operation: str):
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as exc:
        raise TimeoutError(
            f"{operation} timed out after {timeout_seconds:g} seconds"
        ) from exc


async def _retry_transient(
    operation_factory,
    *,
    timeout_seconds: float,
    operation: str,
    max_attempts: int = 2,
):
    for attempt in range(1, max_attempts + 1):
        try:
            return await _with_timeout(
                operation_factory(),
                timeout_seconds=timeout_seconds,
                operation=operation,
            )
        except Exception as exc:
            if attempt >= max_attempts or not _is_transient_error(exc):
                raise
            base_delay = min(2.0, 0.25 * (2 ** (attempt - 1)))
            await asyncio.sleep(base_delay + random.uniform(0.0, base_delay * 0.2))
    raise RuntimeError(f"{operation} exhausted retry attempts")


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (
        TimeoutError,
        ConnectionError,
        httpx.TransportError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    )):
        return True
    message = str(exc).casefold()
    return any(token in message for token in ("429", "502", "503", "timed out"))


def _timeout_from_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _source_failure(
    *,
    document_id: str,
    stage: str,
    reason: str,
    mode: EvaluationMode,
    url: str | None = None,
) -> dict:
    return {
        "document_id": document_id,
        "mode": mode,
        "stage": stage,
        "url": url,
        "reason": reason,
    }


def _require_unique(values, label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"duplicate {label} values: {sorted(duplicates)}")


def _file_hash(path: Path) -> str:
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
