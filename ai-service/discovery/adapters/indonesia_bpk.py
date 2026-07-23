"""Indonesia discovery — peraturan.bpk.go.id (official BPK legal database).

Indonesia's most complete official law database. It sits behind Cloudflare
(datacenter IPs get 403 on plain httpx), but a real Chrome TLS fingerprint via
curl_cffi passes it. There is no JSON API — discovery is a two-step scrape of
the site's own search:

    1. GET /Search?keywords=<query>          → HTML with /Details/<id>/<slug> links
    2. GET /Details/<id>/<slug>              → title, in-force status, and the
                                               /Download/<fileid>/<slug>.pdf link

We keep only in-force instruments ("Berlaku") and return the official PDF as the
fetch target. This is the portal's OWN search — no third-party search engine.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from discovery.adapters.base import DiscoveryAdapter
from discovery.schemas import LegalSourceConfig, RawSearchHit
from discovery.adapters.search_engine import strip_site_filter

_BASE = "https://peraturan.bpk.go.id"

# peraturan.bpk.go.id indexes Indonesian text only, so the English pillar
# queries the builder emits ("personal data protection act") match nothing.
# Map the P6/P7 concepts to their Bahasa Indonesia search terms.
_ID_TERMS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("cross-border", "cross border", "transfer", "outside", "abroad"), "transfer data pribadi ke luar negeri"),
    (("localization", "local storage", "stored local", "store data", "data centre", "data center", "local processing"), "penyelenggaraan sistem elektronik pusat data"),
    (("personal data", "data protection", "privacy", "consent"), "perlindungan data pribadi"),
    (("cyber", "security"), "keamanan siber"),
    (("retention", "retain", "record keeping", "records"), "penyimpanan dokumen elektronik"),
    (("data protection officer", "dpo", "accountability"), "pejabat pelindungan data pribadi"),
    (("government access", "lawful access", "interception"), "akses data pemerintah intersepsi"),
    (("electronic transaction",), "informasi dan transaksi elektronik"),
)


def _localize_query(en_query: str) -> str:
    """Map an English pillar query to its Bahasa Indonesia search term."""
    q = en_query.lower()
    for needles, id_term in _ID_TERMS:
        if any(n in q for n in needles):
            return id_term
    return en_query
_DETAILS_RE = re.compile(r'/Details/(\d+)/([a-z0-9-]+)', re.IGNORECASE)
_DOWNLOAD_RE = re.compile(r'/Download/\d+/[^"\']+\.pdf', re.IGNORECASE)
_TITLE_RE = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
# "Dicabut" = revoked, "Tidak Berlaku" = not in force → out of scope.
_REPEALED_RE = re.compile(r'Dicabut|Tidak Berlaku', re.IGNORECASE)


def _open_client():
    """curl_cffi with a real Chrome TLS fingerprint to clear Cloudflare."""
    try:
        from curl_cffi import requests as _creq

        return _creq.AsyncSession(impersonate="chrome", timeout=25, allow_redirects=True)
    except ImportError:
        import httpx

        return httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(25.0))


def _clean(fragment: str | None) -> str:
    if not fragment:
        return ""
    import html as _html

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", _html.unescape(fragment))).strip()


class IndonesiaBpkAdapter(DiscoveryAdapter):
    name = "indonesia_bpk"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if country_code.upper() != "IDN":
            return []

        hits: list[RawSearchHit] = []
        seen: set[str] = set()
        async with _open_client() as client:
            seen_terms: set[str] = set()
            for query in queries:
                term = _localize_query(strip_site_filter(query).strip())
                if not term or term in seen_terms:
                    continue
                seen_terms.add(term)
                try:
                    resp = await client.get(f"{_BASE}/Search?keywords={quote(term)}")
                    search_html = resp.text
                except Exception:
                    continue
                for did, slug in dict.fromkeys(_DETAILS_RE.findall(search_html)):
                    if did in seen:
                        continue
                    seen.add(did)
                    details_url = f"{_BASE}/Details/{did}/{slug}"
                    try:
                        d_resp = await client.get(details_url)
                        d_html = d_resp.text
                    except Exception:
                        continue
                    if _REPEALED_RE.search(d_html):
                        continue  # drop revoked / not-in-force
                    pdf_match = _DOWNLOAD_RE.search(d_html)
                    if not pdf_match:
                        continue
                    pdf_url = urljoin(_BASE, pdf_match.group(0))
                    law_no = _clean(_TITLE_RE.search(d_html).group(1)) if _TITLE_RE.search(d_html) else slug
                    subject = _clean(_H1_RE.search(d_html).group(1)) if _H1_RE.search(d_html) else ""
                    title = f"{law_no} — {subject}".strip(" —") or slug
                    hits.append(
                        RawSearchHit(
                            title=title,
                            url=pdf_url,
                            snippet=subject,
                            source_adapter=self.name,
                            source_name=source.name,
                            query=term,
                            position=len(hits) + 1,
                            external_id=did,
                            raw={"details_url": details_url, "law_number": law_no},
                            retrieval_mode="live",
                            discovery_method="official_search",
                        )
                    )
                    if len(hits) >= limit:
                        return hits
        return hits


__all__ = ["IndonesiaBpkAdapter"]
