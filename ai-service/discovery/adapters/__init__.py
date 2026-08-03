"""Discovery adapter registry."""

from __future__ import annotations

from .australia import AustraliaLegislationAdapter
from .base import DiscoveryAdapter
from .china import ChinaFlkAdapter
from .india_code import IndiaCodeAdapter
from .indonesia_bpk import IndonesiaBpkAdapter
from .malaysia import MalaysiaLomAdapter
from .mekong_ckan import MekongCkanAdapter
from .mongolia_legalinfo import MongoliaLegalinfoAdapter
from .official_index import OfficialIndexAdapter
from .russia_pravo import RussiaPravoAdapter
from .search_engine import FixtureSearchAdapter, SearchEngineAdapter
from .singapore import SingaporeSsoAdapter
from .thailand import ThailandOcsAdapter


def get_adapter(name: str) -> DiscoveryAdapter:
    adapters: dict[str, DiscoveryAdapter] = {
        "australia_legislation": AustraliaLegislationAdapter(),
        "china_flk": ChinaFlkAdapter(),
        "india_code": IndiaCodeAdapter(),
        "indonesia_bpk": IndonesiaBpkAdapter(),
        "malaysia_lom": MalaysiaLomAdapter(),
        "mekong_ckan": MekongCkanAdapter(),
        "mongolia_legalinfo": MongoliaLegalinfoAdapter(),
        "official_index": OfficialIndexAdapter(),
        "russia_pravo": RussiaPravoAdapter(),
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
    "IndiaCodeAdapter",
    "IndonesiaBpkAdapter",
    "MalaysiaLomAdapter",
    "MekongCkanAdapter",
    "MongoliaLegalinfoAdapter",
    "OfficialIndexAdapter",
    "RussiaPravoAdapter",
    "SearchEngineAdapter",
    "SingaporeSsoAdapter",
    "ThailandOcsAdapter",
    "get_adapter",
]
