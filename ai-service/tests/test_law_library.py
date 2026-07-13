from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from law_library import LawLibraryError, load_library, lookup
from submission.pipeline import run_library


def test_checked_in_library_loads_and_integrity_checks():
    entries = load_library()
    assert len(entries) == 5
    assert {e.economy for e in entries} == {"AUS", "MYS", "SGP"}
    # Every cached text passed SHA-256 verification on load and is non-empty.
    for e in entries:
        assert e.text.strip()
        assert hashlib.sha256(e.text.encode("utf-8")).hexdigest() == e.sha256
        assert e.discovery_tag == "KNOWN"
        assert e.official_url.startswith("http")


def test_lookup_filters_by_economy_and_pillar():
    assert {e.law_name for e in lookup("AUS", pillar=6)} == {
        "My Health Records Act 2012",
        "Privacy Act 1988",
    }
    # SGP PDPA is tagged for pillars 6 and 7; Income Tax Act only pillar 7.
    p7 = {e.law_name for e in lookup("SGP", pillar=7)}
    assert "Income Tax Act 1947" in p7
    assert "Personal Data Protection Act 2012" in p7
    assert lookup("sgp", pillar=6) and all(e.economy == "SGP" for e in lookup("sgp", pillar=6))
    assert lookup("MYS")  # case-insensitive economy, no pillar filter


def test_lookup_indicator_hint_narrows_results():
    # Only the Income Tax Act carries the 7.3 hint; PDPA's hint is 6.4.
    names = {e.law_name for e in lookup("SGP", indicators=["7.3"])}
    assert names == {"Income Tax Act 1947"}


def test_missing_manifest_returns_empty(tmp_path):
    assert load_library(library_root=tmp_path, repo_root=tmp_path) == []


def test_sha_mismatch_raises(tmp_path):
    (tmp_path / "text").mkdir()
    text_file = tmp_path / "text" / "law.txt"
    text_file.write_text("actual cached text", encoding="utf-8")
    record = {
        "law_id": "tampered",
        "economy": "SGP",
        "law_name": "Tampered Act",
        "official_url": "https://example.gov/law",
        "source_status": "in_force",
        "pillars": [6],
        "indicator_hints": ["6.1"],
        "language_codes": ["en"],
        "text_path": "text/law.txt",
        "sha256": hashlib.sha256(b"different text").hexdigest(),
        "retrieved_at": "2026-07-13",
        "discovery_tag": "KNOWN",
    }
    (tmp_path / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(LawLibraryError, match="SHA-256 mismatch"):
        load_library(library_root=tmp_path, repo_root=tmp_path)


@pytest.mark.anyio
async def test_run_library_offline_tags_rows_known(monkeypatch):
    async def fake_extraction(text, provider):
        mapping = SimpleNamespace(
            pillar=6,
            indicator="6.4",
            article_clause="Section 26",
            verbatim_quote=text[:40],
            quote_start=0,
            quote_end=40,
            source_legislation="Personal Data Protection Act 2012",
            last_update="",
            source_url="",
            impact="Conditional cross-border flow regime.",
            requires_human_review=False,
            flag_reasons=[],
        )
        return SimpleNamespace(mappings=[mapping])

    monkeypatch.setattr("services.extraction.run_extraction", fake_extraction)
    monkeypatch.setattr("providers.get_default_provider", lambda: SimpleNamespace(name="fake"))

    rows, meta = await run_library("SGP", 6)

    assert meta["offline"] is True
    assert meta["source"] == "local_library"
    assert meta["laws_available"] == 1  # only PDPA covers SGP pillar 6
    assert len(rows) == 1
    row = rows[0]
    assert row.discovery_tag == "KNOWN"
    assert row.indicator_id == "P6-I4"
    assert row.retrieval_method == "known_mapping"
    assert row.source_url == "https://sso.agc.gov.sg/Act/PDPA2012"


@pytest.mark.anyio
async def test_run_library_reports_empty_economy(monkeypatch):
    async def unused_extraction(text, provider):  # pragma: no cover - must not run
        raise AssertionError("extraction should not run when no cached laws match")

    monkeypatch.setattr("services.extraction.run_extraction", unused_extraction)
    monkeypatch.setattr("providers.get_default_provider", lambda: SimpleNamespace(name="fake"))

    rows, meta = await run_library("Thailand", 6)
    assert rows == []
    assert meta["laws_available"] == 0
    assert any("no cached laws" in w for w in meta["warnings"])
