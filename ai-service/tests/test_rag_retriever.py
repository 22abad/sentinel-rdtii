"""Tests for the indicator-targeted BM25 retriever."""
from rag.retriever import select_relevant_text


def _doc(n_sections: int, needle_at: int) -> str:
    secs = []
    for i in range(1, n_sections + 1):
        body = "General administrative provisions and definitions apply here. " * 40
        if i == needle_at:
            body = ("Every operator shall retain records for a minimum period of "
                    "not less than five years. " * 30)
        secs.append(f"Section {i}. {body}")
    return "\n\n".join(secs)


def test_short_text_is_returned_whole():
    assert select_relevant_text("short text", ["7.3"], 10_000) == "short text"


def test_retrieves_the_buried_retention_clause():
    # The retention clause is in the LAST section, far past a prefix cut.
    text = _doc(60, needle_at=60)
    assert "retain records" not in text[:8000]  # blind prefix would miss it
    sel = select_relevant_text(text, ["7.3"], 8000)
    assert "retain records for a minimum period" in sel.lower()


def test_falls_back_to_prefix_when_no_query_terms():
    text = "x" * 50_000
    out = select_relevant_text(text, [], 10_000)
    assert out == text[:10_000]


def test_respects_char_budget():
    text = _doc(80, needle_at=40)
    out = select_relevant_text(text, ["7.5", "7.3"], 5000)
    assert len(out) <= 5000


def test_cjk_tokenizer_produces_bigrams():
    from rag.retriever import _tokenize
    toks = _tokenize("留存日志")
    assert "留存" in toks and "存日" in toks  # character bigrams


def test_cyrillic_is_tokenized():
    from rag.retriever import _tokenize
    assert "хранения" in _tokenize("срок хранения данных")


def test_chinese_statute_needs_local_terms(monkeypatch):
    # A Chinese statute with the retention clause buried; the English query
    # matches nothing, but the CHN local terms rank it.
    zh = ("第一条 立法目的与原则。" * 300
          + "第二十一条 网络运营者应当留存相关网络日志不少于六个月。" * 12
          + "附则。" * 3000)
    from rag.retriever import select_relevant_text
    assert "留存" not in select_relevant_text(zh, ["7.3"], 3000)             # no country -> prefix
    assert "留存" in select_relevant_text(zh, ["7.3"], 3000, country_code="CHN")


def test_hybrid_rrf_lets_dense_surface_a_lexically_weak_chunk(monkeypatch):
    """When hybrid retrieval is on, a semantically-relevant chunk that BM25 ranks
    low can be pulled into the budget by the dense signal via RRF fusion. We
    stub the dense ranker so the test needs no model download."""
    import rag.retriever as R

    # Filler sections whose wording avoids the query terms (so BM25 scores them
    # zero) + one target section BM25 also can't match but the stubbed dense
    # ranker loves. Small chunks + a roomy budget so the target isn't lost to the
    # final document-order truncation (we're testing selection, not budgeting).
    secs = [f"Section {i}. Administrative provisions apply. " for i in range(1, 21)]
    target = ("Section 99. The controller shall appoint a responsible person to "
              "oversee compliance and accountability for processing operations. ")
    secs.append(target)
    text = "\n\n".join(secs)

    # dense ranker: rank the chunk CONTAINING the target phrase first, whatever
    # index the chunker assigned it (don't assume the chunk layout).
    def fake_dense(query_text, chunks):
        tgt = next((i for i, c in enumerate(chunks) if "responsible person" in c), 0)
        rest = [i for i in range(len(chunks)) if i != tgt]
        return [(1.0, tgt)] + [(0.0, i) for i in rest]

    monkeypatch.setattr(R, "_dense_ranks", fake_dense)
    out = R.select_relevant_text(text, ["7.4"], 4000, country_code="RUS")
    assert "responsible person to oversee compliance" in out  # dense pulled it in

    # with dense off (default), the same call must not raise and stays BM25-only
    monkeypatch.setattr(R, "_dense_ranks", lambda *a, **k: None)
    out2 = R.select_relevant_text(text, ["7.4"], 4000, country_code="RUS")
    assert len(out2) <= 4000
