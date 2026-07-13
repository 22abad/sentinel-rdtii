"""Base interface for Discovery Agent search adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from discovery.schemas import LegalSourceConfig, RawSearchHit


class DiscoveryAdapter(ABC):
    name: str

    @abstractmethod
    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        ...
