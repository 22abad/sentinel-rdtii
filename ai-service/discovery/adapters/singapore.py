"""Singapore discovery adapters."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter, strip_site_filter


class SingaporeSsoAdapter(DiscoveryAdapter):
    name = "singapore_sso"

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
            warning = "singapore_sso live search returned no results; returned official fixture fallback."
        except Exception as exc:
            warning = f"singapore_sso live search failed: {exc}; returned official fixture fallback."

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
        timeout = httpx.Timeout(8.0, connect=4.0)
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
                known_hit_count = len(hits)
                for row in await _known_law_hits(client, search_term):
                    if row["url"] in seen_urls:
                        continue
                    seen_urls.add(row["url"])
                    hits.append(RawSearchHit(
                        title=row["title"],
                        url=row["url"],
                        snippet=row["snippet"],
                        source_adapter=self.name,
                        query=search_term,
                        position=len(hits) + 1,
                        external_id=_external_id_from_url(row["url"]),
                        raw={"match_strategy": "known_official_detail_page"},
                        warnings=[row["warnings"]] if row.get("warnings") else [],
                        retrieval_mode=row["retrieval_mode"],
                    ))
                    if len(hits) >= limit:
                        return hits
                if len(hits) > known_hit_count:
                    continue

                try:
                    response = await client.get(_search_url(search_term))
                    response.raise_for_status()
                except Exception:
                    continue
                for row in _parse_sso_search_results(response.text):
                    if row["url"] in seen_urls:
                        continue
                    seen_urls.add(row["url"])
                    hits.append(RawSearchHit(
                        title=row["title"],
                        url=row["url"],
                        snippet=row["snippet"],
                        source_adapter=self.name,
                        query=search_term,
                        position=len(hits) + 1,
                        external_id=_external_id_from_url(row["url"]),
                        raw={"search_url": str(response.url)},
                        retrieval_mode="live",
                    ))
                    if len(hits) >= limit:
                        return hits
        return hits


def _search_url(query: str) -> str:
    return f"https://sso.agc.gov.sg/Search/Content?Phrase={quote_plus(query)}"


def _external_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] or url


KNOWN_LAWS: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (
        (
            "personal data protection",
            "pdpa",
            "data protection officer",
            "cross-border transfer",
            "cross-border data transfer",
            "overseas transfer",
        ),
        "Personal Data Protection Act 2012",
        "https://sso.agc.gov.sg/Act/PDPA2012",
        "Official text for Singapore personal data protection, data protection officers, and overseas transfers.",
    ),
    (
        ("cybersecurity", "critical information infrastructure", "cyber security"),
        "Cybersecurity Act 2018",
        "https://sso.agc.gov.sg/Act/CA2018",
        "Official text for Singapore cybersecurity duties and critical information infrastructure.",
    ),
)


async def _known_law_hits(client: Any, query: str) -> list[dict[str, str]]:
    query_text = query.casefold()
    rows: list[dict[str, str]] = []
    for terms, fallback_title, url, snippet in KNOWN_LAWS:
        if not any(term in query_text for term in terms):
            continue
        row = {
            "title": fallback_title,
            "url": url,
            "snippet": snippet,
            "retrieval_mode": "fallback",
            "warnings": "Known SSO law page could not be verified live; returned configured fallback.",
        }
        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception:
            rows.append(row)
            continue
        row["title"] = _extract_page_title(response.text) or fallback_title
        row["retrieval_mode"] = "live"
        row["warnings"] = ""
        rows.append(row)
    return rows


def _extract_page_title(markup: str) -> str:
    match = re.search(r"<title\b[^>]*>\s*(.*?)\s*</title>", markup, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = _clean_text(match.group(1))
    return re.sub(r"\s+-\s+Singapore Statutes Online$", "", title).strip()


class _SsoSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active_link: dict[str, Any] | None = None
        self._link_text: list[str] = []
        self._snippet_parts: list[str] = []
        self._capture_snippet_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_by_name = {name.casefold(): value or "" for name, value in attrs}
        if tag.casefold() == "a":
            href = attrs_by_name.get("href", "")
            if _is_sso_result_href(href):
                self._active_link = {"href": href}
                self._link_text = []
                self._snippet_parts = []
                self._capture_snippet_depth = 0
                return

        if self._active_link is not None:
            self._capture_snippet_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._active_link is None:
            return
        if tag.casefold() == "a":
            title = _clean_text(" ".join(self._link_text))
            if title:
                self.results.append({
                    "title": title,
                    "url": urljoin("https://sso.agc.gov.sg", self._active_link["href"]),
                    "snippet": _clean_text(" ".join(self._snippet_parts)),
                })
            self._active_link = None
            self._link_text = []
            self._snippet_parts = []
            self._capture_snippet_depth = 0
            return
        if self._capture_snippet_depth:
            self._capture_snippet_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._active_link is None:
            return
        self._link_text.append(data)
        if self._capture_snippet_depth:
            self._snippet_parts.append(data)


def _parse_sso_search_results(markup: str) -> list[dict[str, str]]:
    parser = _SsoSearchParser()
    parser.feed(markup)
    return parser.results


def _is_sso_result_href(href: str) -> bool:
    path = "/" + urlsplit(href).path.lstrip("/")
    return path.startswith(("/Act/", "/SL/", "/Bill/", "/Act-Supp/"))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()
