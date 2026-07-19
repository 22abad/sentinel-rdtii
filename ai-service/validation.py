"""Anti-hallucination validation layer.

Each extracted mapping passes through a deterministic rule engine before
being accepted.  Rules catch the common failure modes documented in the
hackathon feedback:

  - Section headers passed off as substantive provisions
  - Objectives / purposes / interpretation clauses treated as evidence
  - Procedural boilerplate ("the Commission shall") scored as a norm
  - Same quote mapped to too many indicators (overmatch)
  - Cross-language semantic drift (via embedding similarity)

Architecture
------------
Validation never modifies the LLM's raw output.  It either:
  - **passes** the mapping through unchanged,
  - **flags** the mapping (sets ``requires_human_review=True`` + reasons), or
  - **rejects** the mapping (removes it from the output, like quote
    verification does).

This layer runs *after* quote verification and scoring, so it has access to
the final ``IndicatorMapping``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Public types ────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Outcome of a single validation check on one mapping."""

    level: str = "pass"          # "pass" | "flag" | "reject"
    reasons: list[str] = field(default_factory=list)


# ── State shared across all extractions of the same document ────────────

_quote_registry: dict[str, set[str]] = {}
"""Maps a normalised quote → set of indicator IDs it has been used for.

Populated during validation so cross-reference checks can detect when the
same source passage is being over-applied.
"""


def reset_quote_registry() -> None:
    _quote_registry.clear()


def _norm_quote(quote: str) -> str:
    """Collapse whitespace and lowercase for cross-reference matching."""
    return " ".join(quote.lower().split())


# ── Rules ───────────────────────────────────────────────────────────────

_SECTION_HEADER_PATTERNS: list[re.Pattern] = [
    re.compile(r"^PART\s+(I{1,3}|IV?|V?I{0,3})\s*[—–\-]\s*\w", re.IGNORECASE),
    re.compile(r"^\w+\s+—\s+\w+\s+of\s+\w+", re.IGNORECASE),
    re.compile(r"^Arrangement\s+of\s+Sections", re.IGNORECASE),
    re.compile(r"^Schedule$", re.IGNORECASE),
    re.compile(r"^\d+\.\s{2,}(Objectives|Application|Interpretation|Citation)", re.IGNORECASE),
]


# A provision carries an obligation verb; a heading is a topic label. We
# require an auxiliary/modal so a bare participle in a heading ("Consent
# required") does NOT count, while "consent is required" / "shall provide" do.
_OPERATIVE_VERB_RE = re.compile(
    r"\b(?:shall|must|may(?:\s+not)?|hendaklah|mestilah|wajib|dilarang|"
    r"tidak\s+boleh|"
    r"(?:is|are|be|been|were|was)\s+(?:not\s+)?"
    r"(?:required|prohibited|permitted|entitled|liable|obliged|obligated|"
    r"responsible|allowed|deemed|bound|restricted|guaranteed)|"
    r"(?:shall|must|may)\s+not)\b",
    re.IGNORECASE,
)
_SECTION_MARKER_RE = re.compile(
    r"^\s*(?:(?i:section|article|art\.?|clause|regulation|part|schedule)\s*)?"
    r"[\dIVXLC]+[.)\-\s]*",
)
_NUMBERED_START_RE = re.compile(
    r"^\s*(?:(?i:section|article|art\.?|clause|part|regulation)\s+)?[\dIVXLC]+[.)]",
)
# CJK / Japanese / Korean / Thai. The short-label heading heuristic below is
# English-designed (word counting via \w+ and English obligation verbs), so it
# must NOT run on these scripts — a CJK provision has no spaces (one giant
# "word") and no "shall/must", and would be wrongly flagged as a heading.
_NON_LATIN_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯฀-๿]")
# A statute *name* ("Personal Data Protection Act 2012", "Privacy Act 1988",
# "… (Act 709)") is a proper-noun citation, not a section heading — and is
# legitimate evidence for framework-existence indicators. Statute word + a year
# (or an "(Act NNN)" number) distinguishes it from a topic heading like
# "Application of this Act".
_STATUTE_TITLE_RE = re.compile(
    r"\b(?:Act|Law|Ordinance|Regulations?|Decree|Code|Statute)\b[^,;.]*\b(?:19|20)\d{2}\b"
    r"|\(\s*Act\s+\d+\s*\)",
    re.IGNORECASE,
)


def _continues_in_context(quote: str, context: str) -> bool:
    """True when an occurrence of the quote runs on into more substantive text
    on the same line — a mid-sentence fragment of a provision, not a heading
    standing on its own line."""
    start = 0
    while (idx := context.find(quote, start)) >= 0:
        end = idx + len(quote)
        newline = context.find("\n", end)
        tail = context[end:] if newline < 0 else context[end:newline]
        if re.search(r"[A-Za-z0-9]", tail):
            return True
        start = idx + 1
    return False


def is_section_header(quote: str, context: str | None = None) -> bool:
    """Heuristic: a line that looks like a Part / Section heading only."""
    t = quote.strip()
    if len(t) > 120:
        return False
    for pat in _SECTION_HEADER_PATTERNS:
        if pat.search(t):
            return True
    # Single-line all-caps headings
    if t.isupper() and 5 < len(t) < 100 and not t.endswith("."):
        return True
    # A short Latin-script topic label with NO obligation verb ("21. Access to
    # personal data", "Consent required") — the marginal note, not the rule
    # under it. Long verb-less text (a definition) is spared by the length
    # guard; non-Latin scripts are skipped entirely (see _NON_LATIN_RE).
    if (
        not _NON_LATIN_RE.search(t)
        and not _OPERATIVE_VERB_RE.search(t)
        and not _STATUTE_TITLE_RE.search(t)
    ):
        # Context exemption for this weakest heuristic only: a verb-less span
        # that continues into more provision text on the same source line is a
        # list-limb fragment (e.g. "(c) kept in Malaysia, except as otherwise
        # approved …"), not a marginal note. Hard patterns above still reject
        # regardless of context.
        if context and _continues_in_context(t, context):
            return False
        body = _SECTION_MARKER_RE.sub("", t).strip()
        words = re.findall(r"\w+", body)
        if words and (len(words) <= 8 or bool(_NUMBERED_START_RE.match(t))):
            return True
    return False


_OBJECTIVE_KEYWORDS = [
    "objective", "purpose", "application", "interpretation",
    "commencement", "citation", "extent", " overriding ",
    "scope of", "guaranteed under the constitution",
    "strengthen the legal foundations",
    "provide a legal framework",
    "safeguard the fundamental rights",
    "promote data processing practices",
    "strengthen the national digital economy",
]


def is_objectives_clause(quote: str) -> bool:
    """Check if the quote appears to be from an objectives / purposes section."""
    t = quote.lower().strip()
    # Section number followed by "Objectives" / "Purpose" etc.
    if re.match(r"^\d+\.\s*(objectives|purpose|application|interpretation)\b", t):
        return True
    # "The objectives of this Act are to" pattern (AU drafting says "objects").
    # t is lowercased above — the original pattern's (Act|Law|Regulation) could
    # never match.
    if re.search(r"\b(objects?|objectives|purposes?) of this (act|law|regulation)\s+are\b", t):
        return True
    # "This Act provides a legal framework for" → objectives language
    if re.search(r"this (act|law|regulation) provides?\s+(a|an)\s+(legal\s+)?framework", t):
        return True
    # Keyword match — but never against a quote that carries operative
    # language: "for the purposes of" / "to the extent that" are ubiquitous in
    # substantive provisions, and the bare keywords ("purpose", "extent")
    # previously misfired on them (e.g. Cyber Security Act 2024 s40(4)).
    if any(sig.search(t) for sig in _SUBSTANTIVE_SIGNALS):
        return False
    for kw in _OBJECTIVE_KEYWORDS:
        if kw in t:
            return True
    return False


_SUBSTANTIVE_SIGNALS: list[re.Pattern] = [
    re.compile(r"\bshall\b"),
    re.compile(r"\bmust\b"),
    re.compile(r"\bshall not\b"),
    re.compile(r"\bprohibited\b"),
    re.compile(r"\brequired to\b"),
    re.compile(r"\bentitled to\b"),
    re.compile(r"\bright to\b"),
    re.compile(r"\bobligation\b"),
    re.compile(r"\bpenalty\b"),
    re.compile(r"\bfine\b"),
    re.compile(r"\bimprisonment\b"),
    re.compile(r"\bsanction\b"),
    re.compile(r"\bcomply with\b"),
    re.compile(r"\benforce\b"),
    re.compile(r"\bnotify\b"),
    re.compile(r"\bregister\b"),
    re.compile(r"\bconsent\b"),
    re.compile(r"\bwithdraw\b"),
]

_PROCEDURAL_ONLY_SIGNALS: list[re.Pattern] = [
    re.compile(r"\bcommission shall\b", re.IGNORECASE),
    re.compile(r"\bcouncil shall\b", re.IGNORECASE),
    re.compile(r"\bminister may\b", re.IGNORECASE),
    re.compile(r"\bestablishment of\b", re.IGNORECASE),
    re.compile(r"\bappointment of\b", re.IGNORECASE),
    re.compile(r"\bconstitution of\b", re.IGNORECASE),
    re.compile(r"\b there is established\b", re.IGNORECASE),
    re.compile(r"\bfunds of\b", re.IGNORECASE),
    re.compile(r"\bfinancial provisions?\b", re.IGNORECASE),
    re.compile(r"\bstaff regulations?\b", re.IGNORECASE),
    re.compile(r"\bpension\b", re.IGNORECASE),
    re.compile(r"\blegal proceedings?\b", re.IGNORECASE),
    re.compile(r"\blimitation of suits?\b", re.IGNORECASE),
    re.compile(r"\b indemnity\b", re.IGNORECASE),
]


def has_substantive_content(quote: str) -> bool:
    """Return False if the quote is all procedural boilerplate (no norm)."""
    t = quote.lower()
    # Must have at least one substantive signal
    has_signal = any(p.search(t) for p in _SUBSTANTIVE_SIGNALS)
    if not has_signal:
        return False
    # Check if it's purely procedural
    proc_matches = [p.search(t) for p in _PROCEDURAL_ONLY_SIGNALS]
    proc_count = sum(1 for m in proc_matches if m)
    # If >80% of the match density is procedural, flag it
    if proc_count >= 2 and not any(p.search(t) for p in _SUBSTANTIVE_SIGNALS if p not in _PROCEDURAL_ONLY_SIGNALS):
        return False
    return True


_MULTI_INDICATOR_THRESHOLD = 3
"""If the same quote is used for >= this many distinct indicators, flag it."""


def check_cross_reference(quote: str, indicator_id: str) -> list[str]:
    """Detect when the same quote is being over-applied across indicators."""
    nq = _norm_quote(quote)
    if nq not in _quote_registry:
        _quote_registry[nq] = set()
    _quote_registry[nq].add(indicator_id)
    if len(_quote_registry[nq]) >= _MULTI_INDICATOR_THRESHOLD:
        return [
            f"Quote overmatch: same passage mapped to "
            f"{len(_quote_registry[nq])} indicators "
            f"({', '.join(sorted(_quote_registry[nq]))})"
        ]
    return []


_TRANSFER_TERM = re.compile(
    r"\b(?:transfer(?:red|ring|s)?|disclos(?:e|ed|es|ure)|export(?:ed|ing|s)?)\b|"
    r"(?:数据|个人信息|信息)?出境|跨境(?:传输|提供)?|向境外提供|传输(?:至|到)?境外|境外传输",
    re.IGNORECASE,
)
_CONDITIONAL_FLOW_TERM = re.compile(
    r"\b(?:except\s+in\s+accordance|subject\s+to|provided\s+that|consent|"
    r"adequacy|security\s+assessment|standard\s+contract|comparable\s+"
    r"(?:protection|standard)|standard\s+of\s+protection|adequate\s+protection|"
    r"legally\s+enforceable\s+obligations?)\b|"
    r"(?:取得|获得|经).{0,20}同意|安全评估|标准合同|个人信息保护认证|"
    r"充分性(?:决定|认定)?|可比(?:的)?保护(?:水平|标准)|除非|"
    r"符合.{0,20}(?:条件|要求)|依照.{0,20}规定",
    re.IGNORECASE,
)
_LOCAL_PROCESSING_TERM = re.compile(
    r"\b(?:process(?:ed|ing)?\s+(?:locally|within\s+the\s+(?:country|territory))|"
    r"local\s+processing|data\s+locali[sz]ation)\b|境内处理|本地处理",
    re.IGNORECASE,
)
_ABSOLUTE_TRANSFER_BAN = re.compile(
    r"\b(?:(?:must|shall)\s+not\b.{0,80}\btransfer(?:red|ring|s)?|"
    r"prohibit(?:ed|s|ion)?\b.{0,80}\btransfer(?:red|ring|s)?|"
    r"ban\s+on\s+transfer(?:red|ring|s)?)\b|"
    r"(?:严禁|禁止|不得).{0,40}(?:出境|跨境|向境外提供|传输(?:至|到)?境外|境外传输)",
    re.IGNORECASE,
)


def is_conditional_transfer_without_6_1_requirement(quote: str) -> bool:
    """True when the exact quote is a 6.4 condition, not a 6.1 restriction.

    The classifier deliberately produces a broad shortlist. This check runs on
    the extractor's verified quote, so a consent clause elsewhere in a long
    article cannot suppress a distinct local-processing or absolute-ban clause.
    """

    if not quote or _LOCAL_PROCESSING_TERM.search(quote):
        return False

    conditional_transfer = False
    unconditional_ban = False
    segments = [
        segment.strip()
        for segment in re.split(r"(?<=[.;。；])\s*|[\r\n]+", quote)
        if segment.strip()
    ]
    for segment in segments:
        if not _TRANSFER_TERM.search(segment):
            continue
        conditional = bool(_CONDITIONAL_FLOW_TERM.search(segment))
        if conditional:
            conditional_transfer = True
        elif _ABSOLUTE_TRANSFER_BAN.search(segment):
            unconditional_ban = True

    return conditional_transfer and not unconditional_ban


# ── Multi-language embedding similarity (optional) ─────────────────────


_embedder = None


def _get_embedder():
    """Lazy-load the embedding model (nomic-embed-text via sentence-transformers).

    Only called when cross-language validation is needed. Cached at module
    level — this runs once per mapping, and without the cache every call
    reloads the ~500MB model from disk (and re-hits the HF Hub).
    """
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
    return _embedder


_INDICATOR_CANONICAL_PHRASES: dict[str, list[str]] = {
    "1.1": ["tariff", "customs duty"],
    "2.1": ["public procurement", "government tender"],
    "3.1": ["foreign direct investment", "foreign ownership"],
    "4.1": ["intellectual property", "patent", "copyright"],
    "5.1": ["telecom regulation", "broadband", "frequency spectrum"],
    "5.3": ["government equity", "state owned telecom", "majority stake"],
    "6.1": ["transfer data abroad", "data localization", "restrict cross border transfer"],
    "6.2": ["local storage", "store data locally"],
    "6.3": ["local data centre", "local server requirement"],
    "6.4": ["consent", "adequacy decision", "standard contractual clause", "prior authorization"],
    "6.5": ["free flow of data", "trade agreement", "digital economy agreement"],
    "7.1": ["personal data protection", "privacy law", "data protection framework"],
    "7.2": ["cybersecurity", "cybercrime", "security measure"],
    "7.3": ["data retention period", "minimum retention", "retain records"],
    "7.4": ["data protection officer", "dpo", "data protection impact assessment"],
    "7.5": ["law enforcement access", "government surveillance", "national security"],
    "8.1": ["intermediary liability", "safe harbor"],
    "9.1": ["illegal content", "content moderation"],
    "10.1": ["non tariff measure", "trade restriction"],
    "11.1": ["technical standard", "conformity assessment"],
    "12.1": ["online sale", "electronic signature"],
}


def embedding_similarity_check(quote: str, indicator_id: str) -> list[str]:
    """Compute embedding similarity between quote and canonical indicator phrases.

    If similarity is below threshold for all canonical phrases, flag it as a
    potential semantic mismatch (the quote may not actually relate to the
    indicator despite keyword matching).
    """
    try:
        model = _get_embedder()
    except Exception:
        return []  # embedder not available, skip silently

    phrases = _INDICATOR_CANONICAL_PHRASES.get(indicator_id, [])
    if not phrases:
        return []

    try:
        q_emb = model.encode(quote, normalize_embeddings=True)
        p_embs = model.encode(phrases, normalize_embeddings=True)
    except Exception:
        return []

    import numpy as np
    sims = np.dot(p_embs, q_emb)
    best = float(sims.max())
    if best < 0.25:
        return [f"Low semantic similarity ({best:.2f}) between quote and canonical '{indicator_id}' phrases — possible wrong mapping"]
    if best < 0.40:
        return [f"Marginal semantic similarity ({best:.2f}) for indicator {indicator_id} — verify mapping"]
    return []


# ── Entry point ─────────────────────────────────────────────────────────


def validate_mapping(
    mapping,
    *,
    quote: str,
    chunk_text: str,
    indicator_id: str,
    features: dict,
    include_semantic_check: bool = True,
    track_cross_reference: bool = True,
) -> ValidationResult:
    """Run all deterministic checks on one mapping.

    Parameters
    ----------
    mapping : IndicatorMapping
        The mapping to validate (already built, pre-yield).
    quote : str
        The verbatim_quote (for convenience).
    chunk_text : str
        The full chunk text (for context).
    indicator_id : str
        RDTII indicator ID e.g. ``"7.1"``.
    features : dict
        Feature dict (for additional context).

    Returns
    -------
    ValidationResult
        ``level`` is one of ``"pass"``, ``"flag"``, ``"reject"``.
    """
    result = ValidationResult()

    # A verified conditional-transfer quote belongs to 6.4, even if broad
    # shortlist terms such as "must not transfer ... except" also triggered 6.1.
    if indicator_id == "6.1" and is_conditional_transfer_without_6_1_requirement(quote):
        result.level = "reject"
        result.reasons.append(
            "Conditional cross-border transfer safeguard belongs to indicator 6.4, "
            "not a 6.1 ban or local-processing requirement"
        )
        return result

    # 1. Section header → reject (no substantive content)
    if is_section_header(quote, chunk_text):
        result.level = "reject"
        result.reasons.append("Quote is a section/part heading, not a substantive provision")
        return result

    # 2. Objectives clause → flag (low confidence)
    if is_objectives_clause(quote):
        result.level = "flag"
        result.reasons.append("Quote appears to be from objectives/purposes section — not substantive evidence")

    # 3. Substantive content check → flag if procedural only
    if not has_substantive_content(quote):
        if result.level == "pass":
            result.level = "flag"
        result.reasons.append("Quote lacks normative language (shall/must/prohibition) — may be informational only")

    # 4. Cross-reference overmatch → flag
    if track_cross_reference:
        xref_reasons = check_cross_reference(quote, indicator_id)
        if xref_reasons:
            if result.level == "pass":
                result.level = "flag"
            result.reasons.extend(xref_reasons)

    # 5. Embedding similarity → flag if needed (expensive, run less frequently)
    if include_semantic_check and len(quote.split()) > 5:
        sim_reasons = embedding_similarity_check(quote, indicator_id)
        if sim_reasons:
            if result.level == "pass":
                result.level = "flag"
            result.reasons.extend(sim_reasons)

    return result
