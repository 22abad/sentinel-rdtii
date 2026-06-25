"""Candidate deduplication helpers."""

from __future__ import annotations

import re

from .metadata import canonicalize_url
from .schemas import LegalCandidate


def normalize_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.casefold()).strip()


def merge_candidates(primary: LegalCandidate, duplicate: LegalCandidate) -> LegalCandidate:
    primary.matched_indicators = sorted(set(primary.matched_indicators) | set(duplicate.matched_indicators))
    primary.matched_pillars = sorted(set(primary.matched_pillars) | set(duplicate.matched_pillars))
    primary.reasons = list(dict.fromkeys(primary.reasons + duplicate.reasons + ["duplicate candidate merged"]))
    primary.warnings = list(dict.fromkeys(primary.warnings + duplicate.warnings))
    if len(duplicate.snippet) > len(primary.snippet):
        primary.snippet = duplicate.snippet
    if not primary.last_update and duplicate.last_update:
        primary.last_update = duplicate.last_update
    if not primary.language and duplicate.language:
        primary.language = duplicate.language
    return primary


def dedupe_candidates(candidates: list[LegalCandidate]) -> list[LegalCandidate]:
    by_key: dict[tuple[str, ...], LegalCandidate] = {}
    ordered: list[LegalCandidate] = []

    for candidate in candidates:
        keys = dedupe_keys(candidate)
        existing = next((by_key[key] for key in keys if key in by_key), None)
        if existing:
            merge_candidates(existing, candidate)
            for key in keys:
                by_key[key] = existing
            continue
        for key in keys:
            by_key[key] = candidate
        ordered.append(candidate)
    return ordered


def dedupe_keys(candidate: LegalCandidate) -> list[tuple[str, ...]]:
    keys = [
        (
            "url-title-domain",
            canonicalize_url(candidate.url),
            normalize_title(candidate.title),
            candidate.source_domain,
        )
    ]
    if candidate.external_id:
        keys.append((
            "external-id",
            candidate.country_code,
            candidate.source_adapter or candidate.source_name or candidate.source_domain,
            candidate.external_id.casefold(),
        ))
    return keys
