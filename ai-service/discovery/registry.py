"""Official legal-source registry for Discovery Agent MVP countries."""

from __future__ import annotations

from .schemas import LegalSourceConfig


DISCOVERY_REGISTRY: dict[str, dict] = {
    "CHN": {
        "languages": ["zh", "en"],
        "sources": [
            {
                "name": "National Laws and Regulations Database",
                "base_url": "https://flk.npc.gov.cn",
                "domains": ["flk.npc.gov.cn"],
                "adapter": "china_flk",
                "source_grade": "primary",
                "languages": ["zh"],
                "priority": 100,
                "notes": "Official national laws and regulations database",
            },
            {
                "name": "State Council",
                "base_url": "https://www.gov.cn",
                "domains": ["gov.cn", "www.gov.cn"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["zh", "en"],
                "priority": 90,
            },
            {
                "name": "Cyberspace Administration of China",
                "base_url": "https://www.cac.gov.cn",
                "domains": ["cac.gov.cn", "www.cac.gov.cn"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["zh"],
                "priority": 90,
            },
        ],
    },
    "SGP": {
        "languages": ["en"],
        "sources": [
            {
                "name": "Singapore Statutes Online",
                "base_url": "https://sso.agc.gov.sg",
                "domains": ["sso.agc.gov.sg"],
                "adapter": "singapore_sso",
                "source_grade": "primary",
                "languages": ["en"],
                "priority": 100,
            },
            {
                "name": "Personal Data Protection Commission",
                "base_url": "https://www.pdpc.gov.sg",
                "domains": ["pdpc.gov.sg", "www.pdpc.gov.sg"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["en"],
                "priority": 85,
            },
            {
                "name": "Infocomm Media Development Authority",
                "base_url": "https://www.imda.gov.sg",
                "domains": ["imda.gov.sg", "www.imda.gov.sg"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["en"],
                "priority": 80,
            },
        ],
    },
    "THA": {
        "languages": ["th", "en"],
        "sources": [
            {
                "name": "Office of the Council of State",
                "base_url": "https://www.ocs.go.th",
                "domains": ["ocs.go.th", "searchlaw.ocs.go.th"],
                "adapter": "thailand_ocs",
                "source_grade": "primary",
                "languages": ["th", "en"],
                "priority": 100,
            },
            {
                "name": "Electronic Transactions Development Agency",
                "base_url": "https://www.etda.or.th",
                "domains": ["etda.or.th", "www.etda.or.th"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["th", "en"],
                "priority": 85,
            },
            {
                "name": "Personal Data Protection Committee",
                "base_url": "https://www.pdpc.or.th",
                "domains": ["pdpc.or.th", "www.pdpc.or.th"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["th", "en"],
                "priority": 85,
            },
        ],
    },
    "MYS": {
        "languages": ["en", "ms"],
        "sources": [
            {
                "name": "Attorney General's Chambers of Malaysia",
                "base_url": "https://lom.agc.gov.my",
                "domains": ["lom.agc.gov.my"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["en", "ms"],
                "priority": 100,
            },
            {
                "name": "Personal Data Protection Department",
                "base_url": "https://www.pdp.gov.my",
                "domains": ["pdp.gov.my", "www.pdp.gov.my"],
                "adapter": "search_engine",
                "source_grade": "primary",
                "languages": ["en", "ms"],
                "priority": 90,
            },
        ],
    },
}


def get_country_registry(country_code: str) -> dict:
    country_code = country_code.strip().upper()
    if country_code not in DISCOVERY_REGISTRY:
        raise KeyError(country_code)
    return DISCOVERY_REGISTRY[country_code]


def get_sources(country_code: str) -> list[LegalSourceConfig]:
    registry = get_country_registry(country_code)
    return [LegalSourceConfig(**source) for source in registry.get("sources", [])]


def get_languages(country_code: str) -> list[str]:
    return list(get_country_registry(country_code).get("languages", []))
