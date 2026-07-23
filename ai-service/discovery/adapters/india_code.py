"""India discovery — indiacode.nic.in (official India Code, a DSpace repo).

The standard DSpace REST/OAI endpoints are disabled (404). Discovery works
through the portal's OWN `simple-search`, whose results table gives, per Act,
the handle id — which resolves to the official bitstream PDF. This discovers the
bitstream id at runtime instead of hard-coding it, so new Acts resolve automatically:

    1. GET /simple-search?query=<q>&rpp=<n>     → results table: date | actno |
                                                  short title | View→/handle/<id>
    2. GET /handle/123456789/<id>               → /bitstream/123456789/<id>/<seq>/<file>.pdf

Verified live 2026-07-21: a "data protection" search ranks the Digital Personal
Data Protection Act 2023 first (handle 22037 → a2023-22.pdf, 382 KB). No
third-party search engine.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from discovery.adapters.base import DiscoveryAdapter
from discovery.schemas import LegalSourceConfig, RawSearchHit
from discovery.adapters.search_engine import strip_site_filter

_BASE = "https://www.indiacode.nic.in"
# One results row: the short-title cell (t3) then the View link to /handle/<id>.
_ROW_RE = re.compile(
    r'<td[^>]*headers="t3"[^>]*>(?P<title>.*?)</td>.*?'
    r'href="/handle/123456789/(?P<hid>\d+)',
    re.IGNORECASE | re.DOTALL,
)
_BITSTREAM_RE = re.compile(r'/bitstream/123456789/\d+/\d+/[^"\']+\.pdf', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _open_client():
    try:
        from curl_cffi import requests as _creq

        return _creq.AsyncSession(impersonate="chrome", timeout=30, allow_redirects=True)
    except ImportError:
        import httpx

        return httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30.0))


def _clean_title(fragment: str) -> str:
    import html as _html

    return re.sub(r"\s+", " ", _html.unescape(_TAG_RE.sub("", fragment))).strip(" .")


class IndiaCodeAdapter(DiscoveryAdapter):
    name = "india_code"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if country_code.upper() != "IND":
            return []

        hits: list[RawSearchHit] = []
        seen: set[str] = set()
        async with _open_client() as client:
            for query in queries:
                term = strip_site_filter(query).strip()
                if not term:
                    continue
                try:
                    resp = await client.get(
                        f"{_BASE}/simple-search?query={quote(term)}&rpp={max(limit, 10)}&start=0"
                    )
                    rows = _ROW_RE.findall(resp.text)
                except Exception:
                    continue
                for title_html, hid in rows:
                    if hid in seen:
                        continue
                    seen.add(hid)
                    try:
                        d_resp = await client.get(f"{_BASE}/handle/123456789/{hid}")
                        m = _BITSTREAM_RE.search(d_resp.text)
                    except Exception:
                        continue
                    if not m:
                        continue
                    hits.append(
                        RawSearchHit(
                            title=_clean_title(title_html),
                            url=_BASE + m.group(0),
                            snippet="",
                            source_adapter=self.name,
                            source_name=source.name,
                            query=term,
                            position=len(hits) + 1,
                            external_id=hid,
                            raw={"handle_url": f"{_BASE}/handle/123456789/{hid}"},
                            retrieval_mode="live",
                            discovery_method="official_search",
                        )
                    )
                    if len(hits) >= limit:
                        return hits
        return hits


__all__ = ["IndiaCodeAdapter"]
