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
from urllib.parse import urlsplit

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
    retrieval_mode = (
        getattr(candidate, "retrieval_mode", "") if candidate is not None else ""
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
        discovery_tag=(
            "KNOWN"
            if retrieval_mode in {"fixture", "fallback"}
            else discovery_tag_for_method(discovery_method)
        ),
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
        # Preserve fixture provenance for final novelty reconciliation. For live
        # candidates, retain the more descriptive discovery method as before.
        retrieval_method=(
            retrieval_mode
            if retrieval_mode in {"fixture", "fallback"}
            else discovery_method or doc_meta.get("retrieval_method", "")
        ),
        retrieval_mode=retrieval_mode or doc_meta.get("retrieval_mode", "unknown"),
        final_url=doc_meta.get("final_url", ""),
        http_status=doc_meta.get("http_status"),
        fetch_method=doc_meta.get("fetch_method", ""),
    )


def _strict_fetch_audit(candidate: Any, document: Any) -> tuple[bool, str]:
    """Verify the extraction fetch itself is live, successful, and official."""

    from discovery.validator import _document_retrieval_mode

    metadata = dict(getattr(document, "crawl_metadata", {}) or {})
    final_url = str(metadata.get("final_url") or getattr(candidate, "url", ""))
    fetch_method = str(metadata.get("fetch_method") or "")
    try:
        status = int(metadata.get("http_status"))
    except (TypeError, ValueError):
        status = 0
    try:
        hostname = (urlsplit(final_url).hostname or "").encode("idna").decode("ascii").casefold()
    except (UnicodeError, ValueError):
        hostname = ""
    official_domains = {
        str(domain).rstrip(".").casefold()
        for domain in getattr(candidate, "official_domains", [])
    }
    if hostname not in official_domains:
        return False, f"final URL is outside configured official domains: {final_url}"
    if not 200 <= status < 400:
        return False, f"fetch did not return a successful HTTP status: {status or 'missing'}"
    if _document_retrieval_mode(fetch_method) != "live":
        return False, f"fetch method is not live: {fetch_method or 'missing'}"
    if metadata.get("tls_verified") is not True:
        return False, "fetch did not prove TLS verification"
    return True, ""


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
    strict_live: bool = False,
) -> tuple[list[SubmissionRow], dict]:
    """Run discovery + extraction for one economy and pillar.

    Returns (rows, run_meta). Heavy imports are deferred so that importing this
    module (and unit-testing :func:`build_row`) does not require the provider or
    crawler stack.
    """

    from discovery import DiscoverySearchRequest, DiscoveryService
    from providers import resolve_provider
    from services.document_fetch import fetch_document_text
    from services.extraction import run_extraction

    code = economy_code(economy)
    display = economy_display_name(economy)

    request = DiscoverySearchRequest(
        country_code=code,
        pillars=[pillar],
        indicators=indicators or [],
        limit=limit,
        browser_mode=browser_mode,
        source_mode="official_only" if strict_live else "official_first",
        include_secondary_leads=not strict_live,
        strict_live=strict_live,
    )
    discovery = await DiscoveryService().search(request)
    provider = resolve_provider(provider_name)

    wanted = _pillar_indicators(pillar, indicators)
    rows: list[SubmissionRow] = []
    documents_processed = 0
    warnings: list[str] = list(discovery.diagnostics.get("warnings", []))
    seen_urls: set[str] = set()

    eligible_candidates = [
        candidate
        for candidate in discovery.candidates
        if candidate.retrieval_mode == "live"
    ]
    excluded_non_live = len(discovery.candidates) - len(eligible_candidates)
    if excluded_non_live:
        warnings.append(
            f"Excluded {excluded_non_live} fixture/fallback candidate(s) from formal submission."
        )

    for candidate in eligible_candidates:
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

        if strict_live:
            accepted, reason = _strict_fetch_audit(candidate, document)
            if not accepted:
                warnings.append(f"strict-live rejected {candidate.url}: {reason}")
                continue

        crawl_meta = dict(getattr(document, "crawl_metadata", {}) or {})
        doc_meta = {
            "quality": getattr(document, "quality", "unknown"),
            "retrieval_method": candidate.discovery_method,
            "pdf_is_scanned": getattr(document, "content_type", "") == "pdf",
            "retrieval_mode": candidate.retrieval_mode,
            "final_url": crawl_meta.get("final_url") or candidate.url,
            "http_status": crawl_meta.get("http_status"),
            "fetch_method": crawl_meta.get("fetch_method") or "",
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
        "live_candidates": len(eligible_candidates),
        "fixture_candidates_excluded": excluded_non_live,
        "documents_processed": documents_processed,
        "provisions_mapped": len(rows),
        "retrieval_mode": "strict_live" if strict_live else discovery.diagnostics.get("mode", "auto"),
        "evidence_counts": {
            "seed": 0,
            "live_discovered": len(rows),
            "fixture": 0,
        },
        "discovery_diagnostics": discovery.diagnostics,
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
    from providers import resolve_provider
    from services.extraction import run_extraction

    display = economy_display_name(economy)
    code = economy_code(economy)
    provider = resolve_provider(provider_name)

    entries = lookup(code, pillar=pillar, indicators=indicators)
    wanted = _pillar_indicators(pillar, indicators)
    rows: list[SubmissionRow] = []
    warnings: list[str] = []
    laws_processed = 0

    for entry in entries:
        # Cached KNOWN-baseline laws map to the KNOWN tag; cached NEW discoveries
        # (origin="discovered") must surface as NEW.
        is_discovered = getattr(entry, "origin", "known") == "discovered"
        candidate = SimpleNamespace(
            url=entry.official_url,
            title=entry.law_name,
            last_update="",
            discovery_method="cached_discovery" if is_discovered else "known_mapping",
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
        "retrieval_mode": "seed",
        "offline": True,
        "laws_available": len(entries),
        "documents_processed": laws_processed,
        "provisions_mapped": len(rows),
        "evidence_counts": {"seed": len(rows), "live_discovered": 0, "fixture": 0},
        "warnings": warnings,
    }
    return rows, meta


async def run_seed_first(
    economy: str,
    pillar: int,
    *,
    provider_name: str | None = None,
    indicators: list[str] | None = None,
    limit: int = 20,
    browser_mode: str = "auto",
    max_documents: int | None = None,
) -> tuple[list[SubmissionRow], dict]:
    """Hybrid retrieval: try the known-good seed URLs first, then live discovery.

    Judges' plain ``python main.py --economy X --pillar 6`` should not gamble the
    whole run on a live crawl. This path first serves the curated **seed** laws
    from the local library (``run_library`` — SHA-256-verified cached official
    text, fully reproducible, no network), then runs live ``discover_and_extract``
    as a **fallback** to fill gaps and surface NEW finds. Discovery rows whose
    source URL is already covered by a seed are dropped, so the seed's
    authoritative text wins and there are no duplicates.

    Returns (rows, run_meta) exactly like the other paths.
    """

    from discovery.metadata import canonicalize_url

    display = economy_display_name(economy)
    code = economy_code(economy)

    # 1) Seed pass — cached official texts (reproducible, offline).
    seed_rows, seed_meta = await run_library(
        economy, pillar, provider_name=provider_name, indicators=indicators,
    )
    covered = {
        canonicalize_url(r.source_url) for r in seed_rows if r.source_url
    }

    # 2) Fallback pass — live discovery, minus anything a seed already covered.
    disc_rows, disc_meta = await discover_and_extract(
        economy, pillar,
        provider_name=provider_name, indicators=indicators,
        limit=limit, browser_mode=browser_mode, max_documents=max_documents,
    )
    fresh_rows = [
        r for r in disc_rows
        if not r.source_url or canonicalize_url(r.source_url) not in covered
    ]
    deduped = len(disc_rows) - len(fresh_rows)

    rows = seed_rows + fresh_rows
    meta = {
        "economy": display,
        "economy_code": code,
        "pillar": pillar,
        "provider": seed_meta.get("provider") or disc_meta.get("provider"),
        "retrieval_strategy": "seed_first",
        "retrieval_mode": "seed_first_with_live_discovery",
        "seed_provisions": len(seed_rows),
        "discovery_provisions": len(fresh_rows),
        "discovery_duplicates_dropped": deduped,
        "laws_available": seed_meta.get("laws_available", 0),
        "candidates_found": disc_meta.get("candidates_found", 0),
        "documents_processed": (
            seed_meta.get("documents_processed", 0)
            + disc_meta.get("documents_processed", 0)
        ),
        "provisions_mapped": len(rows),
        "evidence_counts": {
            "seed": len(seed_rows),
            "live_discovered": len(fresh_rows),
            "fixture": 0,
        },
        "warnings": [*seed_meta.get("warnings", []), *disc_meta.get("warnings", [])],
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
    from providers import resolve_provider
    from services.extraction import run_extraction

    display = economy_display_name(economy)
    code = economy_code(economy)
    provider = resolve_provider(provider_name)

    pdf_result = read_pdf(pdf_path, source_url=pdf_path)
    text = "\n".join(getattr(pdf_result, "pages", []) or [])
    # PdfResult reports OCR usage as ocr_ratio/ocr_pages (there is no
    # ``used_ocr`` attribute — the old getattr silently always said False,
    # so scanned documents lost their audit metadata).
    ocr_ratio = float(getattr(pdf_result, "ocr_ratio", 0.0) or 0.0)
    mean_conf = getattr(pdf_result, "mean_conf", None)
    doc_meta = {
        "quality": "unknown",
        "retrieval_method": "provided_pdf",
        "pdf_is_scanned": ocr_ratio > 0.0,
        "ocr_quality_cer": (round(1.0 - mean_conf, 4)
                            if ocr_ratio > 0.0 and mean_conf is not None else None),
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
