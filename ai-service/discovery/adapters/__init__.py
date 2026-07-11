"""Discovery adapter registry."""

from __future__ import annotations

from .australia import AustraliaLegislationAdapter
from .base import DiscoveryAdapter
from .china import ChinaFlkAdapter
from .malaysia import MalaysiaLomAdapter
from .official_index import OfficialIndexAdapter
from .search_engine import FixtureSearchAdapter, SearchEngineAdapter
from .singapore import SingaporeSsoAdapter
from .thailand import ThailandOcsAdapter


def get_adapter(name: str) -> DiscoveryAdapter:
    adapters: dict[str, DiscoveryAdapter] = {
        "australia_legislation": AustraliaLegislationAdapter(),
        "china_flk": ChinaFlkAdapter(),
        "malaysia_lom": MalaysiaLomAdapter(),
        "official_index": OfficialIndexAdapter(),
        "search_engine": SearchEngineAdapter(),
        "singapore_sso": SingaporeSsoAdapter(),
        "thailand_ocs": ThailandOcsAdapter(),
    }
    return adapters.get(name, SearchEngineAdapter())


__all__ = [
    "AustraliaLegislationAdapter",
    "ChinaFlkAdapter",
    "DiscoveryAdapter",
    "FixtureSearchAdapter",
    "MalaysiaLomAdapter",
    "OfficialIndexAdapter",
    "SearchEngineAdapter",
    "SingaporeSsoAdapter",
    "ThailandOcsAdapter",
    "get_adapter",
]
