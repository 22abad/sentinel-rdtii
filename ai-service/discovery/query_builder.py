"""Pillar-aware query generation for official legal-source discovery."""

from __future__ import annotations

import re

from .schemas import DiscoverySearchRequest, LegalSourceConfig

PILLAR_QUERY_TERMS: dict[str, list[str]] = {
    "6.1": [
        "cross-border data transfer ban",
        "data localization",
        "local processing requirement",
        "shall not transfer data abroad",
    ],
    "6.2": [
        "local storage requirement",
        "store data within the country",
        "data must be stored locally",
    ],
    "6.3": [
        "local data centre requirement",
        "local data center requirement",
        "local server requirement",
    ],
    "6.4": [
        "security assessment data export",
        "standard contract personal data transfer",
        "adequacy consent cross-border transfer",
        "prior authorization data transfer",
    ],
    "6.5": [
        "free flow of data agreement",
        "cross-border transfer of information trade agreement",
        "digital economy partnership agreement data flow",
    ],
    "7.1": [
        "personal data protection act",
        "privacy law",
        "data protection legal framework",
    ],
    "7.2": [
        "cybersecurity law",
        "cybercrime law",
        "network security regulation",
    ],
    "7.3": [
        "data retention period",
        "retain records for at least",
        "minimum retention requirement",
    ],
    "7.4": [
        "data protection officer",
        "DPO requirement",
        "data protection impact assessment",
        "DPIA requirement",
    ],
    "7.5": [
        "government access personal data",
        "law enforcement access data without warrant",
        "national security access personal data",
    ],
}

LOCAL_TERMS: dict[str, dict[str, list[str]]] = {
    "CHN": {
        "6.1": ["数据出境 禁止", "数据本地化", "境内处理"],
        "6.2": ["境内存储", "本地存储 数据"],
        "6.3": ["本地服务器", "数据中心 境内"],
        "6.4": ["数据出境安全评估", "个人信息出境 标准合同", "个人信息保护认证"],
        "7.1": ["个人信息保护法", "个人信息保护"],
        "7.2": ["网络安全法", "数据安全法"],
        "7.3": ["数据 保留期限", "至少保存"],
        "7.4": ["个人信息保护负责人", "个人信息保护影响评估"],
        "7.5": ["国家安全 个人信息", "执法 数据 提供"],
    },
    # Tier-2 economies (added 2026-07-16): a few high-value local-language
    # terms per indicator; English PILLAR_QUERY_TERMS still apply everywhere.
    "IDN": {
        "6.4": ["transfer data pribadi ke luar wilayah", "pemindahan data pribadi"],
        "7.1": ["undang-undang pelindungan data pribadi", "UU PDP 27 2022"],
        "7.2": ["keamanan siber undang-undang"],
        "7.3": ["retensi data", "penyimpanan data jangka waktu"],
        "7.5": ["akses pemerintah data pribadi"],
    },
    "RUS": {
        "6.1": ["локализация персональных данных", "хранение персональных данных на территории"],
        "6.2": ["базы данных на территории Российской Федерации 152-ФЗ"],
        "6.4": ["трансграничная передача персональных данных"],
        "7.1": ["федеральный закон о персональных данных 152-ФЗ"],
        "7.2": ["закон о безопасности критической информационной инфраструктуры"],
        "7.3": ["срок хранения данных закон"],
        "7.5": ["СОРМ доступ к данным", "оперативно-розыскная деятельность данные"],
    },
    "MNG": {
        "7.1": ["хувь хүний мэдээлэл хамгаалах тухай хууль"],
        "7.2": ["кибер аюулгүй байдлын тухай хууль"],
        "7.5": ["төрийн байгууллага мэдээлэл авах"],
    },
    "LAO": {
        "7.1": ["ກົດໝາຍວ່າດ້ວຍການປົກປ້ອງຂໍ້ມູນເອເລັກໂຕຣນິກ", "electronic data protection law Lao"],
        "7.2": ["cyber security law Lao PDR"],
    },
    "IND": {
        "6.4": ["transfer of personal data outside India DPDP"],
        "7.1": ["Digital Personal Data Protection Act 2023"],
        "7.4": ["significant data fiduciary data protection officer DPDP"],
        "7.5": ["section 36 DPDP Act government access"],
    },
}


def indicators_for_pillars(pillars: list[int]) -> list[str]:
    prefixes = tuple(f"{pillar}." for pillar in pillars)
    return [
        indicator
        for indicator in PILLAR_QUERY_TERMS
        if indicator.startswith(prefixes)
    ]


def selected_indicators(request: DiscoverySearchRequest) -> list[str]:
    if request.indicators:
        return [
            indicator
            for indicator in request.indicators
            if indicator in PILLAR_QUERY_TERMS
        ]
    return indicators_for_pillars(request.pillars)


def terms_for_request(request: DiscoverySearchRequest) -> list[str]:
    terms: list[str] = []
    explicit_indicator = bool(request.indicators)
    per_indicator_limit = None if explicit_indicator else 2
    include_english_terms = not request.languages or "en" in request.languages
    include_local_terms = not request.languages or any(language != "en" for language in request.languages)

    for indicator in selected_indicators(request):
        indicator_terms: list[str] = []
        if include_english_terms:
            english_terms = list(PILLAR_QUERY_TERMS.get(indicator, []))
            if per_indicator_limit is not None:
                english_terms = english_terms[:per_indicator_limit]
            indicator_terms.extend(english_terms)
        if include_local_terms:
            local_terms = list(LOCAL_TERMS.get(request.country_code, {}).get(indicator, []))
            if per_indicator_limit is not None:
                local_terms = local_terms[:per_indicator_limit]
            indicator_terms.extend(local_terms)
        terms.extend(indicator_terms)

    if request.keywords.strip():
        terms.insert(0, request.keywords.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def build_source_queries(
    request: DiscoverySearchRequest,
    source: LegalSourceConfig,
    *,
    max_per_source: int = 8,
) -> list[str]:
    queries: list[str] = []
    domain = source.domains[0]
    terms = prioritized_terms_for_request(request)

    for term in terms:
        _append_query(queries, domain, term, max_per_source)
        if len(queries) >= max_per_source:
            return queries

    for term in terms:
        if not _is_ascii_query(term):
            continue
        for suffix in (" law", " regulation"):
            _append_query(queries, domain, f"{term}{suffix}", max_per_source)
            if len(queries) >= max_per_source:
                return queries
    return queries


def _append_query(queries: list[str], domain: str, term: str, max_per_source: int) -> None:
    if len(queries) >= max_per_source:
        return
    query = f"site:{domain} {term}".strip()
    if query not in queries:
        queries.append(query)


def _is_ascii_query(term: str) -> bool:
    return bool(re.fullmatch(r"[\x00-\x7f]+", term))


def prioritized_terms_for_request(request: DiscoverySearchRequest) -> list[str]:
    terms_by_indicator = _terms_by_indicator(request)
    prioritized: list[str] = []
    if request.keywords.strip():
        prioritized.append(request.keywords.strip())

    max_depth = max((len(terms) for terms in terms_by_indicator.values()), default=0)
    for index in range(max_depth):
        for terms in terms_by_indicator.values():
            if index < len(terms):
                prioritized.append(terms[index])

    deduped: list[str] = []
    seen: set[str] = set()
    for term in prioritized:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def _terms_by_indicator(request: DiscoverySearchRequest) -> dict[str, list[str]]:
    explicit_indicator = bool(request.indicators)
    per_indicator_limit = None if explicit_indicator else 2
    include_english_terms = not request.languages or "en" in request.languages
    include_local_terms = not request.languages or any(language != "en" for language in request.languages)

    terms_by_indicator: dict[str, list[str]] = {}
    for indicator in selected_indicators(request):
        indicator_terms: list[str] = []
        if include_english_terms:
            english_terms = list(PILLAR_QUERY_TERMS.get(indicator, []))
            if per_indicator_limit is not None:
                english_terms = english_terms[:per_indicator_limit]
            indicator_terms.extend(english_terms)
        if include_local_terms:
            local_terms = list(LOCAL_TERMS.get(request.country_code, {}).get(indicator, []))
            if per_indicator_limit is not None:
                local_terms = local_terms[:per_indicator_limit]
            indicator_terms.extend(local_terms)
        terms_by_indicator[indicator] = indicator_terms
    return terms_by_indicator


def build_queries(
    request: DiscoverySearchRequest,
    sources: list[LegalSourceConfig],
    *,
    max_total: int = 24,
    max_per_source: int = 8,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    remaining = max_total

    for source in sources:
        if remaining <= 0:
            break
        queries = build_source_queries(
            request,
            source,
            max_per_source=min(max_per_source, remaining),
        )
        result[source.name] = queries
        remaining -= len(queries)
    return result
