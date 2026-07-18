"""Legal-text chunker — UAX #29 sentence segmentation + token-budget merger.

Strategy:
  1. UAX #29 (uniseg) splits text into Unicode sentences — language-agnostic,
     works correctly for Thai, Vietnamese, Chinese, Arabic, etc.
  2. Sentences are merged into chunks up to CHUNK_CHAR_BUDGET characters.
  3. When a sentence looks like a structural heading (Article / Section / …),
     prefer breaking before it so headings stay at the top of their chunk.
  4. No hard chunk cap — chunk count scales with document size and budget.

Chunk.start / Chunk.end are absolute character offsets into the original
(unmodified) text — required by the anti-hallucination verifier.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from uniseg.sentencebreak import sentences as _uax29_sentences

# ~3 000 chars ≈ 750 tokens — fits comfortably in Gemini's context window
# while keeping chunks small enough for accurate verbatim-quote verification.
_BUDGET = int(os.getenv("CHUNK_CHAR_BUDGET", "3000"))
_MIN_CHARS = int(os.getenv("CHUNK_MIN_CHARS", "200"))

# Structural heading patterns — used as preferred break points, not required.
_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?i:(?:Article|Section|Clause|Part|Chapter|Schedule|Regulation|Annex|Appendix))\s+(?:\d+|[IVXLC]+\b|[A-Z]\b)"
    r"|(?i:(?:Art|Sec|Para|Cl)\.?\s*\d+)"
    r"|第\s*[\d一二三四五六七八九十百千]+\s*条"  # Chinese
    r"|มาตรา\s*\d+"                              # Thai
    r"|Pasal\s*\d+"                              # Indonesian
    r"|Điều\s*\d+"                               # Vietnamese
    r"|(?:\d+\.){1,3}\s+[A-Z]"                  # numbered: 1.2.3 Heading
    r"|\([a-z]\)\s+[A-Z]"                        # lettered: (a) Heading
    r")",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Chunk:
    """A slice of legal text with its absolute position in the source document.

    Invariant: ``original_text[start:end] == text``
    """
    text: str
    start: int
    end: int


def regex_legal_chunker(text: str) -> list[Chunk]:
    """Segment *text* into article-level chunks tracking absolute offsets.

    Uses UAX #29 sentence boundaries as atomic units, then merges sentences
    up to CHUNK_CHAR_BUDGET chars. Structural headings act as preferred
    break points so each article starts a fresh chunk where possible.
    """
    if not text or not text.strip():
        return []

    def _sentence_units(segment: str, offset: int) -> list[tuple[str, int, bool]]:
        sents = list(_uax29_sentences(segment))
        if not sents:
            return [(segment, offset, bool(_HEADING_RE.match(segment)))]

        units: list[tuple[str, int, bool]] = []
        pos = 0
        for sent in sents:
            rel = segment.find(sent, pos)
            if rel < 0:
                rel = pos
            units.append((sent, offset + rel, bool(_HEADING_RE.match(sent))))
            pos = rel + len(sent)
        return units

    units: list[tuple[str, int, bool]] = []
    heading_matches = list(_HEADING_RE.finditer(text))
    if len(heading_matches) > 1:
        starts = [m.start() for m in heading_matches]
        if text[: starts[0]].strip():
            starts.insert(0, 0)

        for idx, start in enumerate(starts):
            end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
            segment = text[start:end]
            if not segment.strip():
                continue
            if len(segment) <= _BUDGET:
                units.append((segment, start, bool(_HEADING_RE.match(segment))))
            else:
                section_units = _sentence_units(segment, start)
                if section_units:
                    first_text, first_start, _is_heading = section_units[0]
                    units.append((first_text, first_start, True))
                    units.extend(section_units[1:])
    else:
        units = _sentence_units(text, 0)

    if not units:
        stripped = text.strip()
        if not stripped:
            return []
        lead = text.index(stripped)
        return [Chunk(text=stripped, start=lead, end=lead + len(stripped))]

    chunks: list[Chunk] = []
    buf_start: int | None = None
    buf_end = 0
    buf_chars = 0

    def _flush() -> None:
        nonlocal buf_start, buf_end, buf_chars
        if buf_start is None:
            return
        raw = text[buf_start:buf_end]
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            chunks.append(Chunk(
                text=stripped,
                start=buf_start + lead,
                end=buf_start + lead + len(stripped),
            ))
        buf_start = None
        buf_end = 0
        buf_chars = 0

    for unit_text, unit_start, is_heading in units:
        unit_end = unit_start + len(unit_text)
        over_budget = (buf_chars + len(unit_text) > _BUDGET) and (buf_chars >= _MIN_CHARS)
        at_heading = is_heading and buf_start is not None and buf_chars > 0

        if buf_start is not None and (over_budget or at_heading):
            _flush()

        if buf_start is None:
            buf_start = unit_start
        buf_end = unit_end
        buf_chars += len(unit_text)

    _flush()

    return chunks or [Chunk(text=text.strip(), start=0, end=len(text))]


# ── Quote repair helper (used by extraction_repair) ───────────────────────


def snap_to_sentence_start(text: str, start: int, end: int) -> int:
    """Return the start of the UAX #29 sentence that [start, end) begins in.

    Used to complete a quote the LLM clipped mid-sentence — grow it *backward*
    to the sentence start so a material lead-in ("On request of an individual,…")
    isn't dropped. We only move the start: extending the end would just grab
    trailing punctuation and churn otherwise-good quotes.
    """
    if start <= 0 or start > len(text):
        return max(0, start)

    pos = 0
    sent_start = 0
    for sent in _uax29_sentences(text):
        s = text.find(sent, pos)
        if s < 0:
            s = pos
        e = s + len(sent)
        if s <= start < e:
            sent_start = s
            break
        pos = e

    # Trim leading whitespace of that sentence.
    lead = len(text[sent_start:start]) - len(text[sent_start:start].lstrip())
    return sent_start + lead
