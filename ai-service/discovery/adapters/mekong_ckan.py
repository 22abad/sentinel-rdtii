"""Open Development Mekong CKAN adapter — Thailand & Lao PDR discovery.

The official Thai gazette (ratchakitcha.soc.go.th) is Cloudflare-blocked and the
Lao Official Gazette is thin/unreliable. Open Development Mekong (ODM) is an
open-data platform that republishes those SAME official gazette documents as a
standard CKAN catalogue with a public JSON API and — crucially — records the
official source URL on every law (`odm_laws_source`, e.g. the ratchakitcha PDF).

So this is not a third-party search engine: it is a reachable mirror of the
official text, with official provenance carried through to the output. We query
CKAN `package_search`, filter to in-force laws for the requested country, and
return the downloadable gazette PDF as the fetch target.

API: https://data.opendevelopmentmekong.net/api/3/action/package_search
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from discovery.adapters.base import DiscoveryAdapter
from discovery.schemas import LegalSourceConfig, RawSearchHit
from discovery.adapters.search_engine import strip_site_filter

_CKAN = "https://data.opendevelopmentmekong.net/api/3/action/package_search"

# ISO-3 economy → ODM CKAN organization slug.
_ORG: dict[str, str] = {"THA": "thailand", "LAO": "laos"}

# Only enforced, binding law. ODM status strings vary
# (signed_and_in_effect, adopted___validated___in_effect, in_effect, amended…);
# keep anything whose status mentions "effect", drop drafts / repealed.
_DROP_STATUS = ("draft", "repeal", "revoke", "annul", "expired")


def _open_client():
    """curl_cffi with a real Chrome TLS fingerprint (httpx fallback)."""
    try:
        from curl_cffi import requests as _creq

        return _creq.AsyncSession(impersonate="chrome", timeout=20, allow_redirects=True)
    except ImportError:
        import httpx

        return httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(20.0))


def _pdf_resource(pkg: dict[str, Any]) -> str:
    """Best downloadable text URL for a package: a PDF resource, else the
    official gazette source URL recorded by ODM."""
    for res in pkg.get("resources", []) or []:
        url = str(res.get("url", ""))
        fmt = str(res.get("format", "")).lower()
        if fmt == "pdf" or url.lower().endswith(".pdf"):
            return url
    return str(pkg.get("odm_laws_source", "") or "")


class MekongCkanAdapter(DiscoveryAdapter):
    name = "mekong_ckan"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        org = _ORG.get(country_code.upper())
        if not org:
            return []

        fq = quote(f"organization:{org}-organization AND type:laws_record")
        hits: list[RawSearchHit] = []
        seen: set[str] = set()
        async with _open_client() as client:
            for query in queries:
                term = strip_site_filter(query).strip()
                if not term:
                    continue
                params = f"?q={quote(term)}&fq={fq}&rows={max(limit, 10)}"
                try:
                    resp = await client.get(_CKAN + params)
                    payload = resp.json()
                except Exception:
                    continue
                if not payload.get("success"):
                    continue
                for pkg in payload.get("result", {}).get("results", []):
                    status = str(pkg.get("odm_laws_status", "")).lower()
                    if any(bad in status for bad in _DROP_STATUS):
                        continue  # drop drafts / repealed / expired
                    fetch_url = _pdf_resource(pkg)
                    if not fetch_url or fetch_url in seen:
                        continue
                    seen.add(fetch_url)
                    official = str(pkg.get("odm_laws_source", "") or "")
                    hits.append(
                        RawSearchHit(
                            title=str(pkg.get("title", "") or pkg.get("name", "")),
                            url=fetch_url,
                            snippet=str(pkg.get("odm_keywords", "") or ""),
                            source_adapter=self.name,
                            source_name=source.name,
                            query=term,
                            position=len(hits) + 1,
                            external_id=str(pkg.get("id", "")),
                            raw={
                                "official_source": official,
                                "issuing_agency": pkg.get("odm_laws_issuing_agency_parties", []),
                                "effective_date": pkg.get("odm_effective_date", ""),
                                "status": status,
                            },
                            retrieval_mode="live",
                            discovery_method="ckan_open_development_mekong",
                        )
                    )
                    if len(hits) >= limit:
                        return hits
        return hits


__all__ = ["MekongCkanAdapter"]
