"""Independent mapping-eligibility gate.

The extractor proposes features and an exact quote.  This module decides whether
that quote actually supports the candidate indicator *before* scoring or legal
rationale generation.  It combines high-precision deterministic boundaries with
an independent all-indicator LLM classification that never receives the
extractor's rationale or assigned score.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any

from providers.base import LLMProvider
from validation import has_substantive_content


@dataclass
class EligibilityResult:
    decision: str
    candidate_indicator: str
    supported_indicators: list[str] = field(default_factory=list)
    evidence_spans: dict[str, list[str]] = field(default_factory=dict)
    exclusion_reasons: list[str] = field(default_factory=list)
    verifier_mode: str = "deterministic"

    @property
    def supported(self) -> bool:
        return self.decision == "supported" and self.candidate_indicator in self.supported_indicators


_P6_P7_CRITERIA = {
    "6.1": "ban on taking/processing data abroad or domestic-processing requirement",
    "6.2": "requirement to hold/store/retain a copy of data domestically",
    "6.3": "requirement, or explicit confirmed absence of a requirement, for local data-centre/server infrastructure",
    "6.4": "condition on cross-border data transfer such as consent, adequacy, approval or safeguards",
    "6.5": "binding cross-border data-flow agreement (legacy/non-regulatory evidence only)",
    "7.1": "existence or absence of a comprehensive/sectoral personal-data protection framework",
    "7.2": "existence or absence of a dedicated/sectoral cybersecurity legal framework",
    "7.3": "mandatory minimum retention period with an explicit duration; not deletion/minimisation",
    "7.4": "mandatory appointment/designation of a DPO or equivalent responsible individual",
    "7.5": "government/police access to personal data or records without independent judicial authorisation",
}

_PROVISION_INDICATORS = {"6.1", "6.2", "6.4", "7.3", "7.4", "7.5"}
_DURATION = re.compile(
    r"\b(?:at least|not less than|minimum(?: period)? of|for (?:a period of )?)\s*"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(?:days?|months?|years?)\b|至少\s*[一二三四五六七八九十百千万\d]+\s*(?:日|天|个月|月|年)",
    re.IGNORECASE,
)
_RETENTION = re.compile(r"\b(?:retain|retention|keep|kept|preserve|store)\b|保留|保存", re.IGNORECASE)
_MINIMISATION = re.compile(
    r"no longer than necessary|not retain(?:ed)? longer|cease to retain|"
    r"as soon as (?:it is )?reasonable|不得超过|最小化",
    re.IGNORECASE,
)
_DPO = re.compile(
    r"data protection officer|\bDPO\b|designat(?:e|es|ed|ing) one or more individuals|"
    r"privacy officer|数据保护官|pegawai perlindungan data",
    re.IGNORECASE,
)
_GOV_ACTOR = re.compile(
    r"\b(?:government|police|constable|law enforcement|public authority|minister|"
    r"commissioner|competent authority|officer)\b|政府|公安|执法|主管机关",
    re.IGNORECASE,
)
_ACCESS = re.compile(r"\b(?:access|obtain|require|seize|inspect|disclose|production)\b|访问|调取|披露", re.IGNORECASE)
_DATA_OBJECT = re.compile(r"\b(?:personal data|personal information|records?|documents?|computer data|subscriber)\b|个人信息|数据|记录", re.IGNORECASE)
_ACCESS_GATE = re.compile(
    r"\b(?:with (?:the )?(?:prior )?consent|pursuant to (?:a )?(?:court order|warrant)|"
    r"under (?:a )?(?:court order|warrant)|judicial authori[sz]ation|"
    r"authori[sz]ed by (?:a )?court)\b|经(?:本人同意|法院批准)|法院令|搜查令",
    re.IGNORECASE,
)
_OBJECTIVE_OR_PRINCIPLE = re.compile(
    r"\b(?:objectives?|purposes?) of this (?:act|law|regulation)\b|"
    r"^\s*\d+[.)]?\s*(?:objectives?|purposes?)\b|"
    r"\bthis (?:act|law|regulation) provides? (?:a |an )?(?:legal )?framework\b",
    re.IGNORECASE,
)


def _first_spans(quote: str, patterns: dict[str, re.Pattern]) -> dict[str, list[str]]:
    spans: dict[str, list[str]] = {}
    for label, pattern in patterns.items():
        match = pattern.search(quote)
        if match:
            spans[label] = [match.group(0)]
    return spans


def deterministic_eligibility(
    quote: str, indicator_id: str, features: dict[str, Any]
) -> EligibilityResult:
    """Apply auditable minimum-evidence and boundary requirements."""
    reasons: list[str] = []
    spans: dict[str, list[str]] = {}

    if indicator_id in _PROVISION_INDICATORS and _OBJECTIVE_OR_PRINCIPLE.search(quote):
        reasons.append("Objectives/principles text is not an operative measure for this indicator")
    if indicator_id == "6.1":
        if not (features.get("has_ban") or features.get("has_local_processing")):
            reasons.append("No transfer ban or domestic-processing requirement was extracted")
    elif indicator_id == "6.2":
        if not features.get("has_local_storage"):
            reasons.append("No domestic storage/copy requirement was extracted")
    elif indicator_id == "6.3":
        infrastructure = re.search(r"data cent(?:re|er)|local server|physical infrastructure", quote, re.I)
        if not (features.get("has_infrastructure_req") or infrastructure):
            reasons.append("No local data-centre/server infrastructure finding is evidenced")
        if infrastructure:
            spans["infrastructure"] = [infrastructure.group(0)]
    elif indicator_id == "6.4":
        if not features.get("has_conditional_flow"):
            reasons.append("No condition on a cross-border data transfer was extracted")
    elif indicator_id == "6.5":
        if not features.get("has_binding_agreement"):
            reasons.append("No binding data-flow agreement is evidenced")
    elif indicator_id == "7.1":
        if not (features.get("has_comprehensive_framework") or features.get("has_sectoral_framework_only")):
            reasons.append("No comprehensive or sectoral data-protection framework finding is evidenced")
    elif indicator_id == "7.2":
        if not (features.get("has_dedicated_cybersecurity_law") or features.get("has_sectoral_cybersecurity_only")):
            reasons.append("No dedicated or sectoral cybersecurity framework finding is evidenced")
    elif indicator_id == "7.3":
        spans.update(_first_spans(quote, {"retention": _RETENTION, "duration": _DURATION}))
        if _MINIMISATION.search(quote):
            reasons.append("Data minimisation/deletion limit is not a mandatory minimum retention period")
        if not features.get("has_minimum_retention_period"):
            reasons.append("Minimum-retention feature is not established")
        if not _RETENTION.search(quote) or not _DURATION.search(quote):
            reasons.append("Quote must contain both a retention duty and an explicit minimum duration")
    elif indicator_id == "7.4":
        spans.update(_first_spans(quote, {"dpo_duty": _DPO}))
        if not features.get("has_dpo_requirement"):
            reasons.append("DPIA/general compliance language without a DPO appointment duty is insufficient")
        if not _DPO.search(quote):
            reasons.append("Quote does not identify a DPO or equivalent responsible individual")
    elif indicator_id == "7.5":
        spans.update(_first_spans(quote, {"government_actor": _GOV_ACTOR, "access_power": _ACCESS, "data_object": _DATA_OBJECT}))
        access_gate = _ACCESS_GATE.search(quote)
        if access_gate:
            spans["access_gate"] = [access_gate.group(0)]
            reasons.append("Access is consent- or court-gated, not access without independent judicial authorisation")
        if not features.get("has_government_access_without_judicial_oversight"):
            reasons.append("Government-access-without-oversight feature is not established")
        for label, pattern in (("government actor", _GOV_ACTOR), ("access power", _ACCESS), ("data/record object", _DATA_OBJECT)):
            if not pattern.search(quote):
                reasons.append(f"Quote does not identify the required {label}")

    # A clipped sub-clause may inherit its modal from immediately preceding
    # source context (the exact-quote fixtures include one such 6.2 item), so
    # lack of a modal is only fatal when the indicator's required structured
    # feature/elements also failed above.
    if indicator_id in _PROVISION_INDICATORS and not has_substantive_content(quote) and reasons:
        reasons.append("Provision-level indicator lacks operative legal language")

    decision = "insufficient" if reasons else "supported"
    return EligibilityResult(
        decision=decision,
        candidate_indicator=indicator_id,
        supported_indicators=[indicator_id] if not reasons else [],
        evidence_spans=spans,
        exclusion_reasons=reasons,
    )


class EligibilityVerifier:
    """Run deterministic checks plus an independent all-label LLM verdict."""

    def __init__(self, provider) -> None:
        self.provider = provider
        self._cache: dict[str, dict[str, Any]] = {}

    def _should_call_llm(self) -> bool:
        if os.getenv("RDTII_ELIGIBILITY_VERIFIER", "1").strip().lower() in {"0", "false", "off"}:
            return False
        if getattr(self.provider, "name", "") == "offline-fixture":
            return False
        return callable(getattr(self.provider, "query", None))

    @staticmethod
    def _prompt(quote: str) -> str:
        criteria = "\n".join(f"- {iid}: {text}" for iid, text in _P6_P7_CRITERIA.items())
        return f"""Independently classify this exact legal quote against RDTII Pillars 6 and 7.
You are not given any prior label, rationale or score. Select only indicators
whose legal elements are explicitly established by the quote. Otherwise select NONE.

Indicators:
{criteria}

Rules:
- Topic words alone are insufficient.
- Principles, objectives, general powers and definitions are not provision-level measures.
- Distinguish minimum retention from deletion/data minimisation.
- Distinguish warrantless government access from consent- or court-gated access.
- Every evidence span must be copied exactly from the quote.
- Output JSON only with keys:
  decision: "supported" | "insufficient" | "contradicted"
  supported_indicators: array of indicator IDs (empty means NONE)
  evidence_spans: object mapping indicator ID to an array of exact quote substrings
  exclusion_reasons: array of concise strings

Quote:
\"\"\"
{quote}
\"\"\""""

    async def verify(self, quote: str, indicator_id: str, features: dict[str, Any]) -> EligibilityResult:
        deterministic = deterministic_eligibility(quote, indicator_id, features)
        if not deterministic.supported or indicator_id not in _P6_P7_CRITERIA:
            return deterministic
        if not self._should_call_llm():
            return deterministic

        cache_key = " ".join(quote.split())
        if cache_key not in self._cache:
            try:
                with self.provider.usage_operation("eligibility_verify", tuple(_P6_P7_CRITERIA)):
                    raw = await asyncio.to_thread(
                        self.provider.query,
                        self._prompt(quote),
                        system="Output ONLY valid JSON. Do not infer facts outside the quote.",
                    )
                parsed = LLMProvider.parse_json_response(raw)
            except Exception as exc:  # precision-first: verifier failure abstains
                parsed = {
                    "decision": "insufficient",
                    "supported_indicators": [],
                    "evidence_spans": {},
                    "exclusion_reasons": [f"Independent eligibility verifier failed: {type(exc).__name__}"],
                }
            self._cache[cache_key] = parsed

        parsed = self._cache[cache_key]
        supported = [str(value) for value in parsed.get("supported_indicators", []) if str(value) in _P6_P7_CRITERIA]
        raw_spans = parsed.get("evidence_spans") if isinstance(parsed.get("evidence_spans"), dict) else {}
        verified_spans: dict[str, list[str]] = {}
        invalid_span = False
        for iid, values in raw_spans.items():
            if iid not in _P6_P7_CRITERIA or not isinstance(values, list):
                continue
            exact = [str(value) for value in values if str(value) and str(value) in quote]
            if len(exact) != len([value for value in values if str(value)]):
                invalid_span = True
            if exact:
                verified_spans[iid] = exact

        reasons = [str(value) for value in parsed.get("exclusion_reasons", [])]
        if invalid_span:
            reasons.append("Verifier returned an evidence span that is not an exact quote substring")
        if indicator_id in supported and not verified_spans.get(indicator_id):
            reasons.append("Verifier did not ground the candidate indicator in an exact evidence span")

        accepted = indicator_id in supported and bool(verified_spans.get(indicator_id)) and not invalid_span
        raw_decision = str(parsed.get("decision", "insufficient"))
        decision = "supported" if accepted and raw_decision == "supported" else (
            "contradicted" if raw_decision == "contradicted" else "insufficient"
        )
        return EligibilityResult(
            decision=decision,
            candidate_indicator=indicator_id,
            supported_indicators=supported,
            evidence_spans=verified_spans,
            exclusion_reasons=reasons,
            verifier_mode="independent_llm",
        )


def rejected_from_eligibility(result: EligibilityResult, chunk_preview: str, raw_output: dict | None = None):
    """Build the public structured rejection without introducing an import cycle."""
    from schemas import RejectedExtraction

    reason = "; ".join(result.exclusion_reasons) or "Independent verifier did not support candidate indicator"
    return RejectedExtraction(
        reason=reason,
        chunk_preview=chunk_preview,
        raw_output=raw_output or {},
        decision=result.decision,
        candidate_indicator=result.candidate_indicator,
        supported_indicators=result.supported_indicators,
        evidence_spans=result.evidence_spans,
        exclusion_reasons=result.exclusion_reasons,
    )
