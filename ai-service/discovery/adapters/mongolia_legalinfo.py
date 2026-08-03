"""Mongolia discovery — legalinfo.mn (Unified Legal Information System).

The portal serves FULL consolidated law texts server-side at
``/mn/detail?lawId=<id>`` (122K+ chars for the Personal Data Protection Law)
with the statute name in ``<title>`` — but its search runs on a generic "md*"
middleware over POST with no stable public endpoint, and the sitemap's 36,837
detail URLs carry no titles. So discovery follows the china_flk precedent:
a curated seed map of RDTII-relevant statutes, each hit fetched LIVE from the
portal and self-verified against the page's own ``<title>``. A hit is only
tagged ``live`` when the portal itself confirms the statute name; a failed
fetch or title mismatch downgrades to ``fallback`` with a warning.

Seed lawIds located via the portal's sitemap + web search, verified 2026-08-03.
"""

from __future__ import annotations

import re

from discovery.adapters.base import DiscoveryAdapter
from discovery.schemas import LegalSourceConfig, RawSearchHit

_BASE = "https://legalinfo.mn"

# (url_path, expected Mongolian title fragment, English name, concept needles)
_SEEDS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("/mn/detail?lawId=16390288615991",
     "ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ",
     "Law on Personal Data Protection (2021)",
     ("personal data", "data protection", "privacy", "consent", "cross-border",
      "cross border", "transfer", "localization", "local storage", "dpo",
      "data protection officer", "government access", "retention")),
    ("/mn/detail?lawId=16390365491061",
     "КИБЕР АЮУЛГҮЙ БАЙДЛЫН",
     "Law on Cybersecurity (2021)",
     ("cyber", "security", "critical infrastructure", "incident")),
    ("/mn/detail?lawId=16390263044601",
     "НИЙТИЙН МЭДЭЭЛЛИЙН ИЛ ТОД",
     "Law on Public Information Transparency (2021)",
     ("public information", "transparency", "open data", "government data",
      "freedom of information")),
    ("/mn/detail?lawId=16390355252531",
     "ЦАХИМ ГАРЫН ҮСГИЙН",
     "Law on Electronic Signatures (2021)",
     ("electronic signature", "e-signature", "digital signature",
      "electronic transaction", "authentication")),
    ("/mn/detail/523",
     "ХАРИЛЦАА ХОЛБООНЫ",
     "Law on Communications (2001)",
     ("telecom", "communications", "licensing", "network", "operator",
      "interception")),
)

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _matching_seeds(queries: list[str]):
    picked = []
    seen = set()
    for query in queries:
        q = query.lower()
        for path, mn_title, en_name, needles in _SEEDS:
            if path in seen:
                continue
            if any(n in q for n in needles):
                seen.add(path)
                picked.append((path, mn_title, en_name, query))
    return picked


def _open_client():
    import httpx

    return httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(25.0),
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )


class MongoliaLegalinfoAdapter(DiscoveryAdapter):
    name = "mongolia_legalinfo"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if country_code.upper() != "MNG":
            return []

        hits: list[RawSearchHit] = []
        async with _open_client() as client:
            for path, mn_title, en_name, query in _matching_seeds(queries)[:limit]:
                url = f"{_BASE}{path}"
                verified = False
                page_title = ""
                warnings: list[str] = []
                try:
                    resp = await client.get(url)
                    m = _TITLE_RE.search(resp.text or "")
                    page_title = " ".join((m.group(1) if m else "").split())
                    verified = mn_title in page_title
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"live fetch failed: {exc}")
                if not verified and not warnings:
                    warnings.append(
                        f"portal title {page_title!r} does not confirm seed {mn_title!r}"
                    )
                hits.append(
                    RawSearchHit(
                        title=f"{page_title or mn_title} — {en_name}",
                        url=url,
                        snippet=en_name,
                        source_adapter=self.name,
                        source_name=source.name,
                        query=query,
                        position=len(hits) + 1,
                        external_id=path.rsplit("=", 1)[-1].rsplit("/", 1)[-1],
                        raw={"expected_title": mn_title, "page_title": page_title},
                        warnings=warnings,
                        retrieval_mode="live" if verified else "fallback",
                        discovery_method="official_portal_seed",
                    )
                )
        return hits


__all__ = ["MongoliaLegalinfoAdapter"]
