"""China National Laws and Regulations Database discovery adapter."""

from __future__ import annotations

import html
import re
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
            import httpx
            from browser_drivers import OpenCliBrowserDriver

            driver = OpenCliBrowserDriver()
            timeout = httpx.Timeout(10.0, connect=4.0)
            headers = {
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
            }
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout) as client:
                rows = await self._search_queries(driver, queries, limit, client=client)
            if rows:
                return [
                    row.model_copy(update={"source_name": source.name})
                    for row in rows
                ]
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

    async def _search_queries(
        self,
        driver: Any,
        queries: list[str],
        limit: int,
        client: Any | None = None,
    ) -> list[RawSearchHit]:
        hits: list[RawSearchHit] = []
        seen_urls: set[str] = set()
        hit_indexes: dict[str, int] = {}
        fallback_urls: set[str] = set()

        for query in queries:
            search_term = strip_site_filter(query)
            if not search_term:
                continue
            if client is not None:
                for row in await _known_law_hits(client, search_term):
                    url = str(row["url"])
                    if url in seen_urls:
                        if row.get("retrieval_mode") == "live" and url in fallback_urls:
                            index = hit_indexes[url]
                            hits[index] = _raw_hit_from_row(
                                self.name,
                                search_term,
                                hits[index].position,
                                row,
                            )
                            fallback_urls.remove(url)
                        continue
                    seen_urls.add(url)
                    hit_indexes[url] = len(hits)
                    hits.append(_raw_hit_from_row(self.name, search_term, len(hits) + 1, row))
                    if row.get("retrieval_mode") == "fallback":
                        fallback_urls.add(url)
                    if len(hits) >= limit and not fallback_urls:
                        return hits

            rows = await driver.search_gov_law(search_term, limit=max(1, min(limit, 20)))
            for row in rows:
                url = str(row.get("url") or "").strip()
                if not url:
                    continue
                live_row = _row_from_driver(row)
                if url in seen_urls:
                    if url in fallback_urls:
                        index = hit_indexes[url]
                        hits[index] = _raw_hit_from_row(
                            self.name,
                            search_term,
                            hits[index].position,
                            live_row,
                        )
                        fallback_urls.remove(url)
                    continue
                seen_urls.add(url)
                hit_indexes[url] = len(hits)
                hits.append(_raw_hit_from_row(self.name, search_term, len(hits) + 1, live_row))
                if len(hits) >= limit and not fallback_urls:
                    return hits
            if len(hits) >= limit:
                return hits[:limit]
        return hits[:limit]


KNOWN_LAWS: tuple[dict[str, Any], ...] = (
    {
        "terms": (
            "个人信息保护法",
            "个人信息保护",
            "personal information protection",
            "personal data protection",
            "pipl",
            "数据出境",
            "标准合同",
            "个人信息保护认证",
        ),
        "title": "中华人民共和国个人信息保护法",
        "url": "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3YjY4M2JhYjAxN2I5MTYxYzQyMjA4M2I%3D",
        "snippet": "个人信息处理者向境外提供个人信息，应当具备个人信息保护认证、标准合同或者安全评估等条件。",
        "external_id": "pipl",
    },
    {
        "terms": (
            "网络安全法",
            "cybersecurity law",
            "cyber security law",
            "network security",
            "critical information infrastructure",
            "关键信息基础设施",
        ),
        "title": "中华人民共和国网络安全法",
        "url": "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE1YmI3OTY2YTAxNWJiZGMwM2U2YjA0M2I%3D",
        "snippet": "网络运营者应当按照网络安全等级保护制度要求履行安全保护义务。",
        "external_id": "cybersecurity-law",
    },
)


async def _known_law_hits(client: Any, query: str) -> list[dict[str, Any]]:
    query_text = query.casefold()
    rows: list[dict[str, Any]] = []
    for law in KNOWN_LAWS:
        if not any(term.casefold() in query_text for term in law["terms"]):
            continue
        row = {
            "title": law["title"],
            "url": law["url"],
            "snippet": law["snippet"],
            "external_id": law["external_id"],
            "retrieval_mode": "fallback",
            "warnings": [
                "Known National Laws and Regulations Database law page could not be verified live; returned configured fallback."
            ],
            "raw": {"match_strategy": "known_official_law_page"},
        }
        try:
            response = await client.get(law["url"])
            response.raise_for_status()
        except Exception:
            rows.append(row)
            continue
        try:
            live_title = _extract_flk_title(response.text)
        except Exception as exc:
            row["warnings"] = row["warnings"] + [f"Could not extract verified live title: {exc}"]
            rows.append(row)
            continue
        if live_title != law["title"]:
            row["warnings"] = row["warnings"] + [
                "Could not verify the expected law title from the FLK page."
            ]
            rows.append(row)
            continue
        row["title"] = live_title
        row["retrieval_mode"] = "live"
        row["warnings"] = []
        rows.append(row)
    return rows


def _external_id_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.query:
        return parsed.query
    path_leaf = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return path_leaf or url


def _row_from_driver(row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url") or "").strip()
    snippet_parts = [
        str(row.get("type") or "").strip(),
        str(row.get("department") or "").strip(),
        str(row.get("status") or "").strip(),
        str(row.get("publish_date") or "").strip(),
    ]
    return {
        "title": str(row.get("title") or "").strip(),
        "url": url,
        "snippet": " | ".join(part for part in snippet_parts if part),
        "external_id": _external_id_from_url(url),
        "raw": dict(row),
    }


def _raw_hit_from_row(adapter_name: str, query: str, position: int, row: dict[str, Any]) -> RawSearchHit:
    return RawSearchHit(
        title=str(row.get("title") or "").strip(),
        url=str(row.get("url") or "").strip(),
        snippet=str(row.get("snippet") or "").strip(),
        source_adapter=adapter_name,
        query=query,
        position=position,
        external_id=str(row.get("external_id") or _external_id_from_url(str(row.get("url") or ""))),
        raw=dict(row.get("raw") or {}),
        warnings=list(row.get("warnings") or []),
        retrieval_mode=row.get("retrieval_mode") or "live",
    )


def _extract_flk_title(markup: str) -> str:
    text = _clean_text(_strip_tags(markup))
    for law in KNOWN_LAWS:
        if law["title"] in text:
            return str(law["title"])

    title_match = re.search(r"<title\b[^>]*>\s*(.*?)\s*</title>", markup, flags=re.IGNORECASE | re.DOTALL)
    if not title_match:
        return ""
    title = _clean_text(_strip_tags(title_match.group(1)))
    return re.sub(r"\s*[-_]\s*国家法律法规数据库\s*$", "", title).strip()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _strip_tags(value: str) -> str:
    value = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1\s*>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"<[^>]+>", " ", value)
