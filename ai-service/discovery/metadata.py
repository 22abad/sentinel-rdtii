"""Cheap candidate normalization helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from source_validator import grade_source
from staleness_checker import check_staleness
from timeframe_extractor import extract_timeframe

from .query_builder import LOCAL_TERMS, PILLAR_QUERY_TERMS
from .schemas import LegalCandidate, LegalSourceConfig, RawSearchHit, normalize_hostname

TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid"}

DOCUMENT_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("press release", "secondary"),
    ("news", "secondary"),
    ("article", "secondary"),
    ("guideline", "guideline"),
    ("advisory", "guideline"),
    ("guide", "guideline"),
    ("regulation", "regulation"),
    ("rules", "regulation"),
    ("order", "regulation"),
    ("decree", "decree"),
    ("measure", "regulation"),
    ("measures", "regulation"),
    ("provisions", "regulation"),
    ("act", "act"),
    ("law", "act"),
    ("statute", "act"),
    ("code", "act"),
]

STATUS_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("repealed", "revoked", "superseded", "no longer in force", "已废止", "废止", "失效"), "repealed", "candidate appears repealed or no longer in force"),
    (("draft", "consultation", "征求意见", "草案"), "draft", "candidate appears to be draft or consultation material"),
    (("in force", "current", "现行有效"), "in_force", ""),
]

def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path
    if path != "/" and not parsed.fragment:
        path = path.rstrip("/")
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        _strip_tracking_query(parsed.query),
        parsed.fragment,
    ))


def _strip_tracking_query(query: str) -> str:
    """Remove tracking params without re-encoding opaque legal DB tokens."""
    if not query:
        return ""
    kept: list[str] = []
    for part in query.split("&"):
        if not part:
            continue
        raw_key = part.split("=", 1)[0]
        key = unquote_plus(raw_key).casefold()
        if key in TRACKING_PARAMS or key.startswith(TRACKING_PREFIXES):
            continue
        kept.append(part)
    return "&".join(kept)


def source_domain(url: str) -> str:
    try:
        return normalize_hostname(urlsplit(url).hostname or "")
    except (TypeError, ValueError):
        return ""


def source_allows_url(source: LegalSourceConfig, url: str) -> bool:
    """Return whether an HTTP(S) URL belongs to a configured source domain."""
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme.casefold() not in {"http", "https"}:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        # Accessing .port validates malformed values such as ':not-a-port'.
        parsed.port
        host = normalize_hostname(parsed.hostname or "")
    except (TypeError, ValueError):
        return False
    if not host:
        return False

    for configured_domain in source.domains:
        try:
            domain = normalize_hostname(configured_domain)
        except ValueError:
            continue
        if domain and host == domain:
            return True
    return False
def stable_candidate_id(url: str, title: str = "") -> str:
    digest = hashlib.sha256(f"{canonicalize_url(url)}\n{title.strip()}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def infer_document_type(title: str, url: str, snippet: str) -> str:
    text = f"{title} {url} {snippet}".casefold()
    if ".pdf" in url.casefold():
        return "pdf"
    for keyword, document_type in DOCUMENT_TYPE_KEYWORDS:
        if _contains_keyword(text, keyword):
            return document_type
    return "unknown"


def _contains_keyword(text: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword.casefold())}(?![a-z0-9])", text) is not None


def infer_language(text: str, source: LegalSourceConfig) -> str:
    if re.search(r"[\u0e00-\u0e7f]", text):
        return "th"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if "en" in source.languages:
        return "en"
    return source.languages[0] if source.languages else ""


def infer_last_update(title: str, url: str, snippet: str, raw: dict) -> str:
    for key in ("last_update", "publish_date", "published_date", "effective_date", "date", "year"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value

    raw_text = " ".join(str(value) for value in raw.values() if isinstance(value, (str, int, float)))
    timeframe = extract_timeframe(
        text=f"{snippet} {raw_text}",
        source_legislation=title,
        source_url="",
    )
    return str(
        timeframe.get("last_amended_date")
        or timeframe.get("in_force_date")
        or timeframe.get("repealed_date")
        or ""
    )


def infer_timeframe_status(title: str, snippet: str, raw: dict) -> tuple[str, list[str]]:
    text = " ".join([
        title,
        snippet,
        str(raw.get("status") or ""),
        str(raw.get("type") or ""),
    ]).casefold()
    warnings: list[str] = []

    for terms, status, warning in STATUS_RULES:
        if any(term.casefold() in text for term in terms):
            if warning:
                warnings.append(warning)
            return status, warnings
    return "in_force", warnings


def infer_metadata_warnings(title: str, url: str, snippet: str, raw: dict, last_update: str) -> list[str]:
    status, warnings = infer_timeframe_status(title, snippet, raw)
    stale_info = check_staleness(
        last_update=last_update,
        timeframe_status=status,
        source_url=url,
        source_legislation=title,
    )
    warnings.extend(stale_info.get("staleness_reasons", []))
    return list(dict.fromkeys(warnings))


def infer_indicator_matches(title: str, url: str, snippet: str) -> tuple[list[int], list[str], list[str]]:
    text = f"{title} {url} {snippet}".casefold()
    matched_indicators: list[str] = []
    reasons: list[str] = []

    direct_rules = {
        "6.1": [
            ("must not", "process", "outside"),
            ("must not", "hold", "outside"),
            ("local processing requirement",),
            ("data localization",),
            ("data localisation",),
        ],
        "6.2": [
            ("must not", "hold", "outside"),
            ("local storage requirement",),
            ("stored", "within the country"),
            ("accounting and other records", "kept", "place in malaysia"),
        ],
        "6.3": [
            ("local data centre",),
            ("local data center",),
            ("local server requirement",),
        ],
        "6.4": [
            ("cross-border", "personal data"),
            ("standard contract",),
            ("标准合同",),
            ("data export", "security assessment"),
            ("数据出境", "安全评估"),
            ("transfer", "outside singapore"),
            ("transfer", "personal data", "outside"),
            ("overseas", "personal information"),
        ],
        "7.1": [
            ("personal data protection",),
            ("personal information protection law",),
            ("data protection act",),
            ("privacy act",),
            ("privacy law",),
        ],
        "7.2": [
            ("cybersecurity",),
            ("cyber security",),
            ("cybercrime",),
            ("network security",),
        ],
        "7.3": [
            ("retention",),
            ("retain records",),
            ("must keep", "years"),
            ("shall retain", "years"),
            ("not less than", "years"),
            ("保存",),
        ],
        "7.4": [
            ("data protection officer",),
            ("dpo",),
            ("impact assessment",),
            ("designate", "one or more individuals", "responsible", "complies with this act"),
            ("影响评估",),
        ],
        "7.5": [
            ("government access",),
            ("law enforcement access",),
            ("police", "access", "data"),
            ("national security",),
        ],
    }
    for indicator, rules in direct_rules.items():
        if any(all(part in text for part in rule) for rule in rules):
            matched_indicators.append(indicator)
            reasons.append(f"matches indicator {indicator} terms")

    for indicator, terms in PILLAR_QUERY_TERMS.items():
        if indicator in matched_indicators:
            continue
        if any(term.casefold() in text for term in terms):
            matched_indicators.append(indicator)
            reasons.append(f"matches indicator {indicator} terms")

    for country_terms in LOCAL_TERMS.values():
        for indicator, terms in country_terms.items():
            if indicator in matched_indicators:
                continue
            if any(term.casefold() in text for term in terms):
                matched_indicators.append(indicator)
                reasons.append(f"matches indicator {indicator} local-language terms")

    matched_pillars = sorted({int(indicator.split(".", 1)[0]) for indicator in matched_indicators})
    matches = sorted(zip(matched_indicators, reasons), key=lambda match: match[0])
    return (
        matched_pillars,
        [indicator for indicator, _reason in matches],
        [reason for _indicator, reason in matches],
    )


def normalize_hit(country_code: str, source: LegalSourceConfig, hit: RawSearchHit) -> LegalCandidate:
    url = canonicalize_url(hit.url)
    title = hit.title.strip() or url
    snippet = hit.snippet.strip()
    grade_info = grade_source(url, title, snippet)
    matched_pillars, matched_indicators, match_reasons = infer_indicator_matches(title, url, snippet)
    inferred_grade = grade_info.get("grade")
    # DiscoveryService filters off-domain results before normalization, but
    # normalize_hit is also called directly by tests and reusable pipelines.
    # Keep this check as an independent trust-boundary safety net.
    belongs_to_source = source_allows_url(source, url)
    if not belongs_to_source:
        source_grade = "unknown"
    elif source.source_grade == "secondary":
        source_grade = "secondary"
    elif inferred_grade in {"primary", "secondary"}:
        source_grade = inferred_grade
    else:
        source_grade = source.source_grade
    reasons = list(grade_info.get("reasons", [])) + match_reasons
    if source.priority >= 100 and belongs_to_source:
        reasons.append("high-priority official source")
    last_update = infer_last_update(title, url, snippet, hit.raw)
    warnings = list(hit.warnings) + infer_metadata_warnings(title, url, snippet, hit.raw, last_update)
    if not belongs_to_source:
        warnings.append("Candidate URL is outside the configured source domains.")

    return LegalCandidate(
        id=stable_candidate_id(url, title),
        country_code=country_code,
        title=title,
        url=url,
        source_domain=source_domain(url),
        official_domains=list(source.domains),
        source_name=source.name,
        source_grade=source_grade,
        document_type=infer_document_type(title, url, snippet),
        language=infer_language(f"{title} {snippet}", source),
        last_update=last_update,
        matched_pillars=matched_pillars,
        matched_indicators=matched_indicators,
        snippet=snippet,
        confidence=float(grade_info.get("confidence") or 0.0),
        reasons=reasons,
        warnings=list(dict.fromkeys(warnings)),
        external_id=hit.external_id,
        source_adapter=hit.source_adapter,
        query=hit.query,
        retrieval_mode=hit.retrieval_mode,
        discovery_method=hit.discovery_method,
    )
