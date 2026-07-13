"""Orchestrate the full economy+pillar run into submission rows.

Reuses the existing engine end to end:

    DiscoveryService.search()  ->  fetch_document_text()  ->  run_extraction()

Each verified indicator mapping becomes one 13-field ``SubmissionRow``. The
row-building step (:func:`build_row`) is pure and unit-tested offline; the
network/LLM orchestration lives in :func:`discover_and_extract` and
:func:`run_pdf`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from schemas import IndicatorMapping

from .schema import (
    SubmissionRow,
    discovery_tag_for_method,
    economy_code,
    economy_display_name,
    extract_law_number_ref,
    extract_year,
    indicator_to_rdtii_code,
)

_CONTEXT_WINDOW = 160


def _context_windows(text: str, start: int, end: int) -> tuple[str, str]:
    """Return (before, after) snippets around a quote offset, best-effort."""

    if not text or start < 0 or end < 0 or start > len(text):
        return "", ""
    before = text[max(0, start - _CONTEXT_WINDOW):start]
    after = text[end:end + _CONTEXT_WINDOW]
    return before, after


def _notes(mapping: IndicatorMapping, candidate: Any, doc_meta: dict) -> str:
    """Compose the transparency ``notes`` column from audit signals."""

    parts: list[str] = []
    if getattr(mapping, "requires_human_review", False):
        parts.append("requires human review")
    parts.extend(getattr(mapping, "flag_reasons", []) or [])
    if candidate is not None:
        parts.extend(getattr(candidate, "warnings", []) or [])
    quality = (doc_meta or {}).get("quality")
    if quality and quality != "good":
        parts.append(f"document quality: {quality}")
    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique = [p for p in parts if not (p in seen or seen.add(p))]
    return "; ".join(unique)


def build_row(
    mapping: IndicatorMapping,
    *,
    economy_display: str,
    candidate: Any = None,
    source_text: str = "",
    doc_meta: dict | None = None,
) -> SubmissionRow:
    """Convert one internal mapping into the judges' 13-field row (pure)."""

    doc_meta = doc_meta or {}
    law_name = mapping.source_legislation or getattr(candidate, "title", "") or ""
    candidate_url = getattr(candidate, "url", "") if candidate is not None else ""
    candidate_last = getattr(candidate, "last_update", "") if candidate is not None else ""
    discovery_method = (
        getattr(candidate, "discovery_method", "") if candidate is not None else ""
    )
    confidence = float(getattr(candidate, "confidence", 0.0) or 0.0) if candidate else 0.0

    before, after = _context_windows(
        source_text, mapping.quote_start, mapping.quote_end
    )

    return SubmissionRow(
        economy=economy_display,
        law_name=law_name,
        law_number_ref=extract_law_number_ref(law_name),
        last_amended=extract_year(mapping.last_update, candidate_last),
        indicator_id=indicator_to_rdtii_code(mapping.indicator),
        article=mapping.article_clause,
        discovery_tag=discovery_tag_for_method(discovery_method),
        location_reference=doc_meta.get("location_reference", ""),
        verbatim_snippet=mapping.verbatim_quote,
        mapping_rationale=SubmissionRow.clip_rationale(mapping.impact),
        source_url=mapping.source_url or candidate_url,
        confidence=confidence,
        notes=_notes(mapping, candidate, doc_meta),
        # Extended (JSON-only) metadata
        ocr_quality_cer=doc_meta.get("ocr_quality_cer"),
        processing_time_seconds=doc_meta.get("processing_time_seconds"),
        raw_context_before=before,
        raw_context_after=after,
        pdf_is_scanned=doc_meta.get("pdf_is_scanned"),
        retrieval_method=discovery_method or doc_meta.get("retrieval_method", ""),
    )


def _pillar_indicators(pillar: int, requested: list[str] | None) -> set[str] | None:
    """Restrict mappings to the requested pillar/indicators (None = all in pillar)."""

    if requested:
        return {indicator_to_rdtii_code(i) for i in requested}
    return None


async def discover_and_extract(
    economy: str,
    pillar: int,
    *,
    provider_name: str | None = None,
    indicators: list[str] | None = None,
    limit: int = 20,
    browser_mode: str = "auto",
    max_documents: int | None = None,
) -> tuple[list[SubmissionRow], dict]:
    """Run discovery + extraction for one economy and pillar.

    Returns (rows, run_meta). Heavy imports are deferred so that importing this
    module (and unit-testing :func:`build_row`) does not require the provider or
    crawler stack.
    """

    from discovery import DiscoverySearchRequest, DiscoveryService
    from providers import get_default_provider, get_provider
    from services.document_fetch import fetch_document_text
    from services.extraction import run_extraction

    code = economy_code(economy)
    display = economy_display_name(economy)
    provider = get_provider(provider_name) if provider_name else get_default_provider()

    request = DiscoverySearchRequest(
        country_code=code,
        pillars=[pillar],
        indicators=indicators or [],
        limit=limit,
        browser_mode=browser_mode,
    )
    discovery = await DiscoveryService().search(request)

    wanted = _pillar_indicators(pillar, indicators)
    rows: list[SubmissionRow] = []
    documents_processed = 0
    warnings: list[str] = []
    seen_urls: set[str] = set()

    for candidate in discovery.candidates:
        if max_documents is not None and documents_processed >= max_documents:
            break
        if candidate.url in seen_urls:
            continue
        seen_urls.add(candidate.url)

        try:
            document = await fetch_document_text(
                candidate.url, browser_mode=browser_mode
            )
        except Exception as exc:  # noqa: BLE001 — one bad source must not abort the run
            warnings.append(f"fetch failed for {candidate.url}: {exc}")
            continue

        doc_meta = {
            "quality": getattr(document, "quality", "unknown"),
            "retrieval_method": candidate.discovery_method,
            "pdf_is_scanned": getattr(document, "content_type", "") == "pdf",
        }

        try:
            result = await run_extraction(document.text, provider)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"extraction failed for {candidate.url}: {exc}")
            continue

        documents_processed += 1
        for mapping in result.mappings:
            if mapping.pillar != pillar:
                continue
            code_id = indicator_to_rdtii_code(mapping.indicator)
            if wanted is not None and code_id not in wanted:
                continue
            rows.append(
                build_row(
                    mapping,
                    economy_display=display,
                    candidate=candidate,
                    source_text=document.text,
                    doc_meta=doc_meta,
                )
            )

    meta = {
        "economy": display,
        "economy_code": code,
        "pillar": pillar,
        "provider": getattr(provider, "name", provider_name or "unknown"),
        "candidates_found": len(discovery.candidates),
        "documents_processed": documents_processed,
        "provisions_mapped": len(rows),
        "warnings": warnings,
    }
    return rows, meta


async def run_library(
    economy: str,
    pillar: int,
    *,
    provider_name: str | None = None,
    indicators: list[str] | None = None,
) -> tuple[list[SubmissionRow], dict]:
    """Offline path: map cached official texts from the local law library.

    No network. Retrieval is served from ``data/law_library`` (SHA-256 verified on
    load); the mapping itself still runs live through the same
    ``run_extraction`` pipeline, so provisions are produced — not replayed. Rows
    are tagged ``KNOWN`` (the library is the curated known-law baseline).
    """

    from law_library import lookup
    from providers import get_default_provider, get_provider
    from services.extraction import run_extraction

    display = economy_display_name(economy)
    code = economy_code(economy)
    provider = get_provider(provider_name) if provider_name else get_default_provider()

    entries = lookup(code, pillar=pillar, indicators=indicators)
    wanted = _pillar_indicators(pillar, indicators)
    rows: list[SubmissionRow] = []
    warnings: list[str] = []
    laws_processed = 0

    for entry in entries:
        candidate = SimpleNamespace(
            url=entry.official_url,
            title=entry.law_name,
            last_update="",
            discovery_method="known_mapping",  # -> discovery_tag KNOWN
            confidence=1.0,
            warnings=[],
        )
        doc_meta = {
            "quality": "good",
            "retrieval_method": "local_library",
            "pdf_is_scanned": False,
            "location_reference": entry.official_url,
        }
        try:
            result = await run_extraction(entry.text, provider)
        except Exception as exc:  # noqa: BLE001 — one bad entry must not abort the run
            warnings.append(f"extraction failed for {entry.law_id}: {exc}")
            continue

        laws_processed += 1
        for mapping in result.mappings:
            if mapping.pillar != pillar:
                continue
            code_id = indicator_to_rdtii_code(mapping.indicator)
            if wanted is not None and code_id not in wanted:
                continue
            rows.append(
                build_row(
                    mapping,
                    economy_display=display,
                    candidate=candidate,
                    source_text=entry.text,
                    doc_meta=doc_meta,
                )
            )

    if not entries:
        warnings.append(
            f"no cached laws for {display} Pillar {pillar} in the local law library"
        )

    meta = {
        "economy": display,
        "economy_code": code,
        "pillar": pillar,
        "provider": getattr(provider, "name", provider_name or "unknown"),
        "source": "local_library",
        "offline": True,
        "laws_available": len(entries),
        "documents_processed": laws_processed,
        "provisions_mapped": len(rows),
        "warnings": warnings,
    }
    return rows, meta


async def run_pdf(
    economy: str,
    pillar: int,
    pdf_path: str,
    *,
    provider_name: str | None = None,
    indicators: list[str] | None = None,
) -> tuple[list[SubmissionRow], dict]:
    """Bypass discovery: extract directly from a provided PDF path."""

    from pdf_reader import read_pdf
    from providers import get_default_provider, get_provider
    from services.extraction import run_extraction

    display = economy_display_name(economy)
    code = economy_code(economy)
    provider = get_provider(provider_name) if provider_name else get_default_provider()

    pdf_result = read_pdf(pdf_path, source_url=pdf_path)
    text = "\n".join(getattr(pdf_result, "pages", []) or [])
    doc_meta = {
        "quality": "unknown",
        "retrieval_method": "provided_pdf",
        "pdf_is_scanned": bool(getattr(pdf_result, "used_ocr", False)),
        "location_reference": pdf_path,
    }

    result = await run_extraction(text, provider)
    wanted = _pillar_indicators(pillar, indicators)
    rows: list[SubmissionRow] = []
    for mapping in result.mappings:
        if mapping.pillar != pillar:
            continue
        code_id = indicator_to_rdtii_code(mapping.indicator)
        if wanted is not None and code_id not in wanted:
            continue
        rows.append(
            build_row(
                mapping,
                economy_display=display,
                candidate=None,
                source_text=text,
                doc_meta=doc_meta,
            )
        )

    meta = {
        "economy": display,
        "economy_code": code,
        "pillar": pillar,
        "provider": getattr(provider, "name", provider_name or "unknown"),
        "source_pdf": pdf_path,
        "provisions_mapped": len(rows),
        "warnings": [],
    }
    return rows, meta
