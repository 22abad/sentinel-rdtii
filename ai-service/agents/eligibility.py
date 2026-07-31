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
    #: True when the LLM arm raised (network/parse) rather than returning a
    #: judgement. For the PIPELINE this stays precision-first — an unverified
    #: mapping is still dropped. For the REWARD the distinction is essential:
    #: "the verifier says no" is evidence about the candidate, "the verifier
    #: broke" is evidence about nothing, and scoring the second as 0.0 penalises
    #: whichever candidate happened to hit the error.
    verifier_failed: bool = False

    @property
    def supported(self) -> bool:
        return self.decision == "supported" and self.candidate_indicator in self.supported_indicators


_ALL_CRITERIA = {
    # ── Pillar 1: Tariffs & Trade Defence ──
    "1.4": "anti-dumping or countervailing duty measure on ICT goods",
    # ── Pillar 2: Public Procurement ──
    "2.1": "general public procurement framework or law",
    "2.2": "ICT-specific procurement preferences or domestic preference rules",
    "2.3": "procurement rules for services including ICT/digital services",
    # ── Pillar 3: Foreign Investment ──
    "3.1": "foreign-investment screening or review mechanism for ICT/digital sectors",
    "3.2": "foreign-equity limits in ICT/digital sectors",
    "3.3": "licensing or approval requirement for foreign investors in ICT",
    "3.4": "investment restrictions targeting specific countries or sectors",
    "3.5": "local presence or joint-venture requirement for foreign digital firms",
    # ── Pillar 4: IPR ──
    "4.1": "copyright or related-rights protection for digital content",
    "4.2": "patent protection for software or computer-implemented inventions",
    "4.3": "trademark protection applicable to digital goods/services",
    "4.5": "IP enforcement mechanisms including online/digital infringement",
    "4.6": "trade-secrets or confidential-information protection for digital assets",
    "4.9": "IP-related border measures for digital/ICT goods",
    "4.10": "ISDS or investment-dispute provisions affecting IP in digital trade",
    # ── Pillar 5: Telecom Competition & SOEs ──
    "5.1": "telecom regulatory authority existence and independence",
    "5.2": "foreign-ownership limits in telecom operators",
    "5.3": "state ownership or control of telecom operators",
    "5.4": "accounting-separation or structural-separation requirements for telecom",
    "5.5": "telecom infrastructure-sharing or access obligations",
    "5.7": "independent telecom regulator with rule-making and enforcement powers",
    # ── Pillar 6: Cross-Border Data ──
    "6.1": "ban on taking/processing data abroad or domestic-processing requirement",
    "6.2": "requirement to hold/store/retain a copy of data domestically",
    "6.3": "requirement, or explicit confirmed absence of a requirement, for local data-centre/server infrastructure",
    "6.4": "condition on cross-border data transfer such as consent, adequacy, approval or safeguards",
    "6.5": "binding cross-border data-flow agreement (legacy/non-regulatory evidence only)",
    # ── Pillar 7: Domestic Data Protection ──
    "7.1": "existence or absence of a comprehensive/sectoral personal-data protection framework",
    "7.2": "existence or absence of a dedicated/sectoral cybersecurity legal framework",
    "7.3": "mandatory minimum retention period with an explicit duration; not deletion/minimisation",
    "7.4": "mandatory appointment/designation of a DPO or equivalent responsible individual",
    "7.5": "government/police access to personal data or records without independent judicial authorisation",
    # ── Pillar 8: Intermediary Liability ──
    "8.1": "safe-harbour or liability exemption for internet intermediaries",
    "8.2": "notice-and-takedown or notice-and-action regime for online content",
    "8.3": "mandatory user-identification or SIM-card registration requirements",
    "8.4": "content-moderation or monitoring obligations on internet platforms",
    # ── Pillar 9: Online Content Access ──
    "9.1": "website/social-media blocking or content-restriction orders",
    "9.3": "online advertising restrictions or disclosure requirements",
    "9.4": "internet-shutdown or network-disruption authority",
    # ── Pillar 10: Technology Import/Export ──
    "10.1": "import licensing or restrictions on ICT goods",
    "10.2": "technology-import catalogue or prohibited/restricted technology list",
    "10.3": "local-content or domestic-production requirements for ICT goods; content quotas favouring domestic media (e.g. limits on foreign film/TV imports)",
    "10.4": "export controls on dual-use or encryption technology",
    # ── Pillar 11: Standards & Conformity ──
    "11.1": "mandatory national standards for ICT equipment or services",
    "11.2": "conformity-assessment or certification requirements for ICT products",
    "11.3": "mutual-recognition agreements for ICT conformity assessment",
    "11.4": "encryption or cryptographic standards and certification requirements",
    # ── Pillar 12: E-Commerce ──
    "12.1": "e-commerce law or framework establishing online-transaction validity",
    "12.2": "cross-border e-commerce customs or tax facilitation measures",
    "12.3": "online-consumer-protection or e-commerce dispute-resolution rules",
    "12.4.1": "electronic-signature legal recognition",
    "12.4.2": "electronic-contract formation and validity rules",
    "12.4.3": "online-payment or electronic-money regulatory framework",
    "12.4.4": "paperless-trade facilitation or electronic-documents recognition",
    "12.4.5": "cross-border electronic-payments access for foreign providers",
    "12.4.6": "digital-authentication or identity-verification framework",
    "12.4.7": "electronic-transactions or e-government service legal basis",
    "12.5": "restrictions on online sales of specific goods or services",
    "12.7": "geo-blocking or territorial restrictions on online services",
    "12.8": "data-portability or interoperability requirements for digital platforms",
    "12.9": "source-code or algorithm-disclosure requirements",
}

# For backward compatibility
_P6_P7_CRITERIA = _ALL_CRITERIA

_PROVISION_INDICATORS = {
    # P6/P7: requiring operative provisions (not existence statements)
    "6.1", "6.2", "6.4", "7.3", "7.4", "7.5",
    # P8-P12: provision-level indicators
    "8.2", "8.3", "8.4",  # notice-takedown, SIM reg, content moderation
    "9.1", "9.3",         # site blocking, online ad restrictions
    "10.1", "10.2", "10.3", "10.4",  # import/export controls
    "11.1", "11.2", "11.4",         # standards, certification, encryption
    "12.1", "12.2", "12.3", "12.5", "12.7", "12.8", "12.9",
    "12.4.1", "12.4.2", "12.4.3", "12.4.5",  # e-commerce provisions
}
_DURATION = re.compile(
    r"\b(?:at least|not less than|minimum(?: period)? of|for (?:a period of )?)\s*"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(?:days?|months?|years?)\b|"
    r"至少\s*[一二三四五六七八九十百千万\d]+\s*(?:日|天|个月|月|年)|"
    r"не менее\s*\d+\s*(?:дня|дней|месяца|месяцев|год|года|лет)|"
    r"jangka waktu(?: minimal)?\s*(?:\d+|satu|dua|tiga)\s*(?:hari|bulan|tahun)|"
    r"อย่างน้อย\s*\d+\s*(?:วัน|เดือน|ปี)",
    re.IGNORECASE,
)
_RETENTION = re.compile(r"\b(?:retain|retention|keep|kept|preserve|store)\b|保留|保存|хранить|хранит|хранят|хранение|хранения|menyimpan|retensi|penyimpanan|เก็บรักษา|การเก็บรักษา", re.IGNORECASE)
_MINIMISATION = re.compile(
    r"no longer than necessary|not retain(?:ed)? longer|cease to retain|"
    r"as soon as (?:it is )?reasonable|不得超过|最小化|"
    r"не дольше необходимого|прекратить хранение|"
    r"tidak lebih lama dari yang diperlukan|berhenti menyimpan|"
    r"ไม่เกินระยะเวลาที่จำเป็น|ลบเมื่อไม่จำเป็น",
    re.IGNORECASE,
)
_DPO = re.compile(
    r"data protection officer|\bDPO\b|designat(?:e|es|ed|ing) one or more individuals|"
    r"privacy officer|数据保护官|pegawai perlindungan data|"
    r"pejabat perlindungan data|"
    r"сотрудник по защите данных|специалист по защите данных|"
    r"ответственный за защиту данных|"
    r"เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล|เจ้าหน้าที่คุ้มครองข้อมูล",
    re.IGNORECASE,
)
_GOV_ACTOR = re.compile(
    r"\b(?:government|police|constable|law enforcement|public authority|minister|"
    r"commissioner|competent authority|officer)\b|"
    r"政府|公安|执法|主管机关|"
    r"государство|государственный орган|полиция|правоохранительные органы|"
    r"компетентный орган|министр|уполномоченный|"
    r"pemerintah|polisi|penegak hukum|otoritas publik|"
    r"รัฐบาล|ตำรวจ|เจ้าหน้าที่รัฐ|หน่วยงานของรัฐ",
    re.IGNORECASE,
)
_ACCESS = re.compile(r"\b(?:access|obtain|require|seize|inspect|disclose|production)\b|访问|调取|披露|доступ|получение|изъятие|осмотр|раскрытие|akses|memperoleh|mendapatkan|menginspeksi|การเข้าถึง|เข้าถึง|ได้รับ|ขอให้ส่ง", re.IGNORECASE)
_DATA_OBJECT = re.compile(r"\b(?:personal data|personal information|records?|documents?|computer data|subscriber)\b|个人信息|数据|记录|персональные данные|персональных данных|личные данные|личная информация|data pribadi|informasi pribadi|catatan|dokumen|ข้อมูลส่วนบุคคล|ข้อมูลส่วนตัว|บันทึก|เอกสาร", re.IGNORECASE)
_ACCESS_GATE = re.compile(
    r"\b(?:with (?:the )?(?:prior )?consent|pursuant to (?:a )?(?:court order|warrant)|"
    r"under (?:a )?(?:court order|warrant)|judicial authori[sz]ation|"
    r"authori[sz]ed by (?:a )?court)\b|"
    r"经(?:本人同意|法院批准)|法院令|搜查令|"
    r"согласие|согласия|судебное решение|судебный приказ|ордер|санкция суда|"
    r"persetujuan|dengan persetujuan|perintah pengadilan|surat perintah|izin pengadilan|"
    r"ความยินยอม|คำสั่งศาล|หมายค้น|การอนุญาตของศาล",
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
    # ── Pillar 8-12 deterministic checks (Round-2 expansion) ──
    elif indicator_id == "10.3":
        # Local content / content-quota measures (e.g. foreign audiovisual
        # import caps, domestic-purchase quotas, local-sourcing rules).
        _CONTENT_QUOTA = re.compile(
            r"不得超过|不得低于|must not exceed|shall not exceed|"
            r"总量不超过|占比|配额|quota|%", re.IGNORECASE)
        if _CONTENT_QUOTA.search(quote):
            spans["content_quota"] = [_CONTENT_QUOTA.search(quote).group(0)]
        if not features.get("has_local_content_requirement") and not _CONTENT_QUOTA.search(quote):
            reasons.append("No local-content or content-quota requirement is evidenced")
    elif indicator_id == "10.4":
        # Export controls on dual-use / encryption technology.
        _EXPORT_CTRL = re.compile(
            r"禁止出口|限制出口|不得出口|出口许可|export control|export licence|"
            r"экспортный контроль|запрет экспорта|dilarang ekspor|ห้ามส่งออก", re.IGNORECASE)
        if _EXPORT_CTRL.search(quote):
            spans["export_control"] = [_EXPORT_CTRL.search(quote).group(0)]
        if not features.get("has_export_restriction") and not _EXPORT_CTRL.search(quote):
            reasons.append("No export-restriction/control requirement is evidenced")
    elif indicator_id == "8.4":
        # Content moderation / monitoring obligations on internet platforms.
        _MODERATION = re.compile(
            r"应当删除|应当下架|不得发布|内容审核|及时删除|remove.*content|moderat|"
            r"take.?down|삭제|นำออก", re.IGNORECASE)
        if _MODERATION.search(quote):
            spans["moderation"] = [_MODERATION.search(quote).group(0)]
        if not features.get("has_content_moderation") and not _MODERATION.search(quote):
            reasons.append("No content-moderation or takedown obligation is evidenced")
    elif indicator_id == "9.1":
        # Website / social-media blocking orders.
        _BLOCKING = re.compile(
            r"关闭网站|屏蔽|停止接入|封禁|block(?:ing|ed)?|shut down|suspend.*site|"
            r"закрыть сайт|блокировк", re.IGNORECASE)
        if _BLOCKING.search(quote):
            spans["blocking"] = [_BLOCKING.search(quote).group(0)]
        if not features.get("has_blocking_order") and not _BLOCKING.search(quote):
            reasons.append("No website/social-media blocking order is evidenced")

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
        return f"""Independently classify this exact legal quote against the RDTII 2.1 indicators (all 12 pillars).
You are not given any prior label, rationale or score. Select only indicators
whose legal elements are explicitly established by the quote. Otherwise select NONE.

Indicators:
{criteria}

Rules:
- Topic words alone are insufficient.
- Principles, objectives, general powers and definitions are not provision-level measures.
- 10.3 (local content requirements) includes content quotas that favour domestic media,
  such as limits on foreign film/TV imports or foreign-content quotas.
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
                    # Marked so callers can tell "judged ineligible" from "never
                    # got a judgement". Kept inside the cached payload so a
                    # repeat lookup for the same quote stays consistent.
                    "_verifier_failed": True,
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
            verifier_failed=bool(parsed.get("_verifier_failed")),
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
