"""Search adapter fallbacks for the Discovery Agent.

The generic search adapter intentionally avoids scraping public search engines
without an explicit configured backend. In development and CI it can return
fixture hits so the Discovery API contract remains stable.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Protocol

from discovery.schemas import LegalSourceConfig, RawSearchHit, RetrievalMode

from .base import DiscoveryAdapter

logger = logging.getLogger(__name__)


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
                "discovery_method": "fixture",
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
            if not rows:
                # Concept phrases ('site:x.gov data export security assessment')
                # score zero on web engines too — one bounded retry with the
                # phrase's two-word core, keeping the site: filter.
                site_match = re.search(r"(?<![A-Za-z0-9_])site:\S+", query)
                site = site_match.group(0) if site_match else ""
                core = _core_search_term(strip_site_filter(query))
                if core and core != strip_site_filter(query):
                    rows = await backend.search(
                        f"{site} {core}".strip(), max(1, limit - len(hits))
                    )
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
                    "discovery_method": "web_search",
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
                discovery_method="web_search",
            ))
            if len(hits) >= limit:
                break
        return hits


class DuckDuckGoSearchBackend:
    """Free, no-API-key web search via DuckDuckGo's HTML endpoint.

    This is the out-of-the-box default so a reviewer can run live discovery with
    ZERO paid credentials. Quality is good for legal queries — it reliably
    surfaces official government portals (legislation.gov.au, sso.agc.gov.sg,
    pdp.gov.my, ...). It is a little less broad than SerpApi/Google and can be
    rate-limited, so on any failure it degrades to the fixture fallback like any
    other backend. No extra dependency: it parses the plain HTML endpoint.
    """

    endpoint = "https://html.duckduckgo.com/html/"
    _UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )

    async def search(self, query: str, limit: int) -> list[RawSearchHit]:
        import html as _html

        import httpx

        timeout = httpx.Timeout(12.0, connect=4.0)
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": self._UA}
        ) as client:
            response = await client.post(self.endpoint, data={"q": query, "kl": "us-en"})
            response.raise_for_status()
            body = response.text

        # DDG serves its anti-bot challenge as HTTP 202 (a 2xx!) with zero
        # results — surface that as what it is, not as "no results".
        if response.status_code == 202 or "anomaly" in body[:20000]:
            raise RuntimeError(
                "DuckDuckGo is bot-challenging this IP (HTTP 202 anomaly page) — "
                "usually temporary rate limiting after many searches; retry "
                "later or set SERPAPI_API_KEY for the paid backend"
            )

        hits: list[RawSearchHit] = []
        for idx, match in enumerate(
            re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S),
            start=1,
        ):
            url = _html.unescape(match.group(1).strip())
            if not url.startswith("http"):
                continue
            title = _html.unescape(re.sub(r"<[^>]+>", "", match.group(2)).strip()) or url
            hits.append(RawSearchHit(
                title=title,
                url=url,
                snippet="",
                position=idx,
                raw={"url": url, "title": title},
                retrieval_mode="live",
                discovery_method="web_search",
            ))
            if len(hits) >= limit:
                break
        return hits


def _configured_search_backend() -> str:
    value = os.getenv("DISCOVERY_SEARCH_BACKEND", "").strip().lower()
    if value in {"none", "off", "fixture"}:
        return ""
    if value == "serpapi" and not os.getenv("SERPAPI_API_KEY", "").strip():
        # A stale explicit serpapi setting with no key would force every site
        # search into fixture fallback even though the free DuckDuckGo backend
        # works with zero configuration — degrade to DDG loudly instead.
        logger.warning(
            "DISCOVERY_SEARCH_BACKEND=serpapi but SERPAPI_API_KEY is not set — "
            "falling back to the free duckduckgo backend"
        )
        return "duckduckgo"
    if value:
        return value
    # Default when unset: SerpApi if a key is present (best quality), otherwise
    # the free, no-key DuckDuckGo backend — so a reviewer with no search
    # credentials still gets live web search out of the box.
    return "serpapi" if os.getenv("SERPAPI_API_KEY", "").strip() else "duckduckgo"


def _build_search_backend(name: str) -> SearchBackend:
    if name == "serpapi":
        return SerpApiSearchBackend()
    if name in {"duckduckgo", "ddg"}:
        return DuckDuckGoSearchBackend()
    raise SearchBackendConfigError(f"unsupported DISCOVERY_SEARCH_BACKEND: {name}")


def strip_site_filter(query: str) -> str:
    return re.sub(r"(?<![A-Za-z0-9_])site:\S+\s*", "", query).strip()


_GENERIC_QUERY_WORDS = {
    "ban", "bans", "requirement", "requirements", "restriction", "restrictions",
    "rule", "rules", "obligation", "obligations", "framework", "assessment",
    "policy", "measure", "measures", "law", "laws", "the", "for", "and",
}


def _core_search_term(term: str) -> str:
    """Two-word core of a concept phrase ('cross-border data transfer ban' →
    'data transfer') — concept phrases rarely appear verbatim anywhere, so a
    zero-hit query earns one bounded retry with its core."""
    words = [
        w for w in re.findall(r"[A-Za-z][A-Za-z-]+", term.lower())
        if w not in _GENERIC_QUERY_WORDS
    ]
    return " ".join(words[-2:]) if len(words) >= 2 else ""


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
                RawSearchHit(
                    title="Companies Act 1967",
                    url="https://sso.agc.gov.sg/Act/CoA1967",
                    snippet="Official text requiring specified accounting records to be retained for not less than five years.",
                    external_id="CoA1967",
                ),
                RawSearchHit(
                    title="Criminal Procedure Code 2010",
                    url="https://sso.agc.gov.sg/Act/CPC2010",
                    snippet="Official text containing police powers to access computers and data for investigations.",
                    external_id="CPC2010",
                ),
            ],
            "pdpc.gov.sg": [
                RawSearchHit(
                    title="Advisory Guidelines on Key Concepts in the PDPA",
                    url="https://www.pdpc.gov.sg/guidelines-and-consultation/2020/03/advisory-guidelines-on-key-concepts-in-the-pdpa",
                    snippet="Guidance on consent, notification, data protection officers, and transfer of personal data outside Singapore.",
                )
            ],
            "mti.gov.sg": [
                RawSearchHit(
                    title="Australia-Singapore Digital Economy Agreement",
                    url=(
                        "https://isomer-user-content.by.gov.sg/166/"
                        "769c26eb-17cf-4e2d-962b-1277a22df9db/"
                        "australia-singapore-digital-economy-agreement%20-%20Jun%2023.pdf"
                    ),
                    snippet="Official SADEA text containing binding Article 23 cross-border data-flow commitments.",
                )
            ],
        },
        "CHN": {
            "flk.npc.gov.cn": [
                RawSearchHit(
                    title="中华人民共和国个人信息保护法",
                    url="https://flk.npc.gov.cn/detail?id=ff8081817b6472a3017b656cc2040044&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E4%B8%AA%E4%BA%BA%E4%BF%A1%E6%81%AF%E4%BF%9D%E6%8A%A4%E6%B3%95&type=",
                    snippet="个人信息处理者向境外提供个人信息，应当具备个人信息保护认证、标准合同或者安全评估等条件。",
                    external_id="ff8081817b6472a3017b656cc2040044",
                ),
                RawSearchHit(
                    title="中华人民共和国网络安全法",
                    url="https://flk.npc.gov.cn/detail?id=021e7d7684474107b8f3febbb1c4f8b5&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E7%BD%91%E7%BB%9C%E5%AE%89%E5%85%A8%E6%B3%95&type=",
                    snippet="网络运营者应当按照网络安全等级保护制度要求履行安全保护义务。",
                    external_id="021e7d7684474107b8f3febbb1c4f8b5",
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
                    title="My Health Records Act 2012",
                    url="https://www.legislation.gov.au/Latest/C2012A00063",
                    snippet="Official compilation including requirements not to hold or process My Health Record system data outside Australia.",
                    external_id="C2012A00063",
                ),
                RawSearchHit(
                    title="Privacy Act 1988",
                    url="https://www.legislation.gov.au/Latest/C2004A03712",
                    snippet="Official compilation of Australia's Privacy Act 1988, including privacy principles and personal information obligations.",
                    external_id="C2004A03712",
                ),
                RawSearchHit(
                    title="Cyber Security Act 2024",
                    url="https://www.legislation.gov.au/C2024A00098/latest/text",
                    snippet="Official compilation of Australia's cyber security framework, including smart-device security and ransomware reporting obligations.",
                    external_id="C2024A00098",
                ),
                RawSearchHit(
                    title="Telecommunications (Interception and Access) Act 1979",
                    url="https://www.legislation.gov.au/Latest/C2004A02124",
                    snippet="Official compilation including a two-year telecommunications-data retention period and law-enforcement access powers.",
                    external_id="C2004A02124",
                ),
            ],
            "dfat.gov.au": [
                RawSearchHit(
                    title="Australia-Singapore Digital Economy Agreement",
                    url="https://www.dfat.gov.au/sites/default/files/australia-singapore-digital-economy-agreement.pdf",
                    snippet="Official signed agreement containing binding Article 23 cross-border data-flow commitments.",
                )
            ],
            "mti.gov.sg": [
                RawSearchHit(
                    title="Australia-Singapore Digital Economy Agreement",
                    url=(
                        "https://isomer-user-content.by.gov.sg/166/"
                        "769c26eb-17cf-4e2d-962b-1277a22df9db/"
                        "australia-singapore-digital-economy-agreement%20-%20Jun%2023.pdf"
                    ),
                    snippet="Singapore government publication of the joint agreement and its binding Article 23 data-flow commitment.",
                )
            ],
            "oaic.gov.au": [
                RawSearchHit(
                    title="Privacy (Australian Government Agencies — Governance) APP Code 2017",
                    url="https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/government-agencies/australian-government-agencies-privacy-code/privacy-australian-government-agencies-governance-app-code-2017",
                    snippet="Binding APP code requiring agencies to conduct privacy impact assessments for high privacy risk projects.",
                )
            ],
        },
        "MYS": {
            "lom.agc.gov.my": [
                RawSearchHit(
                    title="Companies Act 2016",
                    url="https://lom.agc.gov.my/act-detail.php?type=principal&lang=BI&act=777",
                    snippet="Principal Malaysian companies legislation requiring specified accounting records to be kept in Malaysia.",
                    external_id="act-777",
                ),
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
                ),
                RawSearchHit(
                    title="Digital Signature Act 1997",
                    url="https://lom.agc.gov.my/act-detail.php?type=principal&lang=BI&act=562",
                    snippet="Principal Malaysian legislation containing search-without-warrant and computerized-data access powers.",
                    external_id="act-562",
                ),
            ],
            "pdp.gov.my": [
                RawSearchHit(
                    title="Personal Data Protection (Amendment) Act 2024",
                    url="https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2024/11/Act-A1727.pdf",
                    snippet="Official amendment inserting section 12A on appointment of data protection officers.",
                ),
                RawSearchHit(
                    title="Appointment of Data Protection Officer",
                    url="https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/02/Pekeliling-DPO-1.pdf",
                    snippet="Official Commissioner Circular No. 1/2025 setting mandatory DPO appointment thresholds.",
                ),
            ],
            "ssm.com.my": [
                RawSearchHit(
                    title="Companies Act 2016",
                    url="https://www.ssm.com.my/Pages/Legal_Framework/Companies-Act-2016.aspx",
                    snippet="Official Companies Commission source for accounting-record retention requirements.",
                    external_id="act-777",
                )
            ],
            "fta.miti.gov.my": [
                RawSearchHit(
                    title="Chapter 14 Electronic Commerce",
                    url="https://fta.miti.gov.my/miti-fta/resources/Text%20of%20TPPA%20%28160516%29/14._Electronic_Commerce_.pdf",
                    snippet="Official CPTPP-incorporated chapter containing Article 14.11 on cross-border transfer of information.",
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
