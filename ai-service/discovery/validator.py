"""Lightweight validation for live Discovery candidates."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .metadata import infer_indicator_matches
from .schemas import DiscoverySearchRequest, LegalCandidate

FetchDocumentText = Callable[[str, str], Awaitable[Any]]

DEFAULT_VALIDATION_LIMIT = 5
MAX_VALIDATION_TEXT_CHARS = 12000
DEFAULT_VALIDATION_TIMEOUT_SECONDS = 8.0


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
        except Exception as exc:
            return self._validation_failed(candidate, f"Validation fetch failed: {exc}")

        try:
            text = str(getattr(document, "text", "") or "")
            sample = text[:MAX_VALIDATION_TEXT_CHARS]
            quality = getattr(document, "quality", None)
            quality_status = str(getattr(quality, "status", "") or "")
            quality_warnings = list(getattr(quality, "warnings", []) or [])
            quality_char_count = int(getattr(quality, "char_count", len(sample)) or 0)

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
            )

            if matched_indicators:
                return candidate.model_copy(update={
                    "validation_status": "verified",
                    "validation_metadata": validation_metadata,
                    "matched_indicators": sorted(set(candidate.matched_indicators + matched_indicators)),
                    "matched_pillars": sorted(set(candidate.matched_pillars + matched_pillars)),
                    "reasons": _append_many_unique(
                        reasons,
                        ["fetched text validates requested indicators"] + match_reasons[:2],
                    ),
                })

            warnings = list(candidate.warnings)
            warnings = _append_many_unique(
                warnings,
                ["Fetched text did not match requested discovery indicator terms."] + quality_warnings[:2],
            )
            status = "failed" if quality_status in {"empty", "error_page"} else "weak"
            return candidate.model_copy(update={
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
    error: str = "",
) -> dict[str, Any]:
    return {
        "content_type": content_type,
        "quality_status": quality_status,
        "char_count": char_count,
        "matched_indicators": matched_indicators or [],
        "error": error,
    }


def _append_unique(items: list[str], item: str) -> list[str]:
    return list(dict.fromkeys(items + [item]))


def _append_many_unique(items: list[str], additions: list[str]) -> list[str]:
    return list(dict.fromkeys(items + [item for item in additions if item]))
