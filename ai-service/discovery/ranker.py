"""Deterministic ranking for discovery candidates."""

from __future__ import annotations

from .schemas import LegalCandidate, LegalSourceConfig

SOURCE_AUTHORITY = {
    "primary": 35,
    "secondary": 8,
    "unknown": 0,
}

DOCUMENT_TYPE = {
    "act": 20,
    "regulation": 18,
    "decree": 16,
    "official_guideline": 10,
    "guideline": 10,
    "pdf": 6,
    "secondary": -15,
    "unknown": 0,
}

MATCHING = {
    "per_indicator": 8,
    "per_pillar": 4,
    "title_exact": 12,
    "snippet_match": 4,
}

VALIDATION = {
    "verified": 6,
    "content_mismatch": -4,
}

STALE_WARNING_TERMS = (
    "stale",
    "staleness",
    "outdated",
    "older than",
    "repealed",
    "revoked",
    "superseded",
    "draft",
    "consultation",
    "no longer in force",
    "废止",
    "失效",
    "草案",
)


def score_candidate(candidate: LegalCandidate, source: LegalSourceConfig | None = None) -> float:
    score = 0.0
    reasons: list[str] = []

    source_score = SOURCE_AUTHORITY.get(candidate.source_grade, 0)
    if source_score:
        score += source_score
        reasons.append("official source domain" if candidate.source_grade == "primary" else "secondary source lead")

    if source:
        priority_score = max(0, min(source.priority, 100)) / 5
        score += priority_score
        if source.priority >= 95:
            reasons.append("official statute portal")

    document_score = DOCUMENT_TYPE.get(candidate.document_type, 0)
    score += document_score
    if document_score > 0:
        reasons.append(f"document type: {candidate.document_type}")
    elif document_score < 0:
        reasons.append("secondary source penalty")

    if candidate.matched_indicators:
        score += MATCHING["per_indicator"] * len(candidate.matched_indicators)
    if candidate.matched_pillars:
        score += MATCHING["per_pillar"] * len(candidate.matched_pillars)

    title_lower = candidate.title.casefold()
    if any(term in title_lower for term in (
        "personal data protection act",
        "cybersecurity law",
        "data security law",
        "个人信息保护法",
        "网络安全法",
        "数据安全法",
        "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล",
    )):
        score += MATCHING["title_exact"]
        reasons.append("title matches known legal instrument")

    if candidate.snippet and candidate.matched_indicators:
        score += MATCHING["snippet_match"]
        reasons.append("snippet contains indicator terms")

    if candidate.source_grade == "secondary":
        score -= 15
        reasons.append("secondary source penalty")

    if candidate.validation_status == "verified":
        score += VALIDATION["verified"]
        reasons.append("fetched text validation boost")
    elif candidate.validation_status == "weak":
        score += VALIDATION["content_mismatch"]
        reasons.append("fetched text relevance penalty")
    elif (
        candidate.validation_status == "failed"
        and not candidate.validation_metadata.get("error")
    ):
        score += VALIDATION["content_mismatch"]
        reasons.append("fetched content validation penalty")

    stale_warnings = [
        warning
        for warning in candidate.warnings
        if any(term in warning.lower() for term in STALE_WARNING_TERMS)
    ]
    if stale_warnings:
        stale_penalty = 12 if any("repealed" in warning.lower() or "draft" in warning.lower() for warning in stale_warnings) else 6
        score -= stale_penalty
        reasons.append("staleness/version warning penalty")

    candidate.rank_score = round(score, 2)
    candidate.reasons = list(dict.fromkeys(candidate.reasons + reasons))
    return candidate.rank_score


def rank_candidates(
    candidates: list[LegalCandidate],
    sources: list[LegalSourceConfig],
) -> list[LegalCandidate]:
    source_by_name = {source.name: source for source in sources}
    for candidate in candidates:
        score_candidate(candidate, source_by_name.get(candidate.source_name))
    return sorted(candidates, key=lambda candidate: candidate.rank_score, reverse=True)
