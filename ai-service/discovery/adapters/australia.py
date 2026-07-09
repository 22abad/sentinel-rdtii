"""Australia Federal Register of Legislation discovery adapter."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter, strip_site_filter


class AustraliaLegislationAdapter(DiscoveryAdapter):
    name = "australia_legislation"

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
            rows = await self._search_queries(queries, limit)
            if rows:
                return [
                    row.model_copy(update={"source_name": source.name})
                    for row in rows
                ]
            warning = "australia_legislation live search returned no results; returned fixture fallback."
        except Exception as exc:
            warning = f"australia_legislation live search failed: {exc}; returned fixture fallback."

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

    async def _search_queries(self, queries: list[str], limit: int) -> list[RawSearchHit]:
        import httpx

        hits: list[RawSearchHit] = []
        seen_urls: set[str] = set()
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
            for query in queries:
                search_term = strip_site_filter(query)
                if not search_term:
                    continue

                for row in await _known_instrument_hits(client, search_term):
                    if row["url"] in seen_urls:
                        continue
                    seen_urls.add(row["url"])
                    hits.append(_raw_hit_from_row(self.name, search_term, len(hits) + 1, row))
                    if len(hits) >= limit:
                        return hits

                try:
                    response = await client.get(_search_url(search_term))
                    response.raise_for_status()
                except Exception:
                    continue
                for row in _parse_legislation_search_results(response.text):
                    if row["url"] in seen_urls:
                        continue
                    seen_urls.add(row["url"])
                    row.setdefault("raw", {})["search_url"] = str(response.url)
                    hits.append(_raw_hit_from_row(self.name, search_term, len(hits) + 1, row))
                    if len(hits) >= limit:
                        return hits
        return hits


KNOWN_INSTRUMENTS: tuple[dict[str, Any], ...] = (
    {
        "terms": (
            "privacy act",
            "personal information",
            "data protection",
            "cross-border",
            "overseas disclosure",
        ),
        "title": "Privacy Act 1988",
        "url": "https://www.legislation.gov.au/Latest/C2004A03712",
        "snippet": (
            "Official compilation of Australia's Privacy Act 1988, including "
            "privacy principles and personal information handling obligations."
        ),
        "external_id": "C2004A03712",
    },
    {
        "terms": (
            "security of critical infrastructure",
            "critical infrastructure",
            "cyber security",
            "cybersecurity",
            "incident reporting",
        ),
        "title": "Security of Critical Infrastructure Act 2018",
        "url": "https://www.legislation.gov.au/Latest/C2018A00029",
        "snippet": (
            "Official compilation of Australia's critical infrastructure "
            "security framework, including cyber incident obligations."
        ),
        "external_id": "C2018A00029",
    },
)


async def _known_instrument_hits(client: Any, query: str) -> list[dict[str, Any]]:
    query_text = query.casefold()
    rows: list[dict[str, Any]] = []
    for instrument in KNOWN_INSTRUMENTS:
        if not any(term in query_text for term in instrument["terms"]):
            continue
        row = {
            "title": instrument["title"],
            "url": instrument["url"],
            "snippet": instrument["snippet"],
            "external_id": instrument["external_id"],
            "retrieval_mode": "fallback",
            "warnings": [
                "Known Federal Register instrument could not be verified live; returned configured fallback."
            ],
            "raw": {"match_strategy": "known_official_instrument"},
        }
        try:
            response = await client.get(instrument["url"])
            response.raise_for_status()
        except Exception:
            rows.append(row)
            continue
        try:
            live_title = _extract_page_title(response.text)
        except Exception as exc:
            row["warnings"] = row["warnings"] + [f"Could not extract verified live title: {exc}"]
            rows.append(row)
            continue
        row["title"] = live_title or instrument["title"]
        row["retrieval_mode"] = "live"
        row["warnings"] = []
        rows.append(row)
    return rows


def _search_url(query: str) -> str:
    return f"https://www.legislation.gov.au/search?searchTerm={quote_plus(query)}"


class _LegislationSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active_href = ""
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        attrs_by_name = {name.casefold(): value or "" for name, value in attrs}
        href = attrs_by_name.get("href", "")
        if _is_legislation_href(href):
            self._active_href = href
            self._active_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or not self._active_href:
            return
        title = _clean_text(" ".join(self._active_text))
        if title:
            url = urljoin("https://www.legislation.gov.au", self._active_href)
            self.results.append({
                "title": title,
                "url": url,
                "snippet": "Federal Register of Legislation search result.",
                "external_id": _external_id_from_url(url),
            })
        self._active_href = ""
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)


def _parse_legislation_search_results(markup: str) -> list[dict[str, str]]:
    parser = _LegislationSearchParser()
    parser.feed(markup)
    return parser.results


def _is_legislation_href(href: str) -> bool:
    parsed = urlsplit(href)
    host = parsed.netloc.casefold()
    path = "/" + parsed.path.lstrip("/")
    if host and host not in {"www.legislation.gov.au", "legislation.gov.au"}:
        return False
    return path.startswith(("/Latest/", "/Details/", "/Series/")) and bool(
        re.search(r"C20\d{2}[A-Z]\d{5}", path)
    )


def _extract_page_title(markup: str) -> str:
    match = re.search(r"<title\b[^>]*>\s*(.*?)\s*</title>", markup, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = _clean_text(_strip_tags(match.group(1)))
    return re.sub(r"\s+-\s+Federal Register of Legislation$", "", title).strip()


def _external_id_from_url(url: str) -> str:
    match = re.search(r"C20\d{2}[A-Z]\d{5}", url)
    return match.group(0) if match else url.rstrip("/").rsplit("/", 1)[-1]


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


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)
