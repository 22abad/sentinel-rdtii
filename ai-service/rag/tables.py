"""Table processing for the RAG corpus — a ruled schedule must survive as a grid.

PyMuPDF's flat text layer reads a table cell-by-cell, so a retention / penalty /
tariff schedule collapses into an unlabelled number jumble and the header->cell
link is lost — exactly the provisions (e.g. indicator 7.3, a minimum retention
period) where the cell value carries the score. ``find_tables()`` reconstructs
the grid and ``to_markdown()`` keeps header->cell intact.

Both halves of the RAG path use this module: ingest calls `append_tables` so the
chunker/embedder sees a real table, and retrieval calls `looks_like_table` so a
schedule chunk — which has no operative "shall"/"must" — is not demoted as
low-substance behind prose.
"""

from __future__ import annotations

from pathlib import Path

# Marks a reconstructed table in the extracted text. Doubles as the retrieval
# side's strongest table signal, so keep the two in sync.
TABLE_MARKER = "=== Table (page {page}) ==="
_TABLE_MARKER_PREFIX = "=== Table (page "


def extract_pdf_tables(file_path: str | Path) -> str:
    """Detect tables in a PDF and serialise each to Markdown.

    Best-effort and fail-open: any problem (an old PyMuPDF without
    ``find_tables``, an encrypted/corrupt file, one bad table) yields fewer or
    zero tables rather than breaking ingest.
    """
    try:
        import fitz  # pymupdf
    except Exception:
        return ""
    try:
        doc = fitz.open(str(file_path))
    except Exception:
        return ""
    blocks: list[str] = []
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            finder = getattr(page, "find_tables", None)
            if finder is None:
                continue
            try:
                found = finder()
            except Exception:
                continue
            for table in getattr(found, "tables", []) or []:
                try:
                    md = table.to_markdown().strip()
                except Exception:
                    continue
                if md:
                    blocks.append(f"{TABLE_MARKER.format(page=page_index + 1)}\n{md}")
    finally:
        doc.close()
    return "\n\n".join(blocks)


def append_tables(text: str, file_path: str | Path) -> str:
    """Append *file_path*'s reconstructed tables to *text*. No-op when none."""
    tables = extract_pdf_tables(file_path)
    return f"{text}\n\n{tables}" if tables else text


def looks_like_table(text: str) -> bool:
    """True when a chunk is (or contains) a reconstructed Markdown table.

    Either the ingest marker survived the chunker, or the chunk carries two or
    more pipe-delimited rows — a header plus at least one data row.
    """
    if _TABLE_MARKER_PREFIX in text:
        return True
    rows = 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|") and line.count("|") >= 3:
            rows += 1
            if rows >= 2:
                return True
    return False
