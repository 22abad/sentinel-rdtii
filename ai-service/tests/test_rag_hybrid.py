"""Hybrid retrieval (rag/hybrid.py): RRF fusion, filter safety, fallback.

Hermetic — no database. The fusion formula is a pure function, and the SQL is
asserted structurally; an end-to-end ranking check needs a populated corpus and
belongs in the live-DB smoke run, not the unit suite.
"""

from __future__ import annotations

import pytest

from rag import hybrid
from rag.hybrid import RRF_K, build_sql, lexical_available, rrf


@pytest.fixture(autouse=True)
def _reset_probe():
    hybrid.reset_probe()  # the probe caches per process; keep tests independent
    yield
    hybrid.reset_probe()


# ── RRF fusion ────────────────────────────────────────────────────────────


def test_rrf_rewards_agreement_between_the_arms():
    # 'agreed' is only 2nd on the dense arm but both arms like it; 'dense_top'
    # is 1st there and absent from the lexical arm. Two arms beat one.
    fused = rrf(["dense_top", "agreed"], ["agreed"])
    assert fused["agreed"] > fused["dense_top"]


def test_rrf_barely_separates_adjacent_top_ranks():
    # Documents a property that is easy to assume away: with k=60 the head of
    # each arm is damped hard, so "1st + 3rd" edges out "2nd + 2nd" by ~0.03%.
    # RRF is deliberately not a fine-grained ranker at the top — it is a
    # tie-breaker that stops either arm from dominating. Anything needing
    # finer separation there is a reranker's job, not RRF's.
    one_and_three = rrf(["x", "_", "_"], ["_", "_", "x"])["x"]
    two_and_two = rrf(["_", "y", "_"], ["_", "y", "_"])["y"]
    assert one_and_three == pytest.approx(two_and_two, rel=1e-3)


def test_rrf_uses_ranks_not_scores():
    # Only position matters, so an arm's absolute score scale is irrelevant —
    # that is the property that lets cosine (~0-1) fuse with ts_rank_cd.
    assert rrf(["x"], []) == {"x": 1.0 / (RRF_K + 1)}


def test_rrf_keeps_single_arm_hits():
    # A lexical-only hit (an exact "s46" match the embedding missed) must still
    # surface — that is the entire reason for the lexical arm.
    fused = rrf(["a"], ["z"])
    assert set(fused) == {"a", "z"}
    assert fused["a"] == fused["z"]  # both rank 1 in their own arm


def test_rrf_ranks_a_lexical_only_hit_above_a_deep_dense_hit():
    dense = [f"d{i}" for i in range(20)]
    fused = rrf(dense, ["exact"])
    assert fused["exact"] > fused["d19"]


# ── SQL construction ──────────────────────────────────────────────────────


def test_build_sql_applies_the_filter_to_both_arms():
    # A country/document filter that reached only the dense arm would let the
    # lexical arm leak rows from outside the requested scope.
    sql = build_sql("ce.country_code = %(country_code)s")
    assert sql.count("ce.country_code = %(country_code)s") == 2
    dense_part, lex_part = sql.split("lex AS (")
    assert "%(country_code)s" in dense_part
    assert "%(country_code)s" in lex_part


def test_build_sql_without_filters_has_no_dangling_where():
    sql = build_sql("")
    assert "WHERE  dc.chunk_tsv @@ q.query" in sql
    assert "WHERE AND" not in sql and "AND  ORDER" not in sql


def test_build_sql_reports_cosine_as_score_for_both_arms():
    # Lexical-only hits are joined back to their embedding, so `score` keeps
    # meaning cosine similarity everywhere (min_score / the UI depend on it).
    sql = build_sql("")
    assert "COALESCE(d.cos, l.cos) AS score" in sql
    assert sql.count("1 - (ce.embedding <=> %(qvec)s::vector) AS cos") == 2


def test_build_sql_full_outer_join_keeps_hits_unique_to_one_arm():
    assert "FULL   OUTER JOIN lex l ON l.id = d.id" in build_sql("")


def test_build_sql_uses_simple_text_search_config():
    # 'english' would stem and drop stopwords across an 8-language corpus, and
    # would mangle the statutory tokens the lexical arm exists to catch.
    sql = build_sql("")
    assert "plainto_tsquery('simple', %(qtext)s)" in sql
    assert "'english'" not in sql


# ── Fallback probe ────────────────────────────────────────────────────────


class _Cur:
    """Minimal cursor stand-in: records queries, returns a scripted row."""

    def __init__(self, row=None, raises=False):
        self._row, self._raises, self.queries = row, raises, []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        if self._raises:
            raise RuntimeError("information_schema unavailable")

    def fetchone(self):
        return self._row


def test_lexical_available_true_when_the_column_exists():
    assert lexical_available(_Cur(row=(1,))) is True


def test_lexical_available_false_on_a_pre_migration_database():
    # No chunk_tsv column -> dense-only, not an error.
    assert lexical_available(_Cur(row=None)) is False


def test_lexical_available_fails_closed_on_a_probe_error():
    assert lexical_available(_Cur(raises=True)) is False


def test_lexical_available_probes_once_per_process():
    cur = _Cur(row=(1,))
    lexical_available(cur)
    lexical_available(cur)
    assert len(cur.queries) == 1
