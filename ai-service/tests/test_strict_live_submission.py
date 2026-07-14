from __future__ import annotations

from types import SimpleNamespace

import pytest

import discovery
import providers
from discovery.schemas import LegalCandidate
from services import document_fetch, extraction
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
