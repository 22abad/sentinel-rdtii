"""Russia discovery — publication.pravo.gov.ru (Official Internet Portal of
Legal Information, the state publication of record).

The portal's own front-end uses an unauthenticated JSON API:

    GET /api/Documents?PageSize=<n>&Index=1&Name=<term>   → {"items": [...]}

Each item carries ``eoNumber`` (the official publication number),
``complexName`` (the full instrument name, e.g. 'Федеральный закон от
27.07.2006 № 152-ФЗ "О персональных данных"'), ``documentDate`` and
``pagesCount``. The official PDF sits at ``/file/pdf?eoNumber=<eoNumber>``
(frequently a scan — the OCR path handles those); the human view page at
``/Document/View/<eoNumber>``. Current consolidated texts live in the sibling
IPS system (``pravo.gov.ru/proxy/ips/?doc_itself=&nd=…``, windows-1251,
NO rdk parameter = latest redaction) once an nd id is known.

``Name=`` searches instrument NAMES (verified empirically 2026-08-03:
``Name=персональных`` → 10/10 relevant; ``SearchString``/``Text`` are
ignored), so English pillar queries are mapped to Russian LAW-NAME terms,
not topic phrases.
"""

from __future__ import annotations

from urllib.parse import quote

from discovery.adapters.base import DiscoveryAdapter
from discovery.adapters.search_engine import strip_site_filter
from discovery.schemas import LegalSourceConfig, RawSearchHit

_BASE = "http://publication.pravo.gov.ru"

# Pillar concepts → Russian instrument-name search terms. The API matches the
# instrument NAME, so terms must look like law titles, not topics.
_RU_TERMS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("personal data", "data protection", "privacy", "consent", "cross-border",
      "cross border", "transfer", "localization", "local storage", "dpo",
      "data protection officer"), "персональных данных"),
    (("cyber", "security", "critical infrastructure"),
     "безопасности критической информационной инфраструктуры"),
    (("information", "information technology"),
     "об информации, информационных технологиях"),
    (("telecom", "communications"), "О связи"),
    (("interception", "government access", "lawful access", "counter-terror",
      "retention", "retain"), "противодействии терроризму"),
    (("electronic signature", "e-signature", "electronic transaction"),
     "Об электронной подписи"),
    (("payment", "e-money"), "национальной платежной системе"),
    (("import", "export", "licensing"), "лицензировании отдельных видов деятельности"),
)

# Only statutory instrument types from the publication stream.
_INSTRUMENT_PREFIXES = (
    "Федеральный закон",
    "Федеральный конституционный закон",
    "Указ Президента",
    "Постановление Правительства",
    "Распоряжение Правительства",
    "Приказ",
)


def _localize_query(en_query: str) -> str:
    q = en_query.lower()
    for needles, ru_term in _RU_TERMS:
        if any(n in q for n in needles):
            return ru_term
    return en_query


def _open_client():
    import httpx

    return httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(25.0))


class RussiaPravoAdapter(DiscoveryAdapter):
    name = "russia_pravo"

    async def search(
        self,
        *,
        country_code: str,
        source: LegalSourceConfig,
        queries: list[str],
        limit: int,
        browser_mode: str = "auto",
    ) -> list[RawSearchHit]:
        if country_code.upper() != "RUS":
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
                url = f"{_BASE}/api/Documents?PageSize=30&Index=1&Name={quote(term)}"
                try:
                    resp = await client.get(url)
                    payload = resp.json()
                except Exception:
                    continue
                for item in (payload or {}).get("items", []):
                    eo = item.get("eoNumber") or ""
                    name = " ".join((item.get("complexName") or "").split())
                    if not eo or eo in seen or not name:
                        continue
                    # eoNumber stream prefix: 0001 = federal; anything else is a
                    # regional publication stream (oblast/republic ministries) —
                    # RDTII scores national-level measures.
                    if not eo.startswith("0001"):
                        continue
                    if not name.startswith(_INSTRUMENT_PREFIXES):
                        continue
                    seen.add(eo)
                    hits.append(
                        RawSearchHit(
                            title=name,
                            url=f"{_BASE}/Document/View/{eo}",
                            snippet=name,
                            source_adapter=self.name,
                            source_name=source.name,
                            query=term,
                            position=len(hits) + 1,
                            external_id=eo,
                            raw={
                                "eo_number": eo,
                                "pdf_url": f"{_BASE}/file/pdf?eoNumber={eo}",
                                "document_date": item.get("documentDate"),
                                "pages_count": item.get("pagesCount"),
                            },
                            retrieval_mode="live",
                            discovery_method="official_search",
                        )
                    )
                    if len(hits) >= limit:
                        return hits
        return hits


__all__ = ["RussiaPravoAdapter"]
