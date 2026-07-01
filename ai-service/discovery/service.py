"""Discovery Agent orchestration service."""

from __future__ import annotations

import asyncio
import time

from .adapters import get_adapter
from .dedupe import dedupe_candidates
from .metadata import normalize_hit
from .query_builder import build_queries
from .ranker import rank_candidates
from .registry import get_country_registry
from .schemas import DiscoverySearchRequest, DiscoverySearchResponse, LegalCandidate, LegalSourceConfig


class DiscoveryService:
    async def search(self, request: DiscoverySearchRequest) -> DiscoverySearchResponse:
        started = time.perf_counter()
        country_registry = get_country_registry(request.country_code)
        default_languages = list(country_registry.get("languages", []))
        all_sources = [
            LegalSourceConfig(**{**dict(source), "country_code": request.country_code})
            for source in country_registry.get("sources", [])
        ]
        active_languages = request.languages or default_languages
        sources, skipped_sources = self._select_sources(request, all_sources, default_languages)
        source_queries = build_queries(request, sources)
        raw_hits_by_source, adapter_failures = await self._run_adapters(request, sources, source_queries)

        candidates: list[LegalCandidate] = []
        adapter_warnings: list[str] = []
        raw_hit_count = 0
        for source in sources:
            raw_hits = raw_hits_by_source.get(source.name, [])
            raw_hit_count += len(raw_hits)
            for hit in raw_hits:
                adapter_warnings.extend(hit.warnings)
                candidates.append(self._filter_candidate_matches(normalize_hit(request.country_code, source, hit), request))

        deduped = dedupe_candidates(candidates)
        relevant_candidates, filtered_low_relevance = self._filter_relevant_candidates(deduped, sources)
        ranked = rank_candidates(relevant_candidates, sources)[: request.limit]
        all_queries = [query for queries in source_queries.values() for query in queries]

        mode = "mock_no_network" if request.browser_mode == "mock" else "auto_with_adapter_fallbacks"
        return DiscoverySearchResponse(
            country_code=request.country_code,
            queries=all_queries,
            candidates=ranked,
            diagnostics={
                "adapters_used": sorted({source.adapter for source in sources}),
                "raw_hits": raw_hit_count,
                "deduped_hits": len(deduped),
                "filtered_low_relevance": filtered_low_relevance,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "mode": mode,
                "source_mode": request.source_mode,
                "warnings": sorted(set(adapter_warnings + adapter_failures)),
                "languages": active_languages,
                "sources_considered": len(sources),
                "sources_skipped": skipped_sources,
            },
        )

    def _select_sources(
        self,
        request: DiscoverySearchRequest,
        sources: list[LegalSourceConfig],
        default_languages: list[str],
    ) -> tuple[list[LegalSourceConfig], list[str]]:
        selected: list[LegalSourceConfig] = []
        skipped: list[str] = []
        requested_languages = set(request.languages)

        for source in sources:
            source_languages = set(source.languages or default_languages)
            if requested_languages and source_languages and not requested_languages.intersection(source_languages):
                skipped.append(f"{source.name} (language mismatch)")
                continue

            if not self._source_matches_request_scope(source, request):
                skipped.append(f"{source.name} (pillar/indicator mismatch)")
                continue

            is_secondary = source.source_grade == "secondary"
            if request.source_mode == "official_only" and is_secondary:
                skipped.append(f"{source.name} (secondary source)")
                continue
            if request.source_mode == "official_first" and is_secondary and not request.include_secondary_leads:
                skipped.append(f"{source.name} (secondary source)")
                continue
            selected.append(source)

        return selected, skipped

    def _source_matches_request_scope(
        self,
        source: LegalSourceConfig,
        request: DiscoverySearchRequest,
    ) -> bool:
        if not source.pillars and not source.indicators:
            return True

        requested_pillars = set(request.pillars)
        requested_indicators = set(request.indicators)
        source_pillars = set(source.pillars)
        source_indicators = set(source.indicators)
        source_indicator_pillars = {
            int(indicator.split(".", 1)[0])
            for indicator in source_indicators
        }

        if requested_indicators:
            requested_indicator_pillars = {
                int(indicator.split(".", 1)[0])
                for indicator in requested_indicators
            }
            return (
                bool(source_indicators.intersection(requested_indicators))
                or bool(source_pillars.intersection(requested_indicator_pillars))
            )

        return bool(source_pillars.intersection(requested_pillars)) or bool(
            source_indicator_pillars.intersection(requested_pillars)
        )

    def _filter_candidate_matches(
        self,
        candidate: LegalCandidate,
        request: DiscoverySearchRequest,
    ) -> LegalCandidate:
        allowed_indicators = set(request.indicators)
        allowed_pillars = set(request.pillars)
        if allowed_indicators:
            matched_indicators = [
                indicator
                for indicator in candidate.matched_indicators
                if indicator in allowed_indicators
            ]
        else:
            matched_indicators = [
                indicator
                for indicator in candidate.matched_indicators
                if int(indicator.split(".", 1)[0]) in allowed_pillars
            ]
        matched_pillars = sorted({int(indicator.split(".", 1)[0]) for indicator in matched_indicators})
        return candidate.model_copy(update={
            "matched_indicators": matched_indicators,
            "matched_pillars": matched_pillars,
        })

    def _filter_relevant_candidates(
        self,
        candidates: list[LegalCandidate],
        sources: list[LegalSourceConfig],
    ) -> tuple[list[LegalCandidate], int]:
        source_by_name = {source.name: source for source in sources}
        relevant: list[LegalCandidate] = []
        filtered = 0

        for candidate in candidates:
            source = source_by_name.get(candidate.source_name)
            is_known_law_database = (
                candidate.source_grade == "primary"
                and source is not None
                and source.priority >= 100
            )
            has_indicator_match = bool(candidate.matched_indicators or candidate.matched_pillars)
            if has_indicator_match or is_known_law_database:
                relevant.append(candidate)
                continue
            filtered += 1

        return relevant, filtered

    async def _run_adapters(
        self,
        request: DiscoverySearchRequest,
        sources: list[LegalSourceConfig],
        source_queries: dict[str, list[str]],
    ) -> tuple[dict[str, list], list[str]]:
        async def run_one(source: LegalSourceConfig) -> tuple[str, list, str]:
            adapter = get_adapter(source.adapter)
            try:
                hits = await adapter.search(
                    country_code=request.country_code,
                    source=source,
                    queries=source_queries.get(source.name, []),
                    limit=request.limit,
                    browser_mode=request.browser_mode,
                )
                return source.name, hits, ""
            except Exception as exc:
                return source.name, [], f"{source.adapter} failed for {source.name}: {exc}"

        pairs = await asyncio.gather(*(run_one(source) for source in sources))
        hits_by_source = {source_name: hits for source_name, hits, _warning in pairs}
        warnings = [warning for _source_name, _hits, warning in pairs if warning]
        return hits_by_source, warnings
