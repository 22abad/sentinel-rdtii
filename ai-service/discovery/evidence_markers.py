"""Privacy-safe content markers for indicator-specific live smoke checks.

The validator records marker names, never the fetched legal text.  Smoke cases
can therefore prove that an expected provision and its operative language were
present without copying treaty or statute bodies into reports.
"""

from __future__ import annotations

import re


_MARKER_PATTERNS: dict[str, tuple[str, ...]] = {
    "article_23": (r"\barticle\s+23\b",),
    "article_14_11": (r"\barticle\s+14[.\s]+11\b",),
    "article_4_3": (r"\barticle\s+4[.\s]+3\b",),
    "section_12a": (
        r"\bsection\s+12\s*a\b",
        r"\b12\s*a\s*[.]?\s*[(]1[)]",
        r"\bseksyen\s+12\s*a\b",
    ),
    "cross_border_transfer_information": (
        r"\bcross[- ]border\s+transfer\s+of\s+information\s+by\s+electronic\s+means\b",
    ),
    "neither_party_shall_prohibit_or_restrict": (
        r"\bneither\s+party\s+shall\s+prohibit\s+or\s+restrict\b",
    ),
    "each_party_shall_allow": (
        r"\beach\s+party\s+shall\s+allow\s+the\s+cross[- ]border\s+transfer\b",
    ),
    "legitimate_public_policy_exception": (
        r"\blegitimate\s+public\s+policy\s+objective\b",
    ),
    "arbitrary_or_unjustifiable_discrimination": (
        r"\barbitrary\s+or\s+unjustifiable\s+discrimination\b",
    ),
    "no_greater_than_required": (
        r"\b(?:does\s+not|do\s+not)\s+impose\s+restrictions?.{0,120}\bgreater\s+than\s+(?:are|is)\s+required\b",
    ),
    "data_controller_shall_appoint_dpo": (
        r"\ba\s+data\s+controller\s+shall\s+appoint\s+one\s+or\s+more\s+data\s+protection\s+officers?\b",
    ),
    "data_processor_shall_appoint_dpo": (
        r"\bdata\s+processor\s+shall\s+appoint\s+one\s+or\s+more\s+data\s+protection\s+officers?\b",
    ),
    "mandatory_dpo_appointment": (
        r"\bmandatory\s+requirement.{0,120}\bdata\s+protection\s+officer\b",
        r"\bpengawal\s+data\s+dan\s+pemproses\s+data\s+hendaklah\s+melantik\s+seorang\s+atau\s+lebih\s+pegawai\s+perlindungan\s+data\b",
    ),
    "threshold_20000_data_subjects": (
        r"\b20[,.]?000\b.{0,80}\bdata\s+subjects?\b",
        r"\b20[,.]?000\b.{0,80}\bsubjek\s+data\b",
    ),
    "threshold_10000_sensitive_data_subjects": (
        r"\bsensitive\s+personal\s+data.{0,120}\b10[,.]?000\b.{0,80}\bdata\s+subjects?\b",
        r"\bdata\s+peribadi\s+sensitif.{0,120}\b10[,.]?000\b.{0,80}\bsubjek\s+data\b",
    ),
    "regular_and_systematic_monitoring": (
        r"\bregular\s+and\s+systematic\s+monitoring\b",
        r"\bpemantauan\s+berkala\s+dan\s+sistematik\b",
    ),
}


def known_evidence_markers() -> frozenset[str]:
    return frozenset(_MARKER_PATTERNS)


def match_evidence_markers(text: str) -> list[str]:
    """Return stable marker ids found in fetched text.

    Whitespace and soft-hyphen artefacts are normalized so PDF extraction does
    not weaken the checks.  Only marker ids are persisted in validation data.
    """

    normalized = re.sub(r"\s+", " ", text.replace("\u00ad", "")).casefold()
    return sorted(
        marker
        for marker, patterns in _MARKER_PATTERNS.items()
        if any(re.search(pattern, normalized, re.DOTALL) for pattern in patterns)
    )


__all__ = ["known_evidence_markers", "match_evidence_markers"]
