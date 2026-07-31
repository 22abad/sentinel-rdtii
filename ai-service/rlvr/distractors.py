"""Deterministic distractor synthesis — a pre-flight for the proxy reward.

Best-of-N is only worth wiring if the proxy reward can tell a good candidate
from a bad one. Measuring that with a live model costs API spend and mixes two
questions (is the model diverse? is the reward discriminating?). This module
answers the reward question alone, with zero API calls, by manufacturing the
candidate types a sampled model actually produces and checking whether the
proxy ranks the real extraction above them.

Each distractor targets one reward term, so a failure names the weak component:

    fragment           -> boundary_alignment  (cut mid-sentence)
    page_dump          -> single_provision    (the classic RLVR length hack)
    paraphrase         -> citation_exactness / offsets_recover_quote gate
    heading_only       -> not_a_section_header gate
    metadata_stripped  -> metadata_complete, article_clause_specific
    neighbour_span     -> nothing. See below.

``neighbour_span`` is the honest control. It is a real, substantive, correctly
quoted provision from the same document that is simply the *wrong* provision.
No label-free reward can rule it out — telling the right provision from a
plausible neighbour is a semantic judgement, not a hygiene check. It is
included precisely so the report states the proxy's ceiling instead of hiding
it, and so the hygiene and semantic scores are never averaged into one
flattering number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Distractors that a hygiene reward SHOULD catch.
HYGIENE_KINDS = (
    "fragment",
    "page_dump",
    "paraphrase",
    "heading_only",
    "metadata_stripped",
)
# Distractors that a label-free reward CANNOT be expected to catch.
SEMANTIC_KINDS = ("neighbour_span",)

_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")
_HEADING_LINE = re.compile(r"^\s*(?:PART|Part|Division|Chapter|CHAPTER)\b.*$", re.MULTILINE)


@dataclass(frozen=True)
class SynthCandidate:
    """One candidate in a synthetic best-of-N set."""

    kind: str
    data: dict[str, Any]
    is_reference: bool = False


_METADATA_KEYS = (
    "article_clause",
    "source_legislation",
    "source_url",
    "last_update",
    "scope",
    "coverage",
)


def _base_metadata(reference: dict[str, Any]) -> dict[str, Any]:
    """Everything except the quote, shared by every candidate in a set.

    Held constant on purpose: if distractors also lost their law name and URL,
    the proxy could separate them on metadata alone and the study would
    flatter the reward.

    This MUST include the extractor's structured feature flags (`has_ban`,
    `has_conditional_flow`, ...). An earlier version copied only the six
    display fields, which starved `deterministic_eligibility` of the features
    its per-indicator branches read — so it rejected the CORRECT answer in 94%
    of sets and the whole term collapsed to a near-constant zero. Every
    candidate then scored 100% top-1 for the wrong reason.

    The consequence is a known and stated limit of the offline study: since
    distractors inherit the reference's features, only the QUOTE-driven
    eligibility checks (7.3 duration, 7.4 DPO, 7.5 elements and access gate,
    6.3 infrastructure, objectives/principles) discriminate here. Feature-
    driven branches need a live extractor to differ per candidate.
    """
    carried = {key: reference.get(key, "") for key in _METADATA_KEYS}
    carried.update(
        {
            key: value
            for key, value in reference.items()
            if key not in _METADATA_KEYS and key != "verbatim_quote"
        }
    )
    return carried


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _neighbour_span(chunk_text: str, gold_quote: str) -> str | None:
    """A different real provision from the SAME chunk, similar in length.

    Measured, not assumed: chunking does not rescue us here. In
    ``aus-my-health-records-section-77`` the prohibition in s77(1) and the
    authorising exception in s77(2) both land in one 1442-character chunk,
    well inside CHUNK_CHAR_BUDGET. The extractor genuinely sees both and may
    return either, so this remains a reachable failure the structural terms
    cannot catch.

    Picked deterministically: the non-overlapping sentence whose length is
    closest to the gold quote's, so length alone cannot separate them.
    """
    target = len(gold_quote)
    best: tuple[int, str] | None = None
    for sentence in _sentences(chunk_text):
        if len(sentence) < 60:
            continue
        if sentence in gold_quote or gold_quote in sentence:
            continue
        delta = abs(len(sentence) - target)
        if best is None or delta < best[0]:
            best = (delta, sentence)
    return best[1] if best else None


def _page_dump(chunk_text: str, gold_quote: str) -> str | None:
    """The whole chunk, quoted verbatim — the reachable form of the length hack.

    Was an arbitrary +/-1200 character window carved out of the full document,
    which the pipeline could never produce: the extractor is handed one chunk
    and cannot quote past its edges. Quoting the ENTIRE chunk is the real
    over-reach a model commits, so that is what the distractor now is.
    """
    dump = chunk_text.strip()
    if dump == gold_quote.strip() or len(dump) <= len(gold_quote):
        return None
    return dump


def _paraphrase(gold_quote: str) -> str:
    """Break literal containment while staying fuzzy-similar.

    Mirrors the real failure: the model rewrites a couple of function words and
    the quote stops being a verbatim, which the submission cannot use.
    """
    swaps = (
        ("must not", "shall not"),
        ("shall not", "must not"),
        ("personal data", "personal information"),
        ("an organisation", "a body"),
        ("the company", "the corporation"),
    )
    out = gold_quote
    for src, dst in swaps:
        if src in out:
            return out.replace(src, dst, 1)
        if src.capitalize() in out:
            return out.replace(src.capitalize(), dst.capitalize(), 1)
    # Fall back to an inserted adverb — still fuzzy-close, no longer literal.
    parts = out.split(" ", 1)
    return f"{parts[0]} hereby {parts[1]}" if len(parts) == 2 else out + " hereby"


def _heading(document_text: str) -> str | None:
    match = _HEADING_LINE.search(document_text)
    return match.group(0).strip() if match else None


def build_candidate_set(
    reference: dict[str, Any],
    *,
    chunk_text: str,
) -> list[SynthCandidate]:
    """Build one synthetic best-of-N set around a known-correct extraction.

    ``reference`` is the recorded offline fixture response — a real,
    pipeline-shaped, reviewer-backed correct answer.

    Every distractor is drawn from the CHUNK the reference lives in, not from
    the whole document. That correction matters: the pipeline hands the
    extractor one chunk at a time, so document-wide distractors described a
    choice the selector never actually faces, and the study was measuring the
    wrong distribution.
    """
    gold_quote = (reference.get("verbatim_quote") or "").strip()
    if not gold_quote:
        return []

    meta = _base_metadata(reference)
    candidates: list[SynthCandidate] = [
        SynthCandidate("reference", {**meta, "verbatim_quote": gold_quote}, True)
    ]

    fragment = gold_quote[:40].rsplit(" ", 1)[0]
    if fragment and fragment != gold_quote:
        candidates.append(
            SynthCandidate("fragment", {**meta, "verbatim_quote": fragment})
        )

    dump = _page_dump(chunk_text, gold_quote)
    if dump:
        candidates.append(SynthCandidate("page_dump", {**meta, "verbatim_quote": dump}))

    paraphrased = _paraphrase(gold_quote)
    if paraphrased != gold_quote:
        candidates.append(
            SynthCandidate("paraphrase", {**meta, "verbatim_quote": paraphrased})
        )

    heading = _heading(chunk_text)
    if heading:
        candidates.append(
            SynthCandidate("heading_only", {**meta, "verbatim_quote": heading})
        )

    candidates.append(
        SynthCandidate(
            "metadata_stripped",
            {
                **meta,
                "verbatim_quote": gold_quote,
                "article_clause": "",
                "source_url": "",
                "last_update": "",
                "scope": "unknown",
            },
        )
    )

    neighbour = _neighbour_span(chunk_text, gold_quote)
    if neighbour:
        candidates.append(
            SynthCandidate("neighbour_span", {**meta, "verbatim_quote": neighbour})
        )

    return candidates


__all__ = [
    "HYGIENE_KINDS",
    "SEMANTIC_KINDS",
    "SynthCandidate",
    "build_candidate_set",
]
