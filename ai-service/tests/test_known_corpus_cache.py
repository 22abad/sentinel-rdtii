from __future__ import annotations

import json

from services import known_corpus_cache as kcc


def _write_corpus(tmp_path, entries):
    """Write a tiny known_corpus manifest + text files, point the module at it."""
    corpus = tmp_path / "known_corpus"
    corpus.mkdir()
    lines = []
    for e in entries:
        if e.get("_text") is not None:
            p = corpus / f"{e['slug']}.txt"
            p.write_text(e["_text"], encoding="utf-8")
            e = {**e, "text_path": str(p)}
        lines.append(json.dumps({k: v for k, v in e.items() if not k.startswith("_")}))
    (corpus / "manifest.jsonl").write_text("\n".join(lines), encoding="utf-8")
    return corpus / "manifest.jsonl"


def test_cache_serves_text_for_known_url(tmp_path, monkeypatch):
    manifest = _write_corpus(tmp_path, [
        {"economy": "SGP", "law_name": "Real Act", "slug": "real",
         "url": "https://gov.example/real", "_text": "A" * 800},
        {"economy": "SGP", "law_name": "Stub Act", "slug": "stub",
         "url": "https://gov.example/stub", "_text": "too short"},   # < 400 chars
        {"economy": "SGP", "law_name": "No File", "slug": "nofile",
         "url": "https://gov.example/nofile", "_text": None},        # no text file
    ])
    monkeypatch.setattr(kcc, "_MANIFEST", manifest)
    kcc._url_index.cache_clear()

    assert kcc.cached_text_for_url("https://gov.example/real") == "A" * 800
    # too-short cached text is treated as unusable
    assert kcc.cached_text_for_url("https://gov.example/stub") is None
    # entry with no text file on disk
    assert kcc.cached_text_for_url("https://gov.example/nofile") is None
    # unknown URL, empty URL
    assert kcc.cached_text_for_url("https://gov.example/absent") is None
    assert kcc.cached_text_for_url("") is None
    # both entries with a text file are indexed; the length gate is at read time
    assert kcc.corpus_size() == 2
    kcc._url_index.cache_clear()


def test_missing_manifest_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(kcc, "_MANIFEST", tmp_path / "does_not_exist.jsonl")
    kcc._url_index.cache_clear()
    assert kcc.cached_text_for_url("https://gov.example/x") is None
    assert kcc.corpus_size() == 0
    kcc._url_index.cache_clear()
