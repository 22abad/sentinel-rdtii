"""Indicator-targeted sparse retrieval (BM25) for long statutes.

A 200-page statute can't be fed to the LLM whole, and a blind prefix cut buries
the operative clause hundreds of kB in (the India P7 rows all missed this way).
This retrieves the article/section slices most relevant to the target
indicators — ranked by BM25 over the query terms for those indicators — and
returns them in document order up to a character budget.

Two retrieval paths in the project: the web workbench uses dense MiniLM/pgvector
similarity (`rag/rag.py`); this is the dependency-free BM25 path the lean CLI
and the offline evaluator share, so neither blind-truncates a large document.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter

# Optional dense-retrieval backbone. model2vec = static (distilled) multilingual
# embeddings: pure-numpy inference, NO torch, ~30-100MB — light enough for the
# key-free CLI. Unlike the old paraphrase-MiniLM (which embedded RU/TH/ZH as
# near-noise), a modern multilingual static model gives real cross-lingual
# signal (measured: RU relevant-vs-irrelevant cosine gap ~0.38). Used only when
# RDTII_RETRIEVAL=hybrid AND the package+model are present; otherwise pure BM25.
_DENSE_MODEL = None
_DENSE_TRIED = False
_DENSE_MODEL_NAME = os.getenv(
    "RDTII_DENSE_MODEL", "minishlab/M2V_multilingual_output"
)


def _dense_model():
    global _DENSE_MODEL, _DENSE_TRIED
    if _DENSE_TRIED:
        return _DENSE_MODEL
    _DENSE_TRIED = True
    try:
        from model2vec import StaticModel

        _DENSE_MODEL = StaticModel.from_pretrained(_DENSE_MODEL_NAME)
    except Exception:  # noqa: BLE001 — dense is optional; fall back to BM25
        _DENSE_MODEL = None
    return _DENSE_MODEL


def _dense_ranks(query_text: str, chunks: list[str]) -> list[tuple[float, int]] | None:
    """Cosine of the query against each chunk with the static embedder, best
    first. Returns None when dense retrieval is off/unavailable."""
    if os.getenv("RDTII_RETRIEVAL", "bm25").lower() != "hybrid":
        return None
    model = _dense_model()
    if model is None:
        return None
    try:
        import numpy as np

        vecs = model.encode([query_text] + chunks)
        q = vecs[0]
        mat = vecs[1:]
        qn = q / (np.linalg.norm(q) + 1e-9)
        mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        sims = mn @ qn
        order = sorted(range(len(chunks)), key=lambda i: -float(sims[i]))
        return [(float(sims[i]), i) for i in order]
    except Exception:  # noqa: BLE001
        return None


# Word runs in any script (Latin, Cyrillic, Thai, Arabic, …) plus number runs.
_WORD = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)
# CJK has no word boundaries — index it as character bigrams (standard for CJK
# information retrieval), so a Chinese query term matches a Chinese statute.
_CJK_RUN = re.compile(r"[㐀-鿿]+")


def _tokenize(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens = _WORD.findall(lowered)
    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _indicator_query_terms(indicators: list[str], country_code: str | None) -> list[str]:
    """Tokenized query terms for the target indicators — English (methodology-
    derived + curated) plus the economy's local-language terms, reused from the
    discovery query builder. Local terms are what let BM25 rank a Chinese /
    Russian / Indonesian statute; without them the ASCII query matches nothing
    and retrieval degrades to a blind prefix."""
    try:
        from discovery.query_builder import ALL_QUERY_TERMS, LOCAL_TERMS
    except Exception:  # noqa: BLE001
        ALL_QUERY_TERMS, LOCAL_TERMS = {}, {}
    local = LOCAL_TERMS.get((country_code or "").upper(), {})
    terms: list[str] = []
    for iid in indicators or []:
        terms.extend(ALL_QUERY_TERMS.get(iid, []))
        terms.extend(local.get(iid, []))
    return _tokenize(" ".join(terms))


def _indicator_query_phrases(indicator: str, country_code: str | None) -> list[str]:
    """Raw (un-tokenized) query phrases for one indicator — English + local — for
    dense encoding, which wants natural language, not BM25 tokens."""
    try:
        from discovery.query_builder import ALL_QUERY_TERMS, LOCAL_TERMS
    except Exception:  # noqa: BLE001
        ALL_QUERY_TERMS, LOCAL_TERMS = {}, {}
    local = LOCAL_TERMS.get((country_code or "").upper(), {})
    return list(ALL_QUERY_TERMS.get(indicator, [])) + list(local.get(indicator, []))


def select_relevant_text(
    text: str, indicators: list[str], max_chars: int, country_code: str | None = None
) -> str:
    """Return the indicator-relevant portion of ``text`` within ``max_chars``.

    No-op when the text already fits. Falls back to the prefix when the document
    has no chunk structure or nothing scores against the query. Pass
    ``country_code`` so a non-English statute is ranked with its local-language
    query terms (otherwise the ASCII query matches nothing on it).
    """
    if not text or len(text) <= max_chars:
        return text

    try:
        from chunker import regex_legal_chunker

        chunks = [c.text for c in regex_legal_chunker(text) if c.text.strip()]
    except Exception:  # noqa: BLE001
        chunks = []
    inds = [i for i in (indicators or []) if _indicator_query_terms([i], country_code)]
    if not chunks or not inds:
        return text[:max_chars]

    docs = [_tokenize(c) for c in chunks]
    n = len(docs)
    avgdl = max(1.0, sum(len(d) for d in docs) / n)
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in df}
    k1, b = 1.5, 0.75
    tfs = [Counter(d) for d in docs]

    def _rank(query: list[str]) -> list[tuple[float, int]]:
        scored: list[tuple[float, int]] = []
        for i, tf in enumerate(tfs):
            dl = len(docs[i])
            s = 0.0
            for t in query:
                f = tf.get(t)
                if f:
                    s += idf.get(t, 0.0) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
            if s > 0:
                scored.append((s, i))
        return sorted(scored, key=lambda x: (-x[0], x[1]))

    # Per-indicator budget allocation. Ranking every target indicator with ONE
    # merged query lets a term-dense indicator crowd another out of the budget:
    # on the 329K Indonesian PDP Law, 6.3 (data-centre) chunks pushed the 6.4
    # (cross-border consent) clause past a 60K cut, so 6.4 scored 0.0. Giving
    # each indicator its own share of the budget guarantees every target's
    # operative clause is present, then we union and restore document order.
    def _fuse(bm25: list[tuple[float, int]], iid: str) -> list[int]:
        """Order chunks for one indicator. Pure BM25 by default; when hybrid
        retrieval is on, fuse the BM25 ranking with a dense (static-embedding)
        ranking via Reciprocal Rank Fusion so a semantically-relevant clause that
        uses different wording than the query terms still surfaces — without the
        dense signal ever overriding a strong lexical match."""
        dense = _dense_ranks(" ".join(_indicator_query_phrases(iid, country_code)), chunks)
        if not dense:
            return [i for _s, i in bm25]
        kk = 60.0
        rrf: dict[int, float] = {}
        for rank, (_s, i) in enumerate(bm25):
            rrf[i] = rrf.get(i, 0.0) + 1.0 / (kk + rank)
        for rank, (_s, i) in enumerate(dense):
            rrf[i] = rrf.get(i, 0.0) + 1.0 / (kk + rank)
        return sorted(rrf, key=lambda i: -rrf[i])

    per_ind = max(1, max_chars // len(inds))
    picked: set[int] = set()
    total = 0
    for iid in inds:
        order = _fuse(_rank(_indicator_query_terms([iid], country_code)), iid)
        budget = per_ind
        for i in order:
            if budget <= 0 or total >= max_chars:
                break
            if i not in picked:
                picked.add(i)
                cost = len(chunks[i]) + 2
                budget -= cost
                total += cost
    if not picked:
        return text[:max_chars]
    return "\n\n".join(chunks[i] for i in sorted(picked))[:max_chars]


__all__ = ["select_relevant_text"]
