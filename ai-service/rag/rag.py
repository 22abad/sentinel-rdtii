"""RAG retrieval — query text -> top-k chunks via pgvector cosine search.

Mirrors the ingest side: embeds with the SAME MiniLM-384 model that
canvas_file_ingest uses, so query and stored vectors are comparable.
Distance operator is `<=>` (cosine); score = 1 - distance (1.0 == identical).
"""

from __future__ import annotations

import re

from dataclasses import dataclass

from auth import _db_connect

from rag.hybrid import RRF_K, build_sql, lexical_available
from rag.tables import looks_like_table

# Multilingual: the corpus spans 10 economies in 8 languages; the English
# MiniLM embedded RU/TH/ZH text as near-noise (Russian query -> junk hits).
# Same 384 dims, so the pgvector column is untouched.
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_TOP_K = 5

_TOC_HEADING_LINE = re.compile(r"^\s*(?:\d{1,3}[A-Z]{0,2}\.?\s+\S|Part\b|Division\b|Subdivision\b|Schedule\b|ARRANGEMENT OF)", re.IGNORECASE)
_TOC_OPERATIVE = re.compile(r"\b(shall|must|may not|is liable|commits an offence|应当|不得|必须)\b", re.IGNORECASE)


def _looks_like_toc(text: str) -> bool:
    """A table-of-contents chunk: mostly bare numbered-heading lines, no
    operative language. These repeat every section title verbatim and
    out-rank real provisions for statutory phrasings."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 6:
        return False
    heading_like = sum(1 for line in lines if _TOC_HEADING_LINE.match(line))
    if heading_like / len(lines) < 0.6:
        return False
    return not _TOC_OPERATIVE.search(text)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _to_pgvector(vec) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    document_id: str
    country_code: str | None
    score: float  # cosine similarity in ~[0, 1], higher = closer


def _normalize_country(country_code: str | None) -> str | None:
    """Accept display names ("China") and ISO codes ("CHN") alike.

    The Workbench canvas passes the Source node's display name; documents
    store ISO-3. An exact-match filter on 'China' silently returned zero
    rows and the chat claimed no sources exist.
    """
    if not country_code:
        return None
    try:
        from submission.schema import economy_code
        return economy_code(country_code)
    except Exception:
        return country_code.strip().upper() or None


def retrieve(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    country_code: str | None = None,
    document_ids: list[str] | None = None,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """Retrieve the top_k chunks most relevant to *query*.

    Hybrid: a dense (embedding cosine) arm and a lexical (full-text) arm are
    fused by RRF — see rag/hybrid.py for why, and for the dense-only fallback
    on databases predating the migration. `score` remains cosine similarity in
    both cases.

    Optionally filter by country_code (display name or ISO-3, normalised)
    and/or restrict to specific documents (session-scoped retrieval);
    drop hits below min_score.
    """
    if not query or not query.strip():
        return []

    country_code = _normalize_country(country_code)  # display name or ISO-3 -> ISO-3

    from sklearn.preprocessing import normalize
    vec = normalize(_get_model().encode([query]))[0]
    qvec = _to_pgvector(vec)

    conditions: list[str] = []
    params: dict = {"qvec": qvec, "qtext": query, "rrf_k": RRF_K}
    if country_code:
        conditions.append("ce.country_code = %(country_code)s")
        params["country_code"] = country_code
    if document_ids:
        conditions.append("ce.document_id = ANY(%(document_ids)s::uuid[])")
        params["document_ids"] = document_ids
    where = " AND ".join(conditions)
    # Over-fetch so the ToC penalty below still has substantive chunks to
    # promote into the final top_k.
    params["candidates"] = max(top_k, min(top_k * 4, 40))

    dense_only_sql = f"""
        SELECT dc.id, dc.chunk_text, ce.document_id, ce.country_code,
               1 - (ce.embedding <=> %(qvec)s::vector) AS score
        FROM   chunk_embeddings ce
        JOIN   document_chunks  dc ON dc.id = ce.chunk_id
        {f"WHERE {where}" if where else ""}
        ORDER  BY ce.embedding <=> %(qvec)s::vector
        LIMIT  %(candidates)s
    """

    with _db_connect() as conn:
        with conn.cursor() as cur:
            # Hybrid when the full-text column exists, dense-only otherwise —
            # a database predating the migration must still answer queries.
            sql = build_sql(where) if lexical_available(cur) else dense_only_sql
            cur.execute(sql, params)
            rows = cur.fetchall()

    hits = [
        RetrievedChunk(
            chunk_id=str(r[0]),
            text=r[1],
            document_id=str(r[2]),
            country_code=r[3],
            score=float(r[4]),
        )
        for r in rows
    ]
    # Heading noise out-ranks substance for almost any statutory phrasing:
    # running page headers become tiny duplicate chunks ("Part 3 Ransomware
    # reporting obligations …" ×6, one per page) and ToC chunks repeat every
    # section title verbatim — the chat then honestly answers "only headings
    # were retrieved". Post-rank: dedupe identical texts, then demote
    # low-substance chunks (short + no operative language, or ToC-shaped)
    # behind the real provisions.
    seen: set[str] = set()
    deduped: list[RetrievedChunk] = []
    for h in hits:
        if h.score < min_score:
            continue
        key = " ".join(h.text.split()).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)

    def _low_substance(text: str) -> bool:
        if _looks_like_toc(text):
            return True
        # A reconstructed schedule (see rag/tables.py) is pure substance — the
        # cell value IS the provision (7.3's "7 years") — but it is short and
        # has no operative verb, so the plain heuristic would bury it as filler.
        if looks_like_table(text):
            return False
        return len(text.strip()) < 200 and not _TOC_OPERATIVE.search(text)

    substantive = [h for h in deduped if not _low_substance(h.text)]
    filler = [h for h in deduped if _low_substance(h.text)]
    return (substantive + filler)[:top_k]


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a prompt-ready context block."""
    if not chunks:
        return ""
    blocks = [
        f"[Source {i + 1} · doc {c.document_id[:8]} · score {c.score:.2f}]\n{c.text}"
        for i, c in enumerate(chunks)
    ]
    return "\n\n---\n\n".join(blocks)
