"""RAG retrieval — query text -> top-k chunks via pgvector cosine search.

Mirrors the ingest side: embeds with the SAME MiniLM-384 model that
canvas_file_ingest uses, so query and stored vectors are comparable.
Distance operator is `<=>` (cosine); score = 1 - distance (1.0 == identical).
"""

from __future__ import annotations

from dataclasses import dataclass

from auth import _db_connect

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TOP_K = 5

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


def retrieve(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    country_code: str | None = None,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """Embed *query* and return the top_k most similar chunks.

    Optionally filter by country_code and drop hits below min_score.
    """
    if not query or not query.strip():
        return []

    from sklearn.preprocessing import normalize
    vec = normalize(_get_model().encode([query]))[0]
    qvec = _to_pgvector(vec)

    where = ""
    params: list = [qvec]                      # SELECT score
    if country_code:
        where = "WHERE ce.country_code = %s"
        params.append(country_code)
    params.append(qvec)                        # ORDER BY
    params.append(top_k)                       # LIMIT

    sql = f"""
        SELECT dc.id, dc.chunk_text, ce.document_id, ce.country_code,
               1 - (ce.embedding <=> %s::vector) AS score
        FROM   chunk_embeddings ce
        JOIN   document_chunks  dc ON dc.id = ce.chunk_id
        {where}
        ORDER  BY ce.embedding <=> %s::vector
        LIMIT  %s
    """

    with _db_connect() as conn:
        with conn.cursor() as cur:
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
    return [h for h in hits if h.score >= min_score]


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a prompt-ready context block."""
    if not chunks:
        return ""
    blocks = [
        f"[Source {i + 1} · doc {c.document_id[:8]} · score {c.score:.2f}]\n{c.text}"
        for i, c in enumerate(chunks)
    ]
    return "\n\n---\n\n".join(blocks)
