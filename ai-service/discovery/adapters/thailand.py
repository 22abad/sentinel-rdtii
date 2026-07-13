"""Thailand OCS discovery adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from discovery.schemas import LegalSourceConfig, RawSearchHit

from .base import DiscoveryAdapter
from .search_engine import FixtureSearchAdapter, strip_site_filter


class ThailandOcsAdapter(DiscoveryAdapter):
    name = "thailand_ocs"

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
            from crawler import search_ocs_law

            rows = await self._search_queries(search_ocs_law, queries, limit)
            if rows:
                return [
                    row.model_copy(update={"source_name": source.name})
                    for row in rows
                ]
            warning = "thailand_ocs live search returned no results; returned fixture fallback."
        except Exception as exc:
            warning = f"thailand_ocs live search failed: {exc}; returned fixture fallback."

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

    async def _search_queries(self, search_ocs_law: Any, queries: list[str], limit: int) -> list[RawSearchHit]:
        hits: list[RawSearchHit] = []
        seen_keys: set[str] = set()

        for query in queries:
            search_term = strip_site_filter(query)
            if not search_term:
                continue
            expanded_hit = False
            for ocs_query in _expanded_ocs_queries(search_term):
                if expanded_hit and ocs_query != search_term:
                    continue
                hit_count_before_query = len(hits)
                rows = await search_ocs_law(ocs_query, max_results=max(1, min(limit, 20)))
                for row in rows:
                    url = str(row.get("doc_url") or row.get("url") or "").strip()
                    if not url:
                        continue
                    dedupe_key = str(row.get("doc_id") or "").strip() or url
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    hits.append(_raw_hit_from_ocs_row(self.name, search_term, len(hits) + 1, row))
                    if len(hits) >= limit:
                        return hits
                if ocs_query != search_term and len(hits) > hit_count_before_query:
                    expanded_hit = True
        return hits


KNOWN_OCS_QUERIES: tuple[dict[str, tuple[str, ...]], ...] = (
    {
        "terms": (
            "personal data protection",
            "pdpa",
            "cross-border transfer",
            "data protection officer",
            "dpo",
            "คุ้มครองข้อมูลส่วนบุคคล",
        ),
        "queries": (
            "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล",
            "Personal Data Protection Act",
        ),
    },
    {
        "terms": (
            "cybersecurity",
            "cyber security",
            "cyber security maintenance",
            "national cybersecurity",
            "critical information infrastructure",
            "ความมั่นคงปลอดภัยไซเบอร์",
        ),
        "queries": (
            "พระราชบัญญัติการรักษาความมั่นคงปลอดภัยไซเบอร์",
            "Cyber Security Maintenance Act",
        ),
    },
    {
        "terms": (
            "electronic transaction",
            "electronic transactions",
            "electronic records",
            "ธุรกรรมทางอิเล็กทรอนิกส์",
        ),
        "queries": (
            "พระราชบัญญัติว่าด้วยธุรกรรมทางอิเล็กทรอนิกส์",
            "Electronic Transactions Act",
        ),
    },
)


def _expanded_ocs_queries(query: str) -> list[str]:
    query_text = query.casefold()
    expanded: list[str] = []
    for known in KNOWN_OCS_QUERIES:
        if any(term.casefold() in query_text for term in known["terms"]):
            expanded.extend(known["queries"])
    expanded.append(query)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in expanded:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped


def _raw_hit_from_ocs_row(adapter_name: str, query: str, position: int, row: dict[str, Any]) -> RawSearchHit:
    url = str(row.get("doc_url") or row.get("url") or "").strip()
    doc_id = str(row.get("doc_id") or "").strip() or _external_id_from_url(url)
    return RawSearchHit(
        title=str(row.get("title") or "").strip(),
        url=url,
        snippet=" | ".join(
            str(row.get(key) or "").strip()
            for key in ("status", "published_date", "year", "source")
            if row.get(key)
        ),
        source_adapter=adapter_name,
        query=query,
        position=position,
        external_id=doc_id,
        raw=dict(row),
    )


def _external_id_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.fragment:
        return parsed.fragment.rstrip("/").rsplit("/", 1)[-1]
    return parsed.path.rstrip("/").rsplit("/", 1)[-1] or url
