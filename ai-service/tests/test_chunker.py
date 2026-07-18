"""Tests for the legal-text chunker.

The chunker's offset contract is load-bearing for the audit-view highlight:
for every Chunk, `original_text[chunk.start:chunk.end] == chunk.text` must
hold character-for-character. (Indices are Python str positions, i.e.
Unicode code points, not UTF-8 bytes — important for ZH / non-ASCII text
where one character may span multiple bytes.)
"""

from __future__ import annotations

from chunker import Chunk, regex_legal_chunker


def test_empty_input_returns_empty():
    assert regex_legal_chunker("") == []
    assert regex_legal_chunker("   \n\n   ") == []


def test_single_article_offsets_round_trip():
    text = "Some preamble.\n\nArticle 1. Data must be protected. End."
    chunks = regex_legal_chunker(text)
    assert chunks, "expected at least one chunk"
    for c in chunks:
        # The headline contract: offsets must address the chunk text exactly.
        assert text[c.start : c.end] == c.text, (
            f"offsets {c.start}..{c.end} don't match {c.text!r}"
        )


def test_multiple_articles_offsets_distinct_and_correct():
    text = (
        "Article 1. Personal data shall not be transferred abroad.\n\n"
        "Article 2. Companies shall maintain a domestic data centre.\n\n"
        "Article 3. Operators shall appoint a data protection officer."
    )
    chunks = regex_legal_chunker(text)
    assert len(chunks) == 3, f"expected 3 chunks, got {len(chunks)}"

    # Offsets must round-trip and be strictly increasing (non-overlapping).
    last_end = -1
    for c in chunks:
        assert text[c.start : c.end] == c.text
        assert c.start >= last_end, "chunks should be non-overlapping & ordered"
        last_end = c.end


def test_no_heading_falls_back_to_whole_document():
    text = "  This document has no Article header at all.  "
    chunks = regex_legal_chunker(text)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.text == text.strip()
    assert text[c.start : c.end] == c.text


def test_chinese_article_marker_is_chunked():
    """Real chunking, not the whole-doc fallback. Asserts each `第X条`
    becomes its own chunk so the test would fail if the regex regressed
    to the no-heading fallback."""
    text = (
        "第一条 个人信息处理者向境外提供个人信息的，应当符合下列条件之一。\n\n"
        "第二条 处理敏感个人信息应当具有特定的目的。"
    )
    chunks = regex_legal_chunker(text)
    assert len(chunks) == 2, (
        f"expected ZH headings to split into 2 chunks, got {len(chunks)} "
        "(chunker may have regressed to whole-document fallback)"
    )
    assert chunks[0].text.startswith("第一条"), (
        f"chunk 0 doesn't start with 第一条: {chunks[0].text[:30]!r}"
    )
    assert chunks[1].text.startswith("第二条"), (
        f"chunk 1 doesn't start with 第二条: {chunks[1].text[:30]!r}"
    )
    # And the offset contract must still hold for both.
    for c in chunks:
        assert text[c.start : c.end] == c.text


def test_returns_chunk_dataclass():
    text = "Article 1. Hello."
    chunks = regex_legal_chunker(text)
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(hasattr(c, "text") and hasattr(c, "start") and hasattr(c, "end") for c in chunks)


def test_leading_whitespace_does_not_break_offsets():
    """Pattern captures whitespace-prefixed matches; the chunker should
    strip and adjust offsets so the contract still holds."""
    text = "\n\n\n   Article 1. Hello world.\n\nArticle 2. Goodbye world."
    chunks = regex_legal_chunker(text)
    for c in chunks:
        assert text[c.start : c.end] == c.text
        assert not c.text.startswith(" ")
        assert not c.text.startswith("\n")


def test_wrapped_prose_does_not_match_section_prefix_as_heading():
    text = (
        "Article 1. Personal data shall not be transferred abroad.\n"
        "Section headings in this explanatory paragraph are not new legal sections.\n"
        "Section covers both domestic and overseas processors in this paragraph.\n"
        "Part includes examples and implementation notes, not a new legal part.\n"
        "Article 2. Operators shall appoint a data protection officer."
    )
    chunks = regex_legal_chunker(text)
    assert len(chunks) == 2
    assert "Section headings" in chunks[0].text
    assert "Section covers" in chunks[0].text
    assert "Part includes" in chunks[0].text
    for c in chunks:
        assert text[c.start : c.end] == c.text


def test_uppercase_roman_and_letter_headings_still_split():
    text = (
        "Article I. Personal data shall not be transferred abroad.\n\n"
        "Section A. Operators shall appoint a data protection officer."
    )
    chunks = regex_legal_chunker(text)
    assert len(chunks) == 2
    assert chunks[0].text.startswith("Article I")
    assert chunks[1].text.startswith("Section A")
    for c in chunks:
        assert text[c.start : c.end] == c.text


def test_long_article_still_respects_budget_after_heading_split(monkeypatch):
    import chunker as chunker_module

    monkeypatch.setattr(chunker_module, "_BUDGET", 80)
    monkeypatch.setattr(chunker_module, "_MIN_CHARS", 20)
    text = (
        "Article 1. "
        "Personal data shall not be transferred abroad. "
        "Controllers shall store audit records securely. "
        "Operators shall appoint a data protection officer.\n\n"
        "Article 2. Companies shall maintain a domestic data centre."
    )
    chunks = regex_legal_chunker(text)
    assert len(chunks) >= 3
    assert chunks[-1].text.startswith("Article 2")
    for c in chunks:
        assert text[c.start : c.end] == c.text


# ── reflow_legal_text ─────────────────────────────────────────────────────

from chunker import reflow_legal_text  # noqa: E402


def test_reflow_joins_wrapped_lines_and_dehyphenates():
    messy = (
        "No prosecution for an offence under this Act shall be\n"
        "instituted except by or with the authorisation of the Public Pros-\n"
        "ecutor."
    )
    out = reflow_legal_text(messy)
    assert "shall be instituted" in out
    assert "Public Prosecutor." in out
    assert "\n" not in out  # one flowing sentence now


def test_reflow_preserves_inline_amendment_markers():
    # Amendment markers are part of the official consolidated source text (SSO,
    # legislation.gov.au). Reflow must PRESERVE them so the extracted verbatim
    # still matches the source that judges verify against — stripping them would
    # break verbatim-vs-source integrity.
    assert reflow_legal_text("text [40/2020] more") == "text [40/2020] more"
    assert reflow_legal_text("x [Act 26 of 2012] y") == "x [Act 26 of 2012] y"


def test_reflow_preserves_headings_and_paragraph_breaks():
    clean = "Section 25. Retention of personal data\n\nAn organisation must cease to retain."
    # next line starts uppercase / after a blank line -> not joined
    assert reflow_legal_text(clean) == clean


def test_reflow_is_idempotent():
    messy = "shall be\ninstituted with the Pros-\necutor [40/2020]."
    once = reflow_legal_text(messy)
    assert reflow_legal_text(once) == once


def test_reflow_noop_on_clean_text():
    for clean in [
        "The company shall retain the records for seven years.",
        "Section 77  Requirement not to hold records outside Australia",  # double space kept
        "第十条 关键信息基础设施运营者严禁向境外提供受管制数据。",  # CJK untouched
    ]:
        assert reflow_legal_text(clean) == clean
