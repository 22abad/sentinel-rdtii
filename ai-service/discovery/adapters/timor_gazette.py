"""Timor-Leste discovery — mj.gov.tl/jornal (Jornal da República, the official
gazette of record; final-round bonus economy).

The gazette is a plain-HTTP Drupal site (no JS wall):

    GET /jornal/?q=search/node/<pt-term>   → server-rendered result list
                                             with ?q=node/<id> links
    GET /jornal/?q=node/<id>               → 25K+ chars of gazette text
                                             server-side, plus official PDF
                                             links where the instrument is a
                                             scan

Content is Portuguese/Tetum. English pillar queries are mapped to Portuguese
legal-topic terms; the extraction path reads Portuguese directly (DeepSeek
handles it; the Indonesian precedent showed non-English extraction works
end-to-end). Legacy static mirror (/jornal/lawsTL/) is stale and carries
junk links — deliberately NOT used.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from discovery.adapters.base import DiscoveryAdapter
from discovery.adapters.search_engine import strip_site_filter
from discovery.schemas import LegalSourceConfig, RawSearchHit

_BASE = "https://mj.gov.tl"

# Pillar concepts → Portuguese search terms for the gazette's Drupal search.
_PT_TERMS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("personal data", "data protection", "privacy", "consent", "cross-border",
      "cross border", "transfer", "dpo"), "dados pessoais"),
    (("cyber", "security", "critical infrastructure"), "cibernética segurança"),
    (("telecom", "communications", "licensing", "operator"), "telecomunicações"),
    (("electronic transaction", "e-commerce", "electronic commerce",
      "online sales"), "comércio eletrónico"),
    (("electronic signature", "e-signature", "digital signature"),
     "assinatura eletrónica"),
    (("payment", "e-money", "banking"), "sistema de pagamentos"),
    (("interception", "government access", "lawful access", "retention"),
     "interceção comunicações"),
    (("import", "export", "customs"), "regime aduaneiro"),
    (("investment", "foreign investment"), "investimento privado"),
    (("intellectual property", "copyright", "trademark"),
     "propriedade intelectual"),
)

_RESULT_RE = re.compile(
    r'href="(https?://mj\.gov\.tl/jornal/\?q=node/(\d+))"[^>]*>([^<]+)',
    re.IGNORECASE,
)
# Instrument headline inside a node page, e.g. "DECRETO-LEI N.º 25/2016",
# "LEI N.º 5/2020", "RESOLUÇÃO DO GOVERNO N.º 12/2021".
_INSTRUMENT_RE = re.compile(
    r"\b((?:DECRETO-LEI|LEI|DECRETO|RESOLU[ÇC][ÃA]O(?:\s+DO\s+GOVERNO|\s+DO\s+PARLAMENTO\s+NACIONAL)?|"
    r"DIPLOMA\s+MINISTERIAL)\s+N\.?[ºo°]?\s*\d+\s*/\s*\d{4})",
    re.IGNORECASE,
)


def _localize_query(en_query: str) -> str:
    q = en_query.lower()
    for needles, pt_term in _PT_TERMS:
        if any(n in q for n in needles):
            return pt_term
    return en_query


def _open_client():
    import httpx

    return httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )


class TimorGazetteAdapter(DiscoveryAdapter):
    name = "timor_gazette"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if country_code.upper() != "TLS":
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
                search_url = f"{_BASE}/jornal/?q=search/node/{quote(term)}"
                try:
                    resp = await client.get(search_url)
                    html = resp.text or ""
                except Exception:
                    continue
                for url, node_id, _title in _RESULT_RE.findall(html):
                    if node_id in seen:
                        continue
                    seen.add(node_id)
                    # The result list titles are the generic gazette masthead —
                    # fetch the node to name the actual instrument.
                    instrument = ""
                    pdf_links: list[str] = []
                    try:
                        n_resp = await client.get(url)
                        n_html = n_resp.text or ""
                        n_text = re.sub(r"<[^>]+>", " ", n_html)
                        m = _INSTRUMENT_RE.search(n_text)
                        instrument = " ".join(m.group(1).split()) if m else ""
                        pdf_links = [
                            p for p in re.findall(r'href="([^"]+\.pdf[^"]*)"', n_html)
                        ][:5]
                    except Exception:
                        pass
                    hits.append(
                        RawSearchHit(
                            title=instrument or f"Jornal da República node {node_id} ({term})",
                            url=url,
                            snippet=term,
                            source_adapter=self.name,
                            source_name=source.name,
                            query=term,
                            position=len(hits) + 1,
                            external_id=node_id,
                            raw={"pdf_links": pdf_links, "search_term": term},
                            retrieval_mode="live",
                            discovery_method="official_search",
                        )
                    )
                    if len(hits) >= limit:
                        return hits
        return hits


__all__ = ["TimorGazetteAdapter"]
