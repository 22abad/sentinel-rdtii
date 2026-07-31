"""The PROXY reward — verifiable, label-free, computed on a raw candidate.

This is the objective ``best_of_n`` maximises. Everything in it is computable
from the candidate plus the chunk it came from: no answer key, no GoldenCase,
no LLM call. That is what makes it usable on the seven Round-2 economies,
where labels exist for a handful of cells and the tool has to run on all of
them.

Why these components and not others
-----------------------------------
Each term is a per-candidate stand-in for something the golden harness already
measures in aggregate (``evaluation.metrics._evaluate_core``):

  harness metric                  -> proxy component
  ``citation_exact_match_rate``   -> ``offsets_recover_quote`` gate + ``citation_exactness``
  ``article_citation_accuracy``   -> ``article_clause_specific``
  ``raw_score_accuracy``          -> ``score_in_allowed_tiers`` gate (necessary, not sufficient)
  ``scope_accuracy``              -> ``scope_resolved``
  ``false_positive_rate``         -> ``eligibility_supported`` (agents.eligibility)

The proxy can only ever be a *correlate* of the oracle — a quote can be
perfectly grounded, exactly located, and still be the wrong provision. That is
precisely why ``scripts/rlvr_measure.py`` measures proxy-vs-oracle agreement
instead of assuming it. If the correlation is weak, best-of-N is buying noise
and we should say so rather than ship it.

Deliberately NOT used here
--------------------------
``validation.check_cross_reference`` mutates a module-global quote registry.
Scoring k candidates would register the same passage k times and manufacture
"quote overmatch" flags for the real pipeline. Overmatch is a document-level
property; it stays in the orchestrator's single post-selection validation pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.eligibility import deterministic_eligibility
from chunker import _HEADING_RE
from methodology import get_rule
from validation import is_section_header
from verification import find_quote_offsets, verify_quote


# A citation the grader can follow: "Section 26", "Article 18(2)", "s 46",
# "Reg. 7". A bare "the Act" or an empty string is not a pinpoint cite, and the
# graded feedback was explicit that every row needs one.
_PINPOINT_CLAUSE = re.compile(
    r"(?:section|sec\.?|s\.?|article|art\.?|reg(?:ulation)?\.?|clause|"
    r"para(?:graph)?\.?|rule|item|schedule|principle)"
    r"\s*\d+",
    re.IGNORECASE,
)

# Existence-type indicators: the question is whether a framework EXISTS, so the
# correct evidence is the instrument's title, not an operative clause.
#
# The first measurement run surfaced this the hard way. The reviewed fixtures
# cite 'Privacy Act 1988' (16 chars) and 'Personal Data Protection Act 2012'
# (33 chars) for 7.1 — correct answers that this reward was scoring as
# "boilerplate, too short" and ranking BELOW a manufactured page-dump.
#
# This is the third time the same bug pattern has bitten this codebase: a
# "short and no operative verb means low value" heuristic misfiring on
# structurally different content. It demoted reconstructed tables in RAG
# retrieval (log, 2026-07-22) and it drove the 7.1/7.2 fall-through fix
# (3cf9335). Any heuristic of that shape needs an indicator-class exemption.
EXISTENCE_INDICATORS = frozenset({"7.1", "7.2"})

# Absolute backstop only. Chunk-relative structure (below) does the real work;
# this catches the pathological case where a quote is longer than any citation
# could legitimately be, regardless of how large its chunk was.
QUOTE_DUMP_GATE_CHARS = 2500

# Share of its own chunk a quote may occupy before it stops looking like a
# citation. Generous, because a chunk that IS a single short provision should
# not be punished for being fully quoted — the structural test below is what
# catches genuine over-reach.
CHUNK_COVERAGE_SOFT_LIMIT = 0.75
CHUNK_COVERAGE_FLOOR_VALUE = 0.4


@dataclass(frozen=True)
class RewardComponent:
    """One graded term. ``value`` is in [0, 1]; ``weight`` scales it."""

    name: str
    value: float
    weight: float
    detail: str = ""

    @property
    def contribution(self) -> float:
        return self.value * self.weight


@dataclass(frozen=True)
class ProxyReward:
    """Total proxy reward plus the full breakdown that produced it."""

    total: float
    passed_gates: bool
    failed_gates: tuple[str, ...] = ()
    components: tuple[RewardComponent, ...] = ()
    notes: tuple[str, ...] = field(default=())

    def as_record(self) -> dict:
        return {
            "total": round(self.total, 6),
            "passed_gates": self.passed_gates,
            "failed_gates": list(self.failed_gates),
            "components": {
                c.name: {
                    "value": round(c.value, 6),
                    "weight": c.weight,
                    "detail": c.detail,
                }
                for c in self.components
            },
            "notes": list(self.notes),
        }


# Component weights. Tuned by intent, not by fitting to the golden set — that
# would be the same contamination the oracle/proxy split exists to prevent.
# Citation exactness dominates because it is the one term that is fully
# mechanical and the one the graded feedback punished hardest.
WEIGHTS: dict[str, float] = {
    "citation_exactness": 3.0,
    "article_clause_specific": 2.0,
    "eligibility_supported": 2.0,
    "single_provision": 1.5,
    "not_truncated": 1.5,
    "metadata_complete": 1.5,
    "scope_resolved": 0.5,
}


# A sentence-boundary-alignment component was tried here and REMOVED. Recording
# why, because the idea is superficially attractive and will be proposed again:
#
# The premise — "a real citation starts and ends where a sentence does, a
# fragment is cut mid-clause" — is FALSE for statutory text, which nests:
#
#     (2) The System Operator ... must not: (a) hold the records ...
#
# Quoting the operative prohibition legitimately starts mid-sentence. Measured
# on the reviewed fixtures, only 59% of CORRECT references were boundary
# aligned. Worse, the component is perfectly anti-correlated with the failure
# it was meant to catch: a page-dump of an entire chunk scores 1.0 by
# construction (it starts at the chunk start and ends at the chunk end), so the
# term handed +1.5 weight to the dump and 0.0 to the real provision, and
# page-dump wins went UP.
#
# This is the same trap `chunker.sentence_span` documents: "it can cross clause
# boundaries (fine for reading, not for scoring — that regressed the golden
# set)". Structural tidiness is not evidence quality in legal text.


def _eligibility(
    quote: str, indicator_id: str, data: dict[str, Any]
) -> tuple[float, str]:
    """Reuse the pipeline's own eligibility gate instead of re-deriving it.

    Replaces a hand-rolled ``has_substantive_content and not
    is_objectives_clause`` term that measured worst of every component
    (discrimination 0.045 on 2.0 weight) and was ANTI-correlated on the
    failure that mattered: a page-dump scored 0.727 against the real
    provision's 0.545, because more text means more chance of tripping a
    substantive-language regex.

    ``deterministic_eligibility`` asks the right question — *do this quote's
    legal elements establish this indicator?* — with per-indicator rules the
    project already trusts and reviews: 7.3 needs a retention duty AND an
    explicit duration in the quote; 7.5 needs a government actor, an access
    power and a data object, and is rejected outright when access is consent-
    or warrant-gated; objectives/principles text is excluded for every
    provision-level indicator.

    Only the DETERMINISTIC arm is used here. ``EligibilityVerifier.verify``
    adds a blind all-indicator LLM classification with exact-span grounding,
    but it is async, needs a provider, and self-disables on the offline
    fixture provider. Keeping this reward synchronous and free is what lets
    the measurement stay a reproducible regression gate; the semantic arm
    belongs at inference time, where the orchestrator already calls it.

    Known limit in the offline study: the feature-driven branches read the
    extractor's structured features, and synthetic distractors inherit the
    reference's features, so only the QUOTE-driven checks discriminate there.
    """
    try:
        result = deterministic_eligibility(quote, indicator_id, data)
    except Exception as exc:  # noqa: BLE001 — a verifier crash must not score
        return 0.0, f"eligibility check failed: {type(exc).__name__}"

    if result.supported:
        return 1.0, "eligible for this indicator"
    reason = "; ".join(result.exclusion_reasons) or "not supported"
    return 0.0, reason[:160]


def _not_truncated(quote: str, chunk_text: str) -> tuple[float, str]:
    """Was the quote cut off mid-clause?

    The narrow, survivable version of the boundary idea above. It asks only
    what follows the quote in its chunk, never where the quote begins:

      * chunk continues with a word character, or whitespace then a lowercase
        word  ->  the clause was still running when the quote stopped
      * punctuation, a newline, or the chunk's end  ->  a clean stop

    Crucially this is NEUTRAL on a page-dump — a dump ends at the chunk edge,
    so it scores 1.0 exactly like a good citation — which is precisely how it
    avoids the anti-correlation that killed `boundary_alignment`. It is
    decisive only on truncation, the failure it exists to catch.

    Start position is ignored on purpose: `(2) ... must not: (a) hold the
    records` means a correct quote of the operative prohibition routinely
    begins mid-sentence.
    """
    start, end = find_quote_offsets(quote, chunk_text)
    if start < 0:
        return 0.0, "not locatable in chunk"
    if end >= len(chunk_text):
        return 1.0, "ends at the chunk boundary"

    tail = chunk_text[end:]
    nxt = tail[0]
    if nxt.isalnum():
        return 0.0, f"cut mid-word (chunk continues {tail[:12]!r})"
    if nxt in " \t" and tail.lstrip()[:1].islower():
        return 0.0, f"cut mid-clause (chunk continues {tail[:12]!r})"
    return 1.0, "ends at a clause boundary"


def _single_provision(quote: str, chunk_text: str) -> tuple[float, str]:
    """Did the quote stay inside ONE provision, or swallow its neighbours?

    Two signals, in order of strength:

    1. A structural heading *inside* the quote means it crossed a provision
       boundary — the strongest available evidence of over-reach, and
       independent of length. `_HEADING_RE` is the chunker's own multilingual
       heading pattern, so this stays correct for ZH/TH/ID/VI corpora.
    2. Failing that, the share of its own chunk the quote occupies. Chunk-
       relative rather than absolute: the first measurement run showed an
       absolute ceiling cannot distinguish "a long provision" from "several
       short ones", because it has no idea how big the surrounding provision
       was.
    """
    # Tested across the WHOLE quote, including position 0. An earlier version
    # skipped the first character to tolerate a heading at the start — but a
    # citation that opens with "Section 77  Requirement not to hold..." has
    # swallowed the heading, which is itself the over-reach being detected.
    # That exemption let a full-chunk dump score 0.4 instead of 0.
    if _HEADING_RE.search(quote):
        return 0.0, "contains a section heading — spans multiple provisions"

    if not chunk_text:
        return 1.0, "no chunk context"

    coverage = len(quote) / len(chunk_text)
    if coverage <= CHUNK_COVERAGE_SOFT_LIMIT:
        return 1.0, f"{coverage:.0%} of its chunk"

    over = (coverage - CHUNK_COVERAGE_SOFT_LIMIT) / (1.0 - CHUNK_COVERAGE_SOFT_LIMIT)
    value = 1.0 - over * (1.0 - CHUNK_COVERAGE_FLOOR_VALUE)
    return max(CHUNK_COVERAGE_FLOOR_VALUE, value), f"{coverage:.0%} of its chunk"


def _citation_exactness(quote: str, chunk_text: str) -> tuple[float, str]:
    """How literally the quote was copied.

    Graded rather than binary because the three tiers have genuinely different
    downstream consequences: a strict substring gives reliable offsets, a
    whitespace-only difference still recovers offsets via the stripped-index
    path in ``find_quote_offsets``, and a fuzzy-only match means the model
    paraphrased — which the submission cannot use as a verbatim.
    """
    if quote in chunk_text:
        return 1.0, "strict substring"
    if "".join(quote.split()) in "".join(chunk_text.split()):
        return 0.75, "whitespace-insensitive match"
    if verify_quote(quote, chunk_text, fuzzy=True):
        return 0.35, "fuzzy match only (paraphrase risk)"
    return 0.0, "not found in chunk"


def _allowed_scores(indicator_id: str) -> tuple[float, ...]:
    rule = get_rule(indicator_id)
    return rule.scores if rule else ()


def score_candidate(
    data: dict[str, Any],
    *,
    chunk_text: str,
    indicator_id: str,
    raw_score: float | None = None,
    eligibility_override: tuple[float | None, str] | None = None,
) -> ProxyReward:
    """Score one raw extraction candidate.

    ``data`` is the provider's parsed JSON — the dict the extractor returns,
    before repair, eligibility, or the analyst run. Scoring here is the point:
    best-of-N then multiplies only the extractor call, and the expensive tail
    of the pipeline runs exactly once on the winner.

    ``raw_score`` is optional. When the caller has already run the
    deterministic scorer, passing it in enables the allowed-tier gate; when it
    is None that gate is skipped rather than guessed.
    """
    quote = (data.get("verbatim_quote") or "").strip()
    failed: list[str] = []
    notes: list[str] = []

    # ── Hard gates ───────────────────────────────────────────────────────
    # A candidate failing any of these is not a worse extraction, it is an
    # unusable one. Total collapses to 0 rather than being averaged down, so a
    # hallucinated quote can never out-rank a real one on the strength of tidy
    # metadata.
    if not quote:
        failed.append("quote_present")
        # Nothing else is meaningful without a quote. Note that an empty quote
        # is the *correct* output for a chunk with no qualifying evidence — the
        # selector handles that case in best_of_n, not here.
        return ProxyReward(
            total=0.0,
            passed_gates=False,
            failed_gates=tuple(failed),
            notes=("empty quote — no evidence claimed",),
        )

    if not verify_quote(quote, chunk_text, fuzzy=True):
        failed.append("quote_grounded")

    start, end = find_quote_offsets(quote, chunk_text)
    if start < 0 or end <= start:
        # Mirrors ``evaluation.metrics._citation_is_exact``: offsets that do
        # not recover the quote are a citation failure in the harness, so they
        # are a zero here.
        failed.append("offsets_recover_quote")

    if raw_score is not None:
        allowed = _allowed_scores(indicator_id)
        if allowed and not any(abs(raw_score - a) < 1e-9 for a in allowed):
            failed.append("score_in_allowed_tiers")
            notes.append(
                f"score {raw_score} is not an official tier for {indicator_id} "
                f"(allowed: {', '.join(str(a) for a in allowed)})"
            )

    if is_section_header(quote, chunk_text):
        failed.append("not_a_section_header")

    if len(quote) > QUOTE_DUMP_GATE_CHARS:
        failed.append("quote_not_a_page_dump")
        notes.append(
            f"quote is {len(quote)} chars — a citation, not a page, is required"
        )

    # ── Graded components ────────────────────────────────────────────────
    exactness, exactness_detail = _citation_exactness(quote, chunk_text)
    provision_value, provision_detail = _single_provision(quote, chunk_text)
    intact_value, intact_detail = _not_truncated(quote, chunk_text)

    clause = (data.get("article_clause") or "").strip()
    clause_hit = bool(_PINPOINT_CLAUSE.search(clause))

    # ``eligibility_override`` lets a caller that has already awaited the full
    # ``EligibilityVerifier.verify`` (deterministic arm + blind all-indicator
    # LLM classification with exact-span grounding) feed that verdict in.
    # Keeping it a parameter rather than making this function async is what
    # preserves the reward's two most useful properties: it stays synchronous
    # and free by default, so the offline measurement remains a reproducible
    # regression gate that costs nothing to run.
    # A ``None`` value means the verifier never returned a judgement (it raised).
    # That is not a verdict about this candidate, so the term is dropped from the
    # objective below rather than scored 0.0 — scoring it 0.0 penalises whichever
    # candidate happened to hit the error, which is exactly how a transient API
    # failure handed a page-dump the win over the correct provision in
    # sgp-cpc-7-5-section-20.
    if eligibility_override is not None:
        eligible_value, eligible_detail = eligibility_override
    else:
        eligible_value, eligible_detail = _eligibility(quote, indicator_id, data)
    eligibility_unavailable = eligible_value is None

    present = [
        bool((data.get("source_legislation") or "").strip()),
        bool((data.get("last_update") or "").strip()),
        bool((data.get("source_url") or "").strip()),
    ]
    metadata_value = sum(present) / len(present)

    scope = (data.get("scope") or "").strip().lower()
    scope_value = 1.0 if scope in {"horizontal", "sectoral"} else 0.0

    # For existence-type indicators, the two terms that assume an operative
    # provision are dropped from the objective entirely — not softened. A
    # neutral 1.0 would still shift the weighted mean; removing them from the
    # denominator keeps the remaining terms comparable across indicators.
    is_existence = indicator_id in EXISTENCE_INDICATORS

    components = (
        RewardComponent(
            "citation_exactness",
            exactness,
            WEIGHTS["citation_exactness"],
            exactness_detail,
        ),
        RewardComponent(
            "article_clause_specific",
            1.0 if clause_hit else 0.0,
            WEIGHTS["article_clause_specific"],
            clause or "(none)",
        ),
        RewardComponent(
            "eligibility_supported",
            0.0 if eligibility_unavailable else float(eligible_value or 0.0),
            WEIGHTS["eligibility_supported"],
            eligible_detail,
        ),
        RewardComponent(
            "single_provision",
            provision_value,
            WEIGHTS["single_provision"],
            provision_detail,
        ),
        RewardComponent(
            "not_truncated",
            intact_value,
            WEIGHTS["not_truncated"],
            intact_detail,
        ),
        RewardComponent(
            "metadata_complete",
            metadata_value,
            WEIGHTS["metadata_complete"],
            f"{sum(present)}/3 of law name, date, url",
        ),
        # Low weight on purpose: rewarding "not unknown" nudges the model to
        # guess a scope rather than admit it cannot tell. Kept because an
        # unresolved scope costs a Coverage column the submission needs, but
        # never at a weight that could flip a citation-quality decision.
        RewardComponent(
            "scope_resolved",
            scope_value,
            WEIGHTS["scope_resolved"],
            scope or "unknown",
        ),
    )

    dropped: set[str] = set()

    if is_existence:
        # The evidence is an instrument's TITLE, which frequently IS its whole
        # chunk, so coverage would punish the correct answer.
        dropped.add("single_provision")
        # Eligibility comes off too, but ONLY when an external verdict was
        # supplied. The original exemption kept it on the grounds that the
        # deterministic 7.1/7.2 branches are feature-driven and apply neither
        # the objectives-clause check nor the operative-language backstop — true
        # of that arm, and false of the LLM arm, which substitutes its own
        # judgement and rejects exactly this shape of evidence
        # ("a statement of legislative purpose, not a provision-level measure",
        # sgp-cybersecurity-7-2-framework). Under the LLM arm the term therefore
        # penalises the correct title-style answer and rewards the page-dump
        # that surrounds it — the fifth instance of a provision-shape prior
        # inverting on an existence indicator.
        if eligibility_override is not None:
            dropped.add("eligibility_supported")
        notes.append(
            f"{indicator_id} is an existence-type indicator — the instrument's "
            "title is valid evidence, so the provision-shape terms are not scored"
        )

    if eligibility_unavailable:
        # Abstain, do not penalise. See the eligibility_override comment above.
        dropped.add("eligibility_supported")
        notes.append(
            "eligibility verifier returned no judgement — the term is dropped "
            "from the objective rather than scored 0.0"
        )

    if dropped:
        # Removed from the DENOMINATOR, not softened to a neutral 1.0: a neutral
        # value would still shift the weighted mean and make totals across
        # indicators incomparable.
        components = tuple(c for c in components if c.name not in dropped)

    total_weight = sum(c.weight for c in components)
    graded = sum(c.contribution for c in components) / total_weight if total_weight else 0.0
    passed = not failed

    return ProxyReward(
        total=graded if passed else 0.0,
        passed_gates=passed,
        failed_gates=tuple(failed),
        components=components,
        notes=tuple(notes),
    )


__all__ = [
    "CHUNK_COVERAGE_FLOOR_VALUE",
    "CHUNK_COVERAGE_SOFT_LIMIT",
    "EXISTENCE_INDICATORS",
    "QUOTE_DUMP_GATE_CHARS",
    "WEIGHTS",
    "ProxyReward",
    "RewardComponent",
    "score_candidate",
]
