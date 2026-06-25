"""Thailand OCS discovery adapter."""

from __future__ import annotations

import re
from typing import Any

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter


class ThailandOcsAdapter(DiscoveryAdapter):
    name = "thailand_ocs"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if browser_mode == "mock":
            return await FixtureSearchAdapter(name=self.name).search(
                country_code=country_code,
                source=source,
                queries=queries,
                limit=limit,
                browser_mode=browser_mode,
            )

        try:
            from crawler import search_ocs_law

            rows = await self._search_queries(search_ocs_law, queries, limit)
            if rows:
                return rows
            warning = "thailand_ocs live search returned no results; returned fixture fallback."
        except Exception as exc:
            warning = f"thailand_ocs live search failed: {exc}; returned fixture fallback."

        fallback = await FixtureSearchAdapter(name=self.name).search(
            country_code=country_code,
            source=source,
            queries=queries,
            limit=limit,
            browser_mode=browser_mode,
        )
        return [
            hit.model_copy(update={"warnings": hit.warnings + [warning]})
            for hit in fallback
        ]

    async def _search_queries(self, search_ocs_law: Any, queries: list[str], limit: int) -> list[RawSearchHit]:
        hits: list[RawSearchHit] = []
        seen_doc_ids: set[str] = set()

        for query in queries:
            search_term = _strip_site_filter(query)
            rows = await search_ocs_law(search_term, max_results=max(1, min(limit, 20)))
            for row in rows:
                doc_id = str(row.get("doc_id") or "").strip()
                url = str(row.get("doc_url") or row.get("url") or "").strip()
                title = str(row.get("title") or "").strip()
                if not url or doc_id in seen_doc_ids:
                    continue
                if doc_id:
                    seen_doc_ids.add(doc_id)
                hits.append(RawSearchHit(
                    title=title,
                    url=url,
                    snippet=" | ".join(
                        str(row.get(key) or "").strip()
                        for key in ("status", "published_date", "year", "source")
                        if row.get(key)
                    ),
                    source_adapter=self.name,
                    query=search_term,
                    position=len(hits) + 1,
                    external_id=doc_id,
                    raw=dict(row),
                ))
                if len(hits) >= limit:
                    return hits
        return hits


def _strip_site_filter(query: str) -> str:
    return re.sub(r"\bsite:\S+\s*", "", query).strip()
