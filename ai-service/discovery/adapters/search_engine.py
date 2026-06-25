"""Search adapter fallbacks for the Discovery Agent.

The generic search adapter intentionally avoids scraping public search engines
without an explicit configured backend. In development and CI it can return
fixture hits so the Discovery API contract remains stable.
"""

from __future__ import annotations

import os

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter


class FixtureSearchAdapter(DiscoveryAdapter):
    def __init__(self, name: str = "search_engine") -> None:
        self.name = name

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        hits = _fixture_hits(country_code, source, self.name)
        query = queries[0] if queries else ""
        return [
            hit.model_copy(update={
                "source_adapter": self.name,
                "source_name": source.name,
                "query": query,
                "position": idx + 1,
            })
            for idx, hit in enumerate(hits[:limit])
        ]


class SearchEngineAdapter(DiscoveryAdapter):
    name = "search_engine"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if browser_mode == "mock" or os.getenv("DISCOVERY_USE_FIXTURES", "").lower() in {"1", "true", "yes"}:
            return await FixtureSearchAdapter(name=self.name).search(
                country_code=country_code,
                source=source,
                queries=queries,
                limit=limit,
                browser_mode=browser_mode,
            )

        return [
            hit.model_copy(update={
                "warnings": hit.warnings + [
                    "Generic live site search is not configured; returned fixture fallback."
                ]
            })
            for hit in await FixtureSearchAdapter(name=self.name).search(
                country_code=country_code,
                source=source,
                queries=queries,
                limit=limit,
                browser_mode=browser_mode,
            )
        ]


def _fixture_hits(country_code: str, source: LegalSourceConfig, adapter_name: str) -> list[RawSearchHit]:
    domain = source.domains[0]
    country_code = country_code.upper()

    fixtures: dict[str, dict[str, list[RawSearchHit]]] = {
        "SGP": {
            "sso.agc.gov.sg": [
                RawSearchHit(
                    title="Personal Data Protection Act 2012",
                    url="https://sso.agc.gov.sg/Act/PDPA2012",
                    snippet="An Act to govern the collection, use, disclosure and care of personal data, including transfers outside Singapore.",
                    external_id="PDPA2012",
                ),
                RawSearchHit(
                    title="Cybersecurity Act 2018",
                    url="https://sso.agc.gov.sg/Act/CA2018",
                    snippet="An Act to require cybersecurity duties for critical information infrastructure.",
                    external_id="CA2018",
                ),
            ],
            "pdpc.gov.sg": [
                RawSearchHit(
                    title="Advisory Guidelines on Key Concepts in the PDPA",
                    url="https://www.pdpc.gov.sg/guidelines-and-consultation/2020/03/advisory-guidelines-on-key-concepts-in-the-pdpa",
                    snippet="Guidance on consent, notification, data protection officers, and transfer of personal data outside Singapore.",
                )
            ],
        },
        "CHN": {
            "flk.npc.gov.cn": [
                RawSearchHit(
                    title="中华人民共和国个人信息保护法",
                    url="https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3YjY4M2JhYjAxN2I5MTYxYzQyMjA4M2I%3D",
                    snippet="个人信息处理者向境外提供个人信息，应当具备个人信息保护认证、标准合同或者安全评估等条件。",
                    external_id="pipl",
                ),
                RawSearchHit(
                    title="中华人民共和国网络安全法",
                    url="https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE1YmI3OTY2YTAxNWJiZGMwM2U2YjA0M2I%3D",
                    snippet="网络运营者应当按照网络安全等级保护制度要求履行安全保护义务。",
                    external_id="cybersecurity-law",
                ),
            ],
            "gov.cn": [
                RawSearchHit(
                    title="促进和规范数据跨境流动规定",
                    url="https://www.gov.cn/zhengce/zhengceku/202403/content_6940154.htm",
                    snippet="对数据出境安全评估、个人信息出境标准合同和个人信息保护认证作出规定。",
                )
            ],
            "cac.gov.cn": [
                RawSearchHit(
                    title="数据出境安全评估办法",
                    url="https://www.cac.gov.cn/2022-07/07/c_1658811536396503.htm",
                    snippet="数据处理者向境外提供重要数据和个人信息应当申报数据出境安全评估。",
                )
            ],
        },
        "THA": {
            "ocs.go.th": [
                RawSearchHit(
                    title="Personal Data Protection Act B.E. 2562",
                    url="https://www.ocs.go.th/law/PDPA2562",
                    snippet="Official legal text for personal data protection, controller duties, data protection officer, and cross-border transfer.",
                    external_id="PDPA2562",
                )
            ],
            "etda.or.th": [
                RawSearchHit(
                    title="Electronic Transactions Act",
                    url="https://www.etda.or.th/th/Useful-Resource/Knowledge-Sharing/Electronic-Transactions-Act.aspx",
                    snippet="Official information about electronic transactions law and retention of electronic records.",
                )
            ],
            "pdpc.or.th": [
                RawSearchHit(
                    title="Personal Data Protection Committee Notifications",
                    url="https://www.pdpc.or.th/laws",
                    snippet="Official notifications and guidelines under Thailand personal data protection framework.",
                )
            ],
        },
    }

    return fixtures.get(country_code, {}).get(domain, [
        RawSearchHit(
            title=f"{source.name} legal source",
            url=source.base_url,
            snippet="No live adapter is configured yet; this Phase 1 mock result preserves the discovery response contract.",
            warnings=[f"{adapter_name} is running in no-network mock mode"],
        )
    ])
