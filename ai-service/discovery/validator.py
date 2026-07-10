"""Lightweight validation for live Discovery candidates."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from .metadata import infer_indicator_matches
from .schemas import DiscoverySearchRequest, LegalCandidate

FetchDocumentText = Callable[[str, str], Awaitable[Any]]

DEFAULT_VALIDATION_LIMIT = 5
MAX_VALIDATION_TEXT_CHARS = 200000
DEFAULT_VALIDATION_TIMEOUT_SECONDS = 30.0
FALLBACK_FETCH_METHOD_PREFIXES = ("wayback",)
FALLBACK_FETCH_METHODS = {"google_cache"}
LIVE_FETCH_METHODS = {
    "crawler",
    "download",
    "flk_official_api_pdf",
    "http_fallback",
    "http_fallback_embedded_html",
    "http_fallback_embedded_pdf",
    "http_fallback_pdf",
    "ocs.go.th",
    "opencli",
    "playwright",
}
BLOCKING_QUALITY_WARNING_TERMS = (
    "error, block, or challenge page",
    "navigation-heavy",
    "captcha",
    "cloudflare",
    "page not found",
    "access denied",
)


class CandidateValidator:
    def __init__(
        self,
        *,
        fetch_document_text: FetchDocumentText | None = None,
        validation_limit: int = DEFAULT_VALIDATION_LIMIT,
        timeout_seconds: float = DEFAULT_VALIDATION_TIMEOUT_SECONDS,
    ) -> None:
        self._fetch_document_text = fetch_document_text
        self.validation_limit = validation_limit
        self.timeout_seconds = timeout_seconds

    async def validate(
        self,
        candidates: list[LegalCandidate],
        request: DiscoverySearchRequest,
    ) -> tuple[list[LegalCandidate], dict[str, int]]:
        selected = [
            candidate
            for candidate in candidates
            if candidate.retrieval_mode == "live"
        ][: self.validation_limit]
        if not selected:
            return candidates, {
                "validation_attempted": 0,
                "validation_verified": 0,
                "validation_failed": 0,
                "validation_weak": 0,
            }

        validated = await asyncio.gather(
            *(self._validate_one(candidate, request) for candidate in selected)
        )
        validated_by_id = {candidate.id: candidate for candidate in validated}
        next_candidates = [
            validated_by_id.get(candidate.id, candidate)
            for candidate in candidates
        ]
        status_counts = {
            "validation_attempted": len(selected),
            "validation_verified": sum(1 for candidate in validated if candidate.validation_status == "verified"),
            "validation_failed": sum(1 for candidate in validated if candidate.validation_status == "failed"),
            "validation_weak": sum(1 for candidate in validated if candidate.validation_status == "weak"),
        }
        return next_candidates, status_counts

    async def _validate_one(
        self,
        candidate: LegalCandidate,
        request: DiscoverySearchRequest,
    ) -> LegalCandidate:
        try:
            document = await self._fetch(candidate.url, request.browser_mode)
        except asyncio.TimeoutError:
            return self._validation_failed(
                candidate,
                f"Validation fetch timed out after {self.timeout_seconds:g} seconds.",
            )
        except Exception as exc:
            return self._validation_failed(candidate, f"Validation fetch failed: {exc}")

        try:
            text = str(getattr(document, "text", "") or "")
            sample = text[:MAX_VALIDATION_TEXT_CHARS]
            quality = getattr(document, "quality", None)
            quality_status = str(getattr(quality, "status", "") or "")
            quality_warnings = list(getattr(quality, "warnings", []) or [])
            quality_char_count = int(getattr(quality, "char_count", len(sample)) or 0)
            crawl_metadata = dict(getattr(document, "crawl_metadata", {}) or {})
            fetch_method = str(crawl_metadata.get("fetch_method") or "")
            document_retrieval_mode = _document_retrieval_mode(fetch_method)
            http_status = _optional_int(crawl_metadata.get("http_status"))
            tls_verified = crawl_metadata.get("tls_verified") is True
            final_url = str(crawl_metadata.get("final_url") or candidate.url)
            official_domains = _candidate_official_domains(candidate)
            final_url_official = _url_host_in_domains(final_url, official_domains)
            document_origin_domain = str(
                crawl_metadata.get("document_origin_domain") or ""
            ).casefold()
            document_origin_trusted = (
                crawl_metadata.get("document_origin_trusted") is True
                or document_origin_domain in official_domains
            )
            document_identity_match = _document_matches_candidate_identity(
                candidate,
                sample,
                str(crawl_metadata.get("title") or ""),
            )

            # Validation must be based on fetched evidence alone. Reusing the
            # search title/URL here can incorrectly verify a navigation or error
            # page merely because the candidate title contains a legal keyword.
            _matched_pillars, raw_matched_indicators, raw_match_reasons = infer_indicator_matches(
                "",
                "",
                sample,
            )
            matched_indicators, match_reasons = _filter_indicator_matches(
                raw_matched_indicators,
                raw_match_reasons,
                request,
            )
            matched_pillars = sorted({
                int(indicator.split(".", 1)[0])
                for indicator in matched_indicators
            })

            reasons = list(candidate.reasons)
            validation_metadata = _validation_metadata(
                content_type=str(getattr(document, "content_type", "") or ""),
                quality_status=quality_status,
                char_count=quality_char_count,
                matched_indicators=matched_indicators,
                quality_warnings=quality_warnings,
                final_url=final_url,
                final_url_official=final_url_official,
                fetch_method=fetch_method,
                document_retrieval_mode=document_retrieval_mode,
                http_status=http_status,
                tls_verified=tls_verified,
                document_origin_domain=document_origin_domain,
                document_origin_trusted=document_origin_trusted,
                document_identity_match=document_identity_match,
            )

            warnings = list(candidate.warnings)
            if document_retrieval_mode == "fallback":
                warnings = _append_unique(
                    warnings,
                    f"Document validation used fallback retrieval via {fetch_method or 'unknown source'}.",
                )

            if _quality_blocks_verification(quality_status, quality_warnings):
                warnings = _append_many_unique(
                    warnings,
                    ["Fetched text failed document quality checks."] + quality_warnings[:2],
                )
                return candidate.model_copy(update={
                    "retrieval_mode": "fallback" if document_retrieval_mode == "fallback" else candidate.retrieval_mode,
                    "validation_status": "failed" if quality_status in {"empty", "error_page"} else "weak",
                    "validation_metadata": validation_metadata,
                    "warnings": warnings,
                })

            if quality_status != "good":
                warnings = _append_many_unique(
                    warnings,
                    ["Fetched text quality was not good enough for verification."] + quality_warnings[:2],
                )
                return candidate.model_copy(update={
                    "retrieval_mode": "fallback" if document_retrieval_mode == "fallback" else candidate.retrieval_mode,
                    "validation_status": "weak",
                    "validation_metadata": validation_metadata,
                    "warnings": warnings,
                })

            transport_warnings: list[str] = []
            if document_retrieval_mode == "unknown":
                transport_warnings.append(
                    f"Unknown document fetch method cannot be treated as live: {fetch_method or 'missing'}."
                )
            if http_status is None:
                transport_warnings.append("Document fetch did not report an HTTP status.")
            elif not 200 <= http_status < 400:
                transport_warnings.append(f"Document fetch returned HTTP {http_status}.")
            if not tls_verified:
                transport_warnings.append("Document fetch did not prove successful TLS verification.")
            if document_retrieval_mode == "live" and not final_url_official:
                transport_warnings.append(
                    "Live document fetch ended outside the candidate's configured official domains."
                )
            if document_retrieval_mode == "live" and not document_origin_trusted:
                transport_warnings.append(
                    "Live document origin was not a configured or explicitly trusted domain."
                )
            if transport_warnings:
                return candidate.model_copy(update={
                    "retrieval_mode": "fallback" if document_retrieval_mode == "fallback" else candidate.retrieval_mode,
                    "validation_status": "weak",
                    "validation_metadata": validation_metadata,
                    "warnings": _append_many_unique(warnings, transport_warnings),
                })

            if not document_identity_match:
                return candidate.model_copy(update={
                    "retrieval_mode": "fallback" if document_retrieval_mode == "fallback" else candidate.retrieval_mode,
                    "validation_status": "weak",
                    "validation_metadata": validation_metadata,
                    "warnings": _append_unique(
                        warnings,
                        "Fetched text did not contain the selected candidate's law title.",
                    ),
                })

            if matched_indicators:
                return candidate.model_copy(update={
                    "retrieval_mode": "fallback" if document_retrieval_mode == "fallback" else candidate.retrieval_mode,
                    "validation_status": "verified",
                    "validation_metadata": validation_metadata,
                    "matched_indicators": sorted(set(candidate.matched_indicators + matched_indicators)),
                    "matched_pillars": sorted(set(candidate.matched_pillars + matched_pillars)),
                    "reasons": _append_many_unique(
                        reasons,
                        ["fetched text validates requested indicators"] + match_reasons[:2],
                    ),
                    "warnings": warnings,
                })

            warnings = _append_many_unique(
                warnings,
                ["Fetched text did not match requested discovery indicator terms."] + quality_warnings[:2],
            )
            status = "failed" if quality_status in {"empty", "error_page"} else "weak"
            return candidate.model_copy(update={
                "retrieval_mode": "fallback" if document_retrieval_mode == "fallback" else candidate.retrieval_mode,
                "validation_status": status,
                "validation_metadata": validation_metadata,
                "warnings": warnings,
            })
        except Exception as exc:
            return self._validation_failed(candidate, f"Validation processing failed: {exc}")

    async def _fetch(self, source_url: str, browser_mode: str) -> Any:
        if self._fetch_document_text is not None:
            return await asyncio.wait_for(
                self._fetch_document_text(source_url, browser_mode),
                timeout=self.timeout_seconds,
            )

        from services.document_fetch import fetch_document_text

        return await asyncio.wait_for(
            fetch_document_text(source_url, browser_mode=browser_mode),
            timeout=self.timeout_seconds,
        )

    def _validation_failed(self, candidate: LegalCandidate, warning: str) -> LegalCandidate:
        return candidate.model_copy(update={
            "validation_status": "failed",
            "validation_metadata": _validation_metadata(error=warning),
            "warnings": _append_unique(candidate.warnings, warning),
        })


def _filter_indicator_matches(
    indicators: list[str],
    reasons: list[str],
    request: DiscoverySearchRequest,
) -> tuple[list[str], list[str]]:
    allowed_pillars = set(request.pillars)
    allowed_indicators = set(request.indicators)
    kept_indicators: list[str] = []
    kept_reasons: list[str] = []

    for index, indicator in enumerate(indicators):
        pillar = _indicator_pillar(indicator)
        if pillar is None:
            continue
        if pillar not in allowed_pillars:
            continue
        if allowed_indicators and indicator not in allowed_indicators:
            continue
        kept_indicators.append(indicator)
        reason = reasons[index] if index < len(reasons) else ""
        if reason:
            kept_reasons.append(reason)

    return kept_indicators, kept_reasons


def _indicator_pillar(indicator: str) -> int | None:
    try:
        return int(indicator.split(".", 1)[0])
    except (TypeError, ValueError):
        return None


def _validation_metadata(
    *,
    content_type: str = "",
    quality_status: str = "",
    char_count: int = 0,
    matched_indicators: list[str] | None = None,
    quality_warnings: list[str] | None = None,
    final_url: str = "",
    final_url_official: bool = False,
    fetch_method: str = "",
    document_retrieval_mode: str = "",
    http_status: int | None = None,
    tls_verified: bool = False,
    document_origin_domain: str = "",
    document_origin_trusted: bool = False,
    document_identity_match: bool = False,
    error: str = "",
) -> dict[str, Any]:
    return {
        "content_type": content_type,
        "quality_status": quality_status,
        "char_count": char_count,
        "matched_indicators": matched_indicators or [],
        "quality_warnings": quality_warnings or [],
        "final_url": final_url,
        "final_url_official": final_url_official,
        "fetch_method": fetch_method,
        "document_retrieval_mode": document_retrieval_mode,
        "http_status": http_status,
        "tls_verified": tls_verified,
        "document_origin_domain": document_origin_domain,
        "document_origin_trusted": document_origin_trusted,
        "document_identity_match": document_identity_match,
        "error": error,
    }


def _document_retrieval_mode(fetch_method: str) -> str:
    normalized = fetch_method.strip().casefold()
    if normalized in FALLBACK_FETCH_METHODS or normalized.startswith(FALLBACK_FETCH_METHOD_PREFIXES):
        return "fallback"
    if normalized in LIVE_FETCH_METHODS:
        return "live"
    return "unknown"


def _document_matches_candidate_identity(
    candidate: LegalCandidate,
    text: str,
    fetched_title: str,
) -> bool:
    expected = _normalize_identity_text(candidate.title)
    if len(expected) < 6:
        # Acronym-only titles (for example "PDPA") are legitimate identities,
        # but generic short labels such as "Act" or "Law" are not.
        if (
            len(expected) < 3
            or " " in expected
            or expected in {"act", "law", "code", "bill"}
        ):
            return False
        fetched_tokens = set(_normalize_identity_text(f"{fetched_title} {text}").split())
        return expected in fetched_tokens
    fetched_identity = _normalize_identity_text(f"{fetched_title} {text}")
    return expected in fetched_identity


def _candidate_official_domains(candidate: LegalCandidate) -> set[str]:
    domains = {domain.casefold() for domain in candidate.official_domains if domain}
    if candidate.source_domain:
        domains.add(candidate.source_domain.casefold())
    try:
        candidate_host = (urlsplit(candidate.url).hostname or "").casefold()
    except ValueError:
        candidate_host = ""
    if candidate_host:
        domains.add(candidate_host)
    return domains


def _url_host_in_domains(url: str, domains: set[str]) -> bool:
    try:
        host = (urlsplit(url).hostname or "").casefold()
    except ValueError:
        return False
    return bool(host and host in domains)


def _normalize_identity_text(value: str) -> str:
    return re.sub(
        r"[^a-z0-9\u0e00-\u0e7f\u4e00-\u9fff]+",
        " ",
        value.casefold(),
    ).strip()


def _quality_blocks_verification(quality_status: str, warnings: list[str]) -> bool:
    if quality_status in {"empty", "error_page"}:
        return True
    warning_text = " ".join(warnings).casefold()
    return any(term in warning_text for term in BLOCKING_QUALITY_WARNING_TERMS)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _append_unique(items: list[str], item: str) -> list[str]:
    return list(dict.fromkeys(items + [item]))


def _append_many_unique(items: list[str], additions: list[str]) -> list[str]:
    return list(dict.fromkeys(items + [item for item in additions if item]))
