"""Indicator classifier — short-lists which RDTII 2.1 indicators an article touches."""

from __future__ import annotations

import re
from dataclasses import dataclass

from terminology import expand_phrases

# Unified dictionary for all 12 supported RDTII indicators
_BASE_PHRASES = {
    "1.1": ["tariff", "customs duty", "tax", "关税", "贸易防御"],
    "2.1": [
        "public procurement", "government tender", 
        "การจัดซื้อจัดจ้าง", "พัสดุ", "คณะกรรมการ", 
        "政府采购", "招投标"
    ],
    "3.1": [
        "foreign direct investment", "FDI", "foreign ownership",
        "外商投资", "外资", "外商投资法"
    ],
    "4.1": ["intellectual property", "patent", "copyright", "知识产权", "专利", "著作权"],
    "5.1": ["telecom", "broadband", "frequency", "电信", "宽带"],
    "5.3": [
        "government equity", "government ownership", "state-owned",
        "majority stake", "government share", "public sector",
        "telecom", "operator", "telecommunication service provider",
        "政府持股", "国有", "国有控股", "控股",
    ],
    "6.1": [
        "transfer abroad", "transferred abroad", "transferring abroad", "transferring data abroad", "ban on transfer",
        "process locally", "data localization", "data localisation",
        "xử lý tại chỗ", "pemrosesan", "proses", "ห้ามโอนย้ายไปต่างประเทศ",
        "出境", "境外", "境内处理", "禁止传输", "本地处理",
        "transfer personal data", "transfer of personal data", "restrict transfer",
        "prohibition of transfer", "no transfer", "shall not transfer"
    ],
    "6.2": [
        "store data within", "local storage", "stored locally",
        "lưu trữ dữ liệu", "disimpan", "penyimpanan", "เก็บรักษาไว้",
        "境内存储", "本地存储"
    ],
    "6.3": [
        "local data centre", "local data center", "data center within", "data centre within",
        "local server", "physical infrastructure", "establish a server",
        "服务器", "数据中心"
    ],
    "6.4": [
        "consent", "adequacy", "standard contract", "prior authorization", "security assessment",
        " согласие", "充分性", "标准合同", "安全评估",
        "data exporter", "data importer", "binding corporate", "adequate level of protection",
        "appropriate safeguard", "contractual clause", "transfer mechanism",
        # Conditional cross-border flow language — golden boundary cases:
        # SGP PDPA s.26 ("comparable ... standard of protection") and
        # AUS Privacy Act APP 8.1 ("overseas recipient", "cross-border disclosure").
        "comparable protection", "comparable standard", "standard of protection",
        "adequate protection", "overseas recipient", "cross-border disclosure",
        "cross-border transfer", "跨境提供", "对外提供"
    ],
    "6.5": [
        "trade agreement", "depa", "cptpp", "rcep", "free flow of data",
        "自由贸易协定", "数字经济伙伴关系"
    ],
    "7.1": [
        "personal data protection", "privacy law", "privacy act", "data protection act",
        "luật bảo vệ dữ liệu", "undang-undang perlindungan data",
        "个人信息保护法", "隐私", "数据主体"
    ],
    "7.2": [
        # AU/UK/SG drafting writes the open compound ("cyber security");
        # the closed form alone missed the AUS Cyber Security Act 2024.
        "cybersecurity", "cyber security", "cybercrime", "cyber crime",
        "an ninh mạng", "keamanan siber",
        "网络安全", "网络犯罪"
    ],
    "7.3": [
        "retain", "retention period", "minimum period",
        "thời gian lưu trữ", "periode retensi",
        "保留", "至少保存", "保留期"
    ],
    "7.4": [
        "data protection officer", "dpo", "dpia", "impact assessment",
        "designate one or more individuals",
        # Malay (PDP Commissioner circulars): DPO = Pegawai Perlindungan Data
        "pegawai perlindungan data",
        "数据保护官", "影响评估",
        "compliance officer", "privacy officer", "registration with",
        "data controller", "data processor", "register of processing",
        "annual audit", "data audit", "compliance audit"
    ],
    "7.5": [
        "law enforcement access", "without warrant", "surveillance",
        "执法", "国家安全", "监视",
        "public interest", "public authority access", "government access",
        "national security", "public order", "disclosure to law enforcement",
        "obligation to notify", "competent authority", "regulatory authority"
    ],
    "8.1": ["intermediary liability", "safe harbor", "互联网平台责任", "责任承担"],
    "9.1": ["online content", "illegal content", "在线内容", "违法内容"],
    "10.1": ["non-tariff measure", "trade restriction", "非关税措施", "贸易限制"],
    "11.1": ["standards", "conformity assessment", "技术标准", "合格评定"],
    "12.1": ["online sales", "e-signature", "在线销售", "电子签名"]
}

# Fragments too generic to route on — they appear in nearly every statute.
_GENERIC_FRAGMENTS = {
    "measures", "measure", "requirements", "requirement", "restrictions",
    "restriction", "data", "services", "service", "other", "existence",
    "framework", "issues", "practice", "laws", "law", "related",
    "sectors", "sector", "products", "content",
}


def _phrases_from_category(category: str) -> list[str]:
    """Derive routing phrases from an indicator's official category text.

    Round 2 spans 61 indicators; hand-curating phrases for each is not
    sustainable, so non-curated indicators route on key fragments of their
    official RDTII category (e.g. "Foreign equity limits in e-commerce" ->
    ["foreign equity limits", "e-commerce"]). Curated _BASE_PHRASES always win.
    """

    text = category.split("\n")[0]  # exception notes live on later lines
    text = re.sub(r"\([^)]*\)", " ", text)
    fragments = re.split(
        r"[,;/]| including | such as | related to | relevant to | in | of | for | to | and | or ",
        text, flags=re.IGNORECASE,
    )
    out: list[str] = []
    for fragment in fragments:
        fragment = fragment.strip().lower().strip(" .-–")
        fragment = re.sub(r"^(the|a|an|any|lack of|absence of|existence of|minimum)\s+", "", fragment)
        if (
            4 <= len(fragment) <= 45
            and fragment not in _GENERIC_FRAGMENTS
            and not fragment.isdigit()
        ):
            out.append(fragment)
    return out[:6]


def _methodology_phrases() -> dict[str, list[str]]:
    try:
        from methodology import load_methodology
    except ImportError:  # pragma: no cover — methodology data not provisioned
        return {}
    return {
        iid: phrases
        for iid, rule in load_methodology().items()
        if (phrases := _phrases_from_category(rule.category))
    }


# Build expanded phrases at load time: curated phrases + jurisdiction synonyms,
# unioned with methodology-derived phrases (curated entries keep their hits and
# gain the official category wording; Round 2 indicators without curation get
# the derived phrases alone).
_INDICATOR_PHRASES = {
    k: expand_phrases(v) for k, v in _BASE_PHRASES.items()
}
for _iid, _derived in _methodology_phrases().items():
    _INDICATOR_PHRASES[_iid] = sorted(
        set(_INDICATOR_PHRASES.get(_iid, [])) | set(expand_phrases(_derived))
    )

# Statutes often express localization as a prohibition on offshore handling
# rather than using the concise labels in the RDTII taxonomy. First isolate each
# ``must not`` / ``shall not`` clause so a later positive ``must`` clause cannot
# inherit the earlier negation. ASCII-only boundaries intentionally allow forms
# such as ``规定must not ...`` while still rejecting English word continuations.
_NORMATIVE_PROHIBITION_CLAUSE = re.compile(
    r"(?<![A-Za-z0-9_])(?:must|shall)(?![A-Za-z0-9_])\s+not(?![A-Za-z0-9_])"
    r"(?:(?!(?<![A-Za-z0-9_])(?:must|shall)(?![A-Za-z0-9_])|[.。]).){0,260}",
    re.IGNORECASE | re.DOTALL,
)

_STRUCTURED_INDICATOR_PATTERNS = {
    "6.1": (
        re.compile(
            r"(?<![A-Za-z0-9_])"
            r"(?:process(?:ed|es|ing)?|handle(?:d|s|ing)?)"
            r"(?![A-Za-z0-9_])[^.。]{0,80}"
            r"(?<![A-Za-z0-9_])(?:outside|abroad|overseas)(?![A-Za-z0-9_])",
            re.IGNORECASE,
        ),
    ),
    "6.2": (
        re.compile(
            r"(?<![A-Za-z0-9_])"
            r"(?:hold(?:s|ing)?|held|store(?:d|s|ing)?|keep(?:s|ing)?|kept|"
            r"retain(?:ed|s|ing)?)"
            r"(?![A-Za-z0-9_])[^.。]{0,100}"
            r"(?<![A-Za-z0-9_])(?:outside|abroad|overseas)(?![A-Za-z0-9_])",
            re.IGNORECASE,
        ),
    ),
}

@dataclass(frozen=True)
class IndicatorCandidate:
    """Auditable shortlist evidence for one indicator.

    Keyword routing is recall-only: this score is never treated as mapping
    confidence.  Keeping the exact matched span/rule makes false-positive
    routing diagnosable without asking an LLM to explain itself afterwards.
    """

    indicator_id: str
    matched_span: str
    matched_rule: str
    retrieval_score: float


_SENTENCE_RE = re.compile(r"[^.!?。！？;；\n]+(?:[.!?。！？;；]|$)")


def _bounded_phrase_pattern(phrase: str) -> re.Pattern:
    """Compile an exact phrase with ASCII word boundaries where applicable."""
    escaped = re.escape(phrase)
    left = r"(?<![A-Za-z0-9_])" if phrase[:1].isascii() and phrase[:1].isalnum() else ""
    right = r"(?![A-Za-z0-9_])" if phrase[-1:].isascii() and phrase[-1:].isalnum() else ""
    return re.compile(left + escaped + right, re.IGNORECASE)


def _phrase_match(phrase: str, text: str) -> tuple[str, str, float] | None:
    """Return a local, boundary-aware match; never join words across sentences.

    Exact phrases are preferred.  A conservative proximity fallback handles
    harmless punctuation/word-order damage, but all words must occur in the
    same sentence and within a 120-character window.  The former implementation
    used ``all(word in whole_chunk)`` and therefore routed unrelated paragraphs.
    """
    phrase = phrase.strip()
    if not phrase:
        return None
    exact = _bounded_phrase_pattern(phrase).search(text)
    if exact:
        score = min(1.0, 0.55 + 0.04 * len(phrase.split()) + min(len(phrase), 40) / 200)
        return exact.group(0), f'exact phrase: "{phrase}"', round(score, 3)

    words = [word for word in re.findall(r"[A-Za-z0-9]+", phrase) if len(word) > 1]
    if len(words) < 2:
        return None
    patterns = [_bounded_phrase_pattern(word) for word in words]
    for sentence_match in _SENTENCE_RE.finditer(text):
        sentence = sentence_match.group(0)
        hits = [pattern.search(sentence) for pattern in patterns]
        if not all(hits):
            continue
        starts = [hit.start() for hit in hits if hit]
        ends = [hit.end() for hit in hits if hit]
        start, end = min(starts), max(ends)
        if end - start > 120:
            continue
        span = sentence[start:end]
        score = min(0.74, 0.42 + 0.05 * len(words))
        return span, f'same-sentence proximity: "{phrase}"', round(score, 3)
    return None


def classify_indicator_candidates(article_text: str) -> list[IndicatorCandidate]:
    """Return ranked, auditable recall candidates for an article/chunk."""
    if not article_text or not article_text.strip():
        return []

    best: dict[str, IndicatorCandidate] = {}
    for indicator, phrases in _INDICATOR_PHRASES.items():
        for phrase in phrases:
            match = _phrase_match(phrase, article_text)
            if not match:
                continue
            span, rule, score = match
            candidate = IndicatorCandidate(indicator, span, rule, score)
            if indicator not in best or candidate.retrieval_score > best[indicator].retrieval_score:
                best[indicator] = candidate

    for clause_match in _NORMATIVE_PROHIBITION_CLAUSE.finditer(article_text):
        clause = clause_match.group(0)
        for indicator, patterns in _STRUCTURED_INDICATOR_PATTERNS.items():
            if any(pattern.search(clause) for pattern in patterns):
                candidate = IndicatorCandidate(
                    indicator_id=indicator,
                    matched_span=clause,
                    matched_rule="structured normative prohibition",
                    retrieval_score=0.95,
                )
                if indicator not in best or candidate.retrieval_score > best[indicator].retrieval_score:
                    best[indicator] = candidate

    return sorted(best.values(), key=lambda item: (-item.retrieval_score, item.indicator_id))

def classify_indicator(article_text: str) -> list[str]:
    """Compatibility wrapper returning the historical sorted indicator IDs."""
    return sorted(candidate.indicator_id for candidate in classify_indicator_candidates(article_text))
