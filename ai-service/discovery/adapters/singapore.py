"""Singapore discovery adapters."""

from __future__ import annotations

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter


class SingaporeSsoAdapter(DiscoveryAdapter):
    name = "singapore_sso"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        hits = await FixtureSearchAdapter(name=self.name).search(
            country_code=country_code,
            source=source,
            queries=queries,
            limit=limit,
            browser_mode=browser_mode,
        )
        if browser_mode != "mock":
            hits = [
                hit.model_copy(update={
                    "warnings": hit.warnings + [
                        "singapore_sso live site search is not implemented yet; returned official fixture fallback."
                    ]
                })
                for hit in hits
            ]
        return hits
