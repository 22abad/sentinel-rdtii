"""Tests for the Open Development Mekong CKAN discovery adapter."""

from __future__ import annotations

import pytest

from discovery.adapters.mekong_ckan import MekongCkanAdapter, _pdf_resource
from discovery.schemas import LegalSourceConfig


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Async context-manager client returning one canned CKAN payload."""

    def __init__(self, payload):
        self._payload = payload
        self.requested: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        self.requested.append(url)
        return _FakeResp(self._payload)


_PDPA = {
    "id": "pkg-pdpa",
    "title": "Personal Data Protection Act B.E. 2562 (2019)",
    "name": "2562",
    "odm_laws_status": "signed_and_in_effect",
    "odm_laws_source": "http://www.ratchakitcha.soc.go.th/DATA/PDF/2562/A/069/T_0052.PDF",
    "odm_keywords": "PDP,Privacy",
    "resources": [{"format": "PDF", "url": "https://data.opendevelopmentmekong.net/x/t_0052.pdf"}],
}
_DRAFT = {
    "id": "pkg-draft",
    "title": "Draft Cyber Bill",
    "odm_laws_status": "draft",
    "resources": [{"format": "PDF", "url": "https://data.opendevelopmentmekong.net/x/draft.pdf"}],
}


def _payload(*pkgs):
    return {"success": True, "result": {"count": len(pkgs), "results": list(pkgs)}}


@pytest.mark.anyio
async def test_returns_in_force_law_with_official_provenance(monkeypatch):
    client = _FakeClient(_payload(_PDPA))
    monkeypatch.setattr("discovery.adapters.mekong_ckan._open_client", lambda: client)
    src = LegalSourceConfig(
        name="ODM", base_url="https://data.opendevelopmentmekong.net",
        domains=["data.opendevelopmentmekong.net"], adapter="mekong_ckan",
    )
    hits = await MekongCkanAdapter().search(
        country_code="THA", source=src, queries=["personal data protection"], limit=5
    )
    assert len(hits) == 1
    h = hits[0]
    assert h.url.endswith("t_0052.pdf")
    assert h.discovery_method == "ckan_open_development_mekong"
    assert h.retrieval_mode == "live"
    # Official gazette source is carried through for provenance.
    assert "ratchakitcha" in h.raw["official_source"]
    # The org+type filter was sent to CKAN.
    assert "organization%3Athailand-organization" in client.requested[0]


@pytest.mark.anyio
async def test_drafts_are_dropped(monkeypatch):
    client = _FakeClient(_payload(_PDPA, _DRAFT))
    monkeypatch.setattr("discovery.adapters.mekong_ckan._open_client", lambda: client)
    src = LegalSourceConfig(
        name="ODM", base_url="https://x", domains=["x"], adapter="mekong_ckan",
    )
    hits = await MekongCkanAdapter().search(
        country_code="THA", source=src, queries=["cyber"], limit=5
    )
    assert [h.title for h in hits] == ["Personal Data Protection Act B.E. 2562 (2019)"]


@pytest.mark.anyio
async def test_unsupported_country_returns_empty(monkeypatch):
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        raise AssertionError("must not open a client for an unsupported country")

    monkeypatch.setattr("discovery.adapters.mekong_ckan._open_client", _boom)
    src = LegalSourceConfig(name="ODM", base_url="https://x", domains=["x"], adapter="mekong_ckan")
    hits = await MekongCkanAdapter().search(
        country_code="CHN", source=src, queries=["data"], limit=5
    )
    assert hits == [] and called["n"] == 0


def test_pdf_resource_prefers_pdf_then_official_source():
    assert _pdf_resource(_PDPA).endswith("t_0052.pdf")
    # No PDF resource → fall back to the official gazette URL.
    only_source = {"odm_laws_source": "http://gazette/x.pdf", "resources": []}
    assert _pdf_resource(only_source) == "http://gazette/x.pdf"
