"""China National Laws and Regulations Database discovery adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter, strip_site_filter


class ChinaFlkAdapter(DiscoveryAdapter):
    name = "china_flk"

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
            from browser_drivers import OpenCliBrowserDriver

            driver = OpenCliBrowserDriver()
            rows = await self._search_queries(driver, queries, limit)
            if rows:
                return rows
            warning = "china_flk live search returned no results; returned fixture fallback."
        except Exception as exc:
            warning = f"china_flk live search failed: {exc}; returned fixture fallback."

        fallback = await FixtureSearchAdapter(name=self.name, retrieval_mode="fallback").search(
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

    async def _search_queries(self, driver: Any, queries: list[str], limit: int) -> list[RawSearchHit]:
        hits: list[RawSearchHit] = []
        seen_urls: set[str] = set()

        for query in queries:
            search_term = strip_site_filter(query)
            rows = await driver.search_gov_law(search_term, limit=max(1, min(limit, 20)))
            for row in rows:
                url = str(row.get("url") or "").strip()
                title = str(row.get("title") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                snippet_parts = [
                    str(row.get("type") or "").strip(),
                    str(row.get("department") or "").strip(),
                    str(row.get("status") or "").strip(),
                    str(row.get("publish_date") or "").strip(),
                ]
                hits.append(RawSearchHit(
                    title=title,
                    url=url,
                    snippet=" | ".join(part for part in snippet_parts if part),
                    source_adapter=self.name,
                    query=search_term,
                    position=int(row.get("rank") or len(hits) + 1),
                    external_id=_external_id_from_url(url),
                    raw=dict(row),
                ))
                if len(hits) >= limit:
                    return hits
        return hits

def _external_id_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.query:
        return parsed.query
    path_leaf = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return path_leaf or url
