"""Discovery adapter registry."""

from __future__ import annotations

from .base import DiscoveryAdapter
from .china import ChinaFlkAdapter
from .search_engine import FixtureSearchAdapter, SearchEngineAdapter
from .singapore import SingaporeSsoAdapter
from .thailand import ThailandOcsAdapter


def get_adapter(name: str) -> DiscoveryAdapter:
    adapters: dict[str, DiscoveryAdapter] = {
        "china_flk": ChinaFlkAdapter(),
        "search_engine": SearchEngineAdapter(),
        "singapore_sso": SingaporeSsoAdapter(),
        "thailand_ocs": ThailandOcsAdapter(),
    }
    return adapters.get(name, SearchEngineAdapter())


__all__ = [
    "ChinaFlkAdapter",
    "DiscoveryAdapter",
    "FixtureSearchAdapter",
    "SearchEngineAdapter",
    "SingaporeSsoAdapter",
    "ThailandOcsAdapter",
    "get_adapter",
]
