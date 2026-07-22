"""Table processing (rag/tables.py): a ruled schedule must survive as a grid.

PyMuPDF's flat text layer flattens a table cell-by-cell, breaking the
header->cell link that indicators like 7.3 (a minimum retention period) depend
on. `extract_pdf_tables` reconstructs the grid to Markdown, `append_tables`
feeds it to the chunker/embedder via ingest, and `looks_like_table` keeps the
result from being demoted as low-substance at retrieval time.
"""

from __future__ import annotations

import fitz  # pymupdf

from rag.tables import append_tables, extract_pdf_tables, looks_like_table
from services.canvas_file_ingest import _extract_text


def _make_retention_table_pdf(path: str) -> None:
    """A 3x2 ruled table (header + two rows) that find_tables() can detect."""
    doc = fitz.open()
    page = doc.new_page()
    xs = (100.0, 260.0, 420.0)
    ys = (100.0, 132.0, 164.0, 196.0)
    for x in xs:  # vertical rules
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:  # horizontal rules
        page.draw_line((xs[0], y), (xs[-1], y))
    rows = [
        ("Record type", "Minimum retention"),
        ("Tax records", "7 years"),
        ("Employee records", "3 years"),
    ]
    for r, (a, b) in enumerate(rows):
        page.insert_text((xs[0] + 5, ys[r] + 21), a, fontsize=10)
        page.insert_text((xs[1] + 5, ys[r] + 21), b, fontsize=10)
    doc.save(path)
    doc.close()


def test_extract_pdf_tables_reconstructs_the_grid(tmp_path):
    pdf = tmp_path / "retention.pdf"
    _make_retention_table_pdf(str(pdf))

    md = extract_pdf_tables(str(pdf))

    # The header->cell link is preserved (all on one Markdown row).
    assert "Minimum retention" in md
    assert "7 years" in md
    assert "3 years" in md
    assert "Tax records" in md
    assert "|" in md  # Markdown table pipes → it is a real grid, not a jumble


def test_append_tables_marks_the_block_and_keeps_the_prose(tmp_path):
    pdf = tmp_path / "retention.pdf"
    _make_retention_table_pdf(str(pdf))

    out = append_tables("body text", str(pdf))

    assert out.startswith("body text")
    assert "=== Table (page 1) ===" in out
    assert "7 years" in out


def test_ingest_extract_text_appends_the_table(tmp_path):
    pdf = tmp_path / "retention.pdf"
    _make_retention_table_pdf(str(pdf))

    text = _extract_text(str(pdf), "retention.pdf")

    assert "=== Table (page 1) ===" in text
    assert "7 years" in text


def test_extract_pdf_tables_fails_open(tmp_path):
    # Missing / non-PDF input must yield no tables, never raise.
    assert extract_pdf_tables(str(tmp_path / "does-not-exist.pdf")) == ""
    junk = tmp_path / "not-a.pdf"
    junk.write_bytes(b"this is not a pdf")
    assert extract_pdf_tables(str(junk)) == ""
    assert append_tables("body text", str(junk)) == "body text"


def test_looks_like_table_recognises_schedules_not_prose():
    # The ingest marker, even if the chunker split off the rows.
    assert looks_like_table("=== Table (page 4) ===\nsomething")
    # Bare Markdown rows (header + data) with no marker.
    assert looks_like_table(
        "| Record type | Minimum retention |\n|---|---|\n| Tax records | 7 years |"
    )
    # Prose — including a single stray pipe — is not a table.
    assert not looks_like_table("A data controller shall retain records | as needed.")
    assert not looks_like_table("Part 3 Ransomware reporting obligations")
