"""Hybrid retrieval — dense cosine fused with lexical full-text, via RRF.

Dense embeddings are weakest exactly where legal retrieval is most demanding:
a statutory identifier ("s46", "Act 854", "section 125") is a near-arbitrary
token, and MiniLM maps every such reference into the same fuzzy neighbourhood.
Lexical search nails those and is hopeless at paraphrase ("can data leave the
country?" vs "transfer of personal data outside Malaysia"); dense search is the
reverse. Running both and fusing keeps each one's strength.

Fusion is Reciprocal Rank Fusion — score = sum over arms of 1/(k + rank). RRF
consumes only RANKS, never raw scores, so a cosine similarity (~0-1, tightly
bunched) and a ts_rank_cd value (unbounded, corpus-dependent) combine without
inventing a normalisation constant that would need retuning per corpus.

Text search config is 'simple' deliberately: the corpus spans 10 economies in 8
languages, and 'english' would stem and drop stopwords in ways that damage the
others. 'simple' also leaves statutory tokens ("s46", "854") untouched, which
is the whole point of the lexical arm. Caveat: 'simple' splits on whitespace and
punctuation, so unsegmented scripts (ZH/TH/JA) contribute little to this arm —
those queries fall back to dense behaviour, which is what they had before.
"""

from __future__ import annotations

# RRF's smoothing constant. 60 is the value from the original paper (Cormack et
# al. 2009) and the de-facto default; it damps the top ranks so a single arm's
# #1 hit cannot dominate a document both arms rank respectably.
RRF_K = 60

# Set once per process by `lexical_available`. None = not yet probed.
_lexical_ok: bool | None = None


def lexical_available(cur) -> bool:
    """Whether document_chunks carries the `chunk_tsv` full-text column.

    A database created before the hybrid-search migration has no such column;
    retrieval must degrade to dense-only rather than error. Judges run this
    tool against a fresh `docker compose up` (init.sql has the column) but a
    long-lived dev volume will not, so both must work. Probed once per process.
    """
    global _lexical_ok
    if _lexical_ok is None:
        try:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'document_chunks' AND column_name = 'chunk_tsv'"
            )
            _lexical_ok = cur.fetchone() is not None
        except Exception:  # noqa: BLE001 — never break retrieval on a probe
            _lexical_ok = False
    return _lexical_ok


def reset_probe() -> None:
    """Forget the cached probe (tests, or after applying the migration)."""
    global _lexical_ok
    _lexical_ok = None


def rrf(dense_ids: list, lexical_ids: list, *, k: int = RRF_K) -> dict:
    """Reciprocal Rank Fusion over two ranked id lists -> {id: fused score}.

    Ranks are 1-based and per-arm; an id missing from an arm simply contributes
    nothing from it. Kept pure so the fusion is testable without a database —
    the SQL path below computes the identical formula server-side.
    """
    fused: dict = {}
    for ids in (dense_ids, lexical_ids):
        for rank, chunk_id in enumerate(ids, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return fused


def build_sql(where: str) -> str:
    """Hybrid SQL: dense arm ∪ lexical arm, fused by RRF, ordered by fusion.

    *where* is the shared filter (country / document scope) already rendered
    with named placeholders, applied to BOTH arms so a filtered search cannot
    leak rows in through the lexical side.

    `score` stays the cosine similarity for every row — including lexical-only
    hits, which are joined back to their embedding — so the value the UI shows
    and `min_score` filters on keeps its meaning across the change.
    """
    and_where = f"AND {where}" if where else ""
    where_clause = f"WHERE {where}" if where else ""
    return f"""
        WITH dense AS (
            SELECT ce.chunk_id AS id,
                   1 - (ce.embedding <=> %(qvec)s::vector) AS cos,
                   ROW_NUMBER() OVER (ORDER BY ce.embedding <=> %(qvec)s::vector) AS rnk
            FROM   chunk_embeddings ce
            {where_clause}
            ORDER  BY ce.embedding <=> %(qvec)s::vector
            LIMIT  %(candidates)s
        ),
        lex AS (
            SELECT ce.chunk_id AS id,
                   1 - (ce.embedding <=> %(qvec)s::vector) AS cos,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(dc.chunk_tsv, q.query) DESC
                   ) AS rnk
            FROM   chunk_embeddings ce
            JOIN   document_chunks  dc ON dc.id = ce.chunk_id
            CROSS  JOIN plainto_tsquery('simple', %(qtext)s) AS q(query)
            WHERE  dc.chunk_tsv @@ q.query {and_where}
            ORDER  BY ts_rank_cd(dc.chunk_tsv, q.query) DESC
            LIMIT  %(candidates)s
        )
        SELECT dc.id, dc.chunk_text, ce.document_id, ce.country_code,
               COALESCE(d.cos, l.cos) AS score,
               COALESCE(1.0 / (%(rrf_k)s + d.rnk), 0)
             + COALESCE(1.0 / (%(rrf_k)s + l.rnk), 0) AS fused
        FROM   dense d
        FULL   OUTER JOIN lex l ON l.id = d.id
        JOIN   document_chunks  dc ON dc.id = COALESCE(d.id, l.id)
        JOIN   chunk_embeddings ce ON ce.chunk_id = dc.id
        ORDER  BY fused DESC
        LIMIT  %(candidates)s
    """
