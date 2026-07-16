from __future__ import annotations

from types import SimpleNamespace

import pytest

import discovery
import providers
from discovery.schemas import LegalCandidate
from schemas import ExtractionResponse, IndicatorMapping
from services import document_fetch, extraction
from services.document_fetch import CrawlQuality, DocumentText
from submission.pipeline import discover_and_extract


@pytest.mark.anyio
async def test_formal_submission_excludes_fixture_fallback_candidates(monkeypatch):
    candidate = LegalCandidate(
        id="fixture-fallback",
        country_code="SGP",
        title="Configured Fixture Act",
        url="https://sso.agc.gov.sg/Act/FIXTURE",
        source_domain="sso.agc.gov.sg",
        official_domains=["sso.agc.gov.sg"],
        source_name="Singapore Statutes Online",
        source_grade="primary",
        matched_pillars=[6],
        matched_indicators=["6.4"],
        retrieval_mode="fallback",
        discovery_method="fixture",
    )

    class FakeDiscoveryService:
        async def search(self, _request):
            return SimpleNamespace(
                candidates=[candidate],
                diagnostics={"mode": "auto_with_adapter_fallbacks"},
            )

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("fixture candidates must not be fetched or extracted")

    monkeypatch.setattr(discovery, "DiscoveryService", FakeDiscoveryService)
    monkeypatch.setattr(providers, "resolve_provider", lambda _name: SimpleNamespace(name="fake"))
    monkeypatch.setattr(document_fetch, "fetch_document_text", forbidden)
    monkeypatch.setattr(extraction, "run_extraction", forbidden)

    rows, meta = await discover_and_extract("Singapore", 6)

    assert rows == []
    assert meta["fixture_candidates_excluded"] == 1
    assert meta["documents_processed"] == 0
    assert meta["evidence_counts"] == {
        "seed": 0,
        "live_discovered": 0,
        "fixture": 0,
    }


@pytest.mark.anyio
async def test_live_submission_populates_pdf_audit_metadata(monkeypatch):
    page_one = "Section 1. General rules."
    page_two = "Section 26. Personal data shall not be transferred overseas."
    text = f"{page_one}\n{page_two}"
    quote = "Personal data shall not be transferred overseas."
    quote_start = text.index(quote)
    candidate = LegalCandidate(
        id="live-pdf",
        country_code="SGP",
        title="Official Data Act",
        url="https://official.example/data.pdf",
        source_domain="official.example",
        official_domains=["official.example"],
        source_name="Official Gazette",
        source_grade="primary",
        matched_pillars=[6],
        matched_indicators=["6.4"],
        retrieval_mode="live",
        discovery_method="official_search",
        confidence=0.88,
    )

    class FakeDiscoveryService:
        async def search(self, _request):
            return SimpleNamespace(candidates=[candidate], diagnostics={"mode": "live"})

    async def fake_fetch(*_args, **_kwargs):
        return DocumentText(
            source_url=candidate.url,
            text=text,
            content_type="pdf",
            pdf_metadata={
                "mean_confidence": 0.91,
                "ocr_ratio": 0.5,
                "pdf_type": "mixed",
                "page_char_spans": [
                    {"page": 1, "start": 0, "end": len(page_one)},
                    {"page": 2, "start": len(page_one) + 1, "end": len(text)},
                ],
                "source_file_sha256": "a" * 64,
                "source_pdf_path": "/evidence/data.pdf",
            },
            crawl_metadata={
                "final_url": candidate.url,
                "fetch_method": "download",
                "http_status": 200,
            },
            quality=CrawlQuality(status="good", should_extract=True),
            timing_seconds={"fetch": 1.0, "pdf_processing": 2.0},
        )

    async def fake_extract(*_args, **_kwargs):
        return ExtractionResponse(mappings=[IndicatorMapping(
            pillar=6,
            indicator="6.4",
            score=1.0,
            verbatim_quote=quote,
            quote_start=quote_start,
            quote_end=quote_start + len(quote),
            article_clause="Section 26",
            source_legislation="Official Data Act",
            source_url=candidate.url,
        )])

    monkeypatch.setattr(discovery, "DiscoveryService", FakeDiscoveryService)
    monkeypatch.setattr(
        providers,
        "resolve_provider",
        lambda _name: SimpleNamespace(name="provider", model_name="model-v2"),
    )
    monkeypatch.setattr(document_fetch, "fetch_document_text", fake_fetch)
    monkeypatch.setattr(extraction, "run_extraction", fake_extract)

    rows, _meta = await discover_and_extract("Singapore", 6)

    assert len(rows) == 1
    row = rows[0]
    assert row.location_reference == "p. 2"
    assert row.pdf_type == "mixed"
    assert row.pdf_is_scanned is False
    assert row.ocr_quality_cer == pytest.approx(0.09)
    assert row.processing_time_seconds >= 3.0
    assert row.model_version == "model-v2"
    assert row.source_file_sha256 == "a" * 64
    assert row.source_pdf_path == "/evidence/data.pdf"
    assert row.confidence_type == "discovery_confidence"


@pytest.mark.anyio
async def test_out_of_scope_candidates_are_skipped_before_fetch(monkeypatch):
    """A candidate the submission noise-gate would drop anyway (trade agreement,
    blog) is skipped BEFORE the expensive fetch + LLM extraction — and the skip
    is loudly reported (warning + meta count), never silent."""
    agreement = LegalCandidate(
        id="dea",
        country_code="SGP",
        title="Australia-Singapore Digital Economy Agreement",
        url="https://www.mti.gov.sg/Trade/Digital-Economy-Agreements",
        source_domain="mti.gov.sg",
        official_domains=["mti.gov.sg"],
        source_name="MTI",
        source_grade="primary",
        matched_pillars=[6],
        matched_indicators=["6.4"],
        retrieval_mode="live",
        discovery_method="portal_search",
    )

    class FakeDiscoveryService:
        async def search(self, _request):
            return SimpleNamespace(
                candidates=[agreement],
                diagnostics={"mode": "auto"},
            )

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("out-of-scope candidates must not be fetched or extracted")

    monkeypatch.setattr(discovery, "DiscoveryService", FakeDiscoveryService)
    monkeypatch.setattr(providers, "resolve_provider", lambda _name: SimpleNamespace(name="fake"))
    monkeypatch.setattr(document_fetch, "fetch_document_text", forbidden)
    monkeypatch.setattr(extraction, "run_extraction", forbidden)

    rows, meta = await discover_and_extract("Singapore", 6)

    assert rows == []
    assert meta["candidates_skipped_out_of_scope"] == 1
    assert meta["documents_processed"] == 0
    # Loud, not silent: the skip is recorded as a warning naming the candidate.
    assert any("out-of-scope" in w and "Digital Economy Agreement" in w
               for w in meta.get("warnings", []))


@pytest.mark.anyio
async def test_domestic_statute_candidates_are_not_prefiltered(monkeypatch):
    """The pre-filter must NOT touch a genuine domestic statute — it reaches
    the fetch stage (here mocked to fail, proving fetch was attempted)."""
    statute = LegalCandidate(
        id="pdpa",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_domain="sso.agc.gov.sg",
        official_domains=["sso.agc.gov.sg"],
        source_name="Singapore Statutes Online",
        source_grade="primary",
        matched_pillars=[6],
        matched_indicators=["6.4"],
        retrieval_mode="live",
        discovery_method="portal_search",
    )

    class FakeDiscoveryService:
        async def search(self, _request):
            return SimpleNamespace(candidates=[statute], diagnostics={"mode": "auto"})

    fetch_attempted = {"n": 0}

    async def failing_fetch(*_args, **_kwargs):
        fetch_attempted["n"] += 1
        raise RuntimeError("network down (test)")

    monkeypatch.setattr(discovery, "DiscoveryService", FakeDiscoveryService)
    monkeypatch.setattr(providers, "resolve_provider", lambda _name: SimpleNamespace(name="fake"))
    monkeypatch.setattr(document_fetch, "fetch_document_text", failing_fetch)

    rows, meta = await discover_and_extract("Singapore", 6)

    assert fetch_attempted["n"] == 1, "a real statute must reach the fetch stage"
    assert meta["candidates_skipped_out_of_scope"] == 0
