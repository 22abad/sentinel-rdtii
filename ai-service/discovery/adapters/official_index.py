"""Discover configured legal documents from official government index pages."""

from __future__ import annotations

import html
import os
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

from discovery.metadata import source_allows_url
from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter


class OfficialIndexAdapter(DiscoveryAdapter):
    """Follow links published on a configured official landing page.

    This provides auditable live discovery for sources that publish treaty or
    circular PDFs in an index but do not offer a search API.  The configured
    include patterns keep the adapter source-specific and deterministic.
    """

    name = "official_index"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if browser_mode == "mock" or os.getenv("DISCOVERY_USE_FIXTURES", "").lower() in {
            "1", "true", "yes",
        }:
            return await FixtureSearchAdapter(name=self.name).search(
                country_code=country_code,
                source=source,
                queries=queries,
                limit=limit,
                browser_mode=browser_mode,
            )

        try:
            rows = await self._search_indexes(source, queries, limit)
            if rows:
                return rows
            warning = "official_index live discovery returned no matching links; returned fixture fallback."
        except Exception as exc:
            warning = f"official_index live discovery failed: {exc}; returned fixture fallback."

        fallback = await FixtureSearchAdapter(
            name=self.name,
            retrieval_mode="fallback",
        ).search(
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

    async def _search_indexes(
        self,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
    ) -> list[RawSearchHit]:
        import httpx

        if not source.search_paths:
            raise ValueError("official_index requires at least one configured search path")

        timeout = httpx.Timeout(30.0, connect=8.0)
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
        }
        rows: list[RawSearchHit] = []
        seen: set[str] = set()
        failures: list[str] = []
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout) as client:
            for search_path in source.search_paths:
                index_url = urljoin(source.base_url.rstrip("/") + "/", search_path)
                if not source_allows_url(source, index_url):
                    failures.append(f"{index_url}: outside configured official domains")
                    continue
                try:
                    response = await client.get(index_url)
                    response.raise_for_status()
                    parsed_rows = parse_official_index(
                        response.text,
                        index_url=str(response.url),
                        source=source,
                        query=queries[0] if queries else "",
                    )
                except Exception as exc:
                    failures.append(f"{index_url}: {exc.__class__.__name__}")
                    continue
                for row in parsed_rows:
                    key = row.url.casefold()
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row.model_copy(update={"position": len(rows) + 1}))
                    if len(rows) >= limit:
                        return rows
        if not rows and failures:
            raise RuntimeError("; ".join(failures))
        if failures:
            warning = "Some official index paths failed: " + "; ".join(failures)
            rows = [
                row.model_copy(update={"warnings": row.warnings + [warning]})
                for row in rows
            ]
        return rows


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        self._href = dict(attrs).get("href") or ""
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text)))
            self._href = ""
            self._text = []


def parse_official_index(
    document: str,
    *,
    index_url: str,
    source: LegalSourceConfig,
    query: str,
) -> list[RawSearchHit]:
    parser = _LinkParser()
    parser.feed(document)
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in source.include_patterns]
    rows: list[RawSearchHit] = []
    for href, anchor_text in parser.links:
        url = urljoin(index_url, html.unescape(href).strip())
        searchable = f"{url} {anchor_text}"
        if patterns and not any(pattern.search(searchable) for pattern in patterns):
            continue
        title = next(
            (
                configured_title
                for pattern, configured_title in source.title_overrides.items()
                if re.search(pattern, url, re.IGNORECASE)
            ),
            "",
        )
        title = re.sub(r"\s+", " ", html.unescape(title or anchor_text)).strip()
        if not title:
            title = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        rows.append(RawSearchHit(
            title=title,
            url=url,
            snippet=(
                f"{source.notes} Document linked from the official index at {index_url}."
            ).strip(),
            source_adapter="official_index",
            source_name=source.name,
            query=query,
            retrieval_mode="live",
            discovery_method="official_search",
            external_id=unquote(urlsplit(url).path.rsplit("/", 1)[-1]),
            raw={"index_url": index_url},
        ))
    return rows


__all__ = ["OfficialIndexAdapter", "parse_official_index"]
