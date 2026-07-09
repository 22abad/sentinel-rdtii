"""Search adapter fallbacks for the Discovery Agent.

The generic search adapter intentionally avoids scraping public search engines
without an explicit configured backend. In development and CI it can return
fixture hits so the Discovery API contract remains stable.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

from discovery.schemas import LegalSourceConfig, RawSearchHit, RetrievalMode

from .base import DiscoveryAdapter


class SearchBackendConfigError(RuntimeError):
    """Raised when a configured live search backend is missing credentials."""


class SearchBackend(Protocol):
    async def search(self, query: str, limit: int) -> list[RawSearchHit]:
        ...


class FixtureSearchAdapter(DiscoveryAdapter):
    def __init__(
        self,
        name: str = "search_engine",
        retrieval_mode: RetrievalMode = "fixture",
    ) -> None:
        self.name = name
        self.retrieval_mode = retrieval_mode

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        hits = _fixture_hits(country_code, source, self.name, self.retrieval_mode)
        query = queries[0] if queries else ""
        return [
            hit.model_copy(update={
                "source_adapter": self.name,
                "source_name": source.name,
                "query": query,
                "position": idx + 1,
                "retrieval_mode": self.retrieval_mode,
            })
            for idx, hit in enumerate(hits[:limit])
        ]


class SearchEngineAdapter(DiscoveryAdapter):
    name = "search_engine"

    def __init__(self, search_backend: SearchBackend | None = None) -> None:
        self.search_backend = search_backend

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

        backend_name = _configured_search_backend()
        if self.search_backend is not None or backend_name:
            try:
                backend = self.search_backend or _build_search_backend(backend_name)
                backend_label = backend_name or backend.__class__.__name__
                hits = await self._search_live(
                    backend=backend,
                    source=source,
                    queries=queries,
                    limit=limit,
                )
                if hits:
                    return hits
                warning = f"{backend_label} live site search returned no results; returned fixture fallback."
            except Exception as exc:
                backend_label = backend_name or "configured_search_backend"
                warning = f"{backend_label} live site search failed: {exc}; returned fixture fallback."
            return await self._fixture_fallback(
                country_code=country_code,
                source=source,
                queries=queries,
                limit=limit,
                browser_mode=browser_mode,
                warning=warning,
            )

        return await self._fixture_fallback(
            country_code=country_code,
            source=source,
            queries=queries,
            limit=limit,
            browser_mode=browser_mode,
            warning="Generic live site search is not configured; returned fixture fallback.",
        )

    async def _search_live(
        self,
        *,
        backend: SearchBackend,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
    ) -> list[RawSearchHit]:
        hits: list[RawSearchHit] = []
        seen_urls: set[str] = set()
        for query in queries:
            rows = await backend.search(query, max(1, limit - len(hits)))
            for row in rows:
                if row.url in seen_urls:
                    continue
                seen_urls.add(row.url)
                hits.append(row.model_copy(update={
                    "source_adapter": self.name,
                    "source_name": source.name,
                    "query": query,
                    "position": len(hits) + 1,
                    "retrieval_mode": "live",
                }))
                if len(hits) >= limit:
                    return hits
        return hits

    async def _fixture_fallback(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str,
        warning: str,
    ) -> list[RawSearchHit]:
        return [
            hit.model_copy(update={
                "retrieval_mode": "fallback",
                "warnings": hit.warnings + [warning],
            })
            for hit in await FixtureSearchAdapter(name=self.name, retrieval_mode="fallback").search(
                country_code=country_code,
                source=source,
                queries=queries,
                limit=limit,
                browser_mode=browser_mode,
            )
        ]


class SerpApiSearchBackend:
    endpoint = "https://serpapi.com/search"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key or os.getenv("SERPAPI_API_KEY", "")).strip()
        if not self.api_key:
            raise SearchBackendConfigError("SERPAPI_API_KEY is not set")

    async def search(self, query: str, limit: int) -> list[RawSearchHit]:
        import httpx

        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": max(1, min(limit, 10)),
        }
        timeout = httpx.Timeout(12.0, connect=4.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))

        hits: list[RawSearchHit] = []
        for idx, item in enumerate(payload.get("organic_results") or [], start=1):
            url = str(item.get("link") or "").strip()
            if not url:
                continue
            hits.append(RawSearchHit(
                title=str(item.get("title") or url).strip(),
                url=url,
                snippet=str(item.get("snippet") or "").strip(),
                position=idx,
                raw=dict(item),
                retrieval_mode="live",
            ))
            if len(hits) >= limit:
                break
        return hits


def _configured_search_backend() -> str:
    value = os.getenv("DISCOVERY_SEARCH_BACKEND", "").strip().lower()
    return "" if value in {"", "none", "off", "fixture"} else value


def _build_search_backend(name: str) -> SearchBackend:
    if name == "serpapi":
        return SerpApiSearchBackend()
    raise SearchBackendConfigError(f"unsupported DISCOVERY_SEARCH_BACKEND: {name}")


def strip_site_filter(query: str) -> str:
    return re.sub(r"(?<![A-Za-z0-9_])site:\S+\s*", "", query).strip()


def _fixture_hits(
    country_code: str,
    source: LegalSourceConfig,
    adapter_name: str,
    retrieval_mode: RetrievalMode,
) -> list[RawSearchHit]:
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
        "AUS": {
            "legislation.gov.au": [
                RawSearchHit(
                    title="Privacy Act 1988",
                    url="https://www.legislation.gov.au/Latest/C2004A03712",
                    snippet="Official compilation of Australia's Privacy Act 1988, including privacy principles and personal information obligations.",
                    external_id="C2004A03712",
                ),
                RawSearchHit(
                    title="Security of Critical Infrastructure Act 2018",
                    url="https://www.legislation.gov.au/Latest/C2018A00029",
                    snippet="Official compilation of Australia's critical infrastructure security framework, including cyber incident obligations.",
                    external_id="C2018A00029",
                ),
            ],
        },
        "MYS": {
            "lom.agc.gov.my": [
                RawSearchHit(
                    title="Personal Data Protection Act 2010",
                    url="https://lom.agc.gov.my/act-detail.php?type=principal&lang=BI&act=709",
                    snippet="Principal Malaysian personal data protection legislation covering processing, disclosure, and cross-border transfer controls.",
                    external_id="act-709",
                ),
                RawSearchHit(
                    title="Cyber Security Act 2024",
                    url="https://lom.agc.gov.my/act-detail.php?type=principal&lang=BI&act=854",
                    snippet="Principal Malaysian cyber security legislation covering national cyber security duties and incident management.",
                    external_id="act-854",
                )
            ],
            "pdp.gov.my": [
                RawSearchHit(
                    title="Personal Data Protection Codes of Practice",
                    url="https://www.pdp.gov.my/ppdpv1/en/akta/",
                    snippet="Official sectoral codes and guidance issued under Malaysia's personal data protection framework.",
                )
            ],
        },
    }

    fallback_warning = (
        f"{adapter_name} is running in no-network mock mode"
        if retrieval_mode == "fixture"
        else f"{adapter_name} returned fixture fallback for {source.name}"
    )
    return fixtures.get(country_code, {}).get(domain, [
        RawSearchHit(
            title=f"{source.name} legal source",
            url=source.base_url,
            snippet="No live adapter is configured yet; this Phase 1 mock result preserves the discovery response contract.",
            warnings=[fallback_warning],
        )
    ])
