"""Tests for the Indonesia peraturan.bpk.go.id discovery adapter."""

from __future__ import annotations

import pytest

from discovery.adapters.indonesia_bpk import IndonesiaBpkAdapter
from discovery.schemas import LegalSourceConfig

_SEARCH_HTML = """
<html><body>
  <a href="/Details/229798/uu-no-27-tahun-2022">UU 27/2022</a>
  <a href="/Details/150543/permenkominfo-no-20-tahun-2016">Permenkominfo 20/2016</a>
  <a href="/Details/999999/uu-no-1-tahun-1990-dicabut">Old law</a>
</body></html>
"""

_DETAILS = {
    "229798": """<html><head><title>UU No. 27 Tahun 2022</title></head>
        <body><h1>Pelindungan Data Pribadi</h1><span>Berlaku</span>
        <a href="/Download/402884/UU%20Nomor%2027%20Tahun%202022.pdf">PDF</a></body></html>""",
    "150543": """<html><head><title>Permenkominfo No. 20 Tahun 2016</title></head>
        <body><h1>Perlindungan Data Pribadi Dalam Sistem Elektronik</h1><span>Berlaku</span>
        <a href="/Download/111/permenkominfo-20-2016.pdf">PDF</a></body></html>""",
    "999999": """<html><head><title>UU No. 1 Tahun 1990</title></head>
        <body><h1>Old Law</h1><span>Dicabut</span>
        <a href="/Download/222/old.pdf">PDF</a></body></html>""",
}


class _FakeClient:
    def __init__(self):
        self.gets: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        self.gets.append(url)

        class _R:
            text = ""

        r = _R()
        if "/Search" in url:
            r.text = _SEARCH_HTML
        else:
            did = url.rstrip("/").split("/Details/")[1].split("/")[0]
            r.text = _DETAILS.get(did, "")
        return r


def _src():
    return LegalSourceConfig(
        name="BPK", base_url="https://peraturan.bpk.go.id",
        domains=["peraturan.bpk.go.id"], adapter="indonesia_bpk",
    )


@pytest.mark.anyio
async def test_returns_in_force_laws_with_pdf(monkeypatch):
    monkeypatch.setattr("discovery.adapters.indonesia_bpk._open_client", _FakeClient)
    hits = await IndonesiaBpkAdapter().search(
        country_code="IDN", source=_src(), queries=["perlindungan data pribadi"], limit=10
    )
    titles = [h.title for h in hits]
    assert any("UU No. 27 Tahun 2022" in t and "Pelindungan Data Pribadi" in t for t in titles)
    assert all(h.url.endswith(".pdf") for h in hits)
    assert all(h.retrieval_mode == "live" for h in hits)


@pytest.mark.anyio
async def test_revoked_law_is_dropped(monkeypatch):
    monkeypatch.setattr("discovery.adapters.indonesia_bpk._open_client", _FakeClient)
    hits = await IndonesiaBpkAdapter().search(
        country_code="IDN", source=_src(), queries=["data"], limit=10
    )
    # The "Dicabut" (revoked) instrument must not appear.
    assert not any("1 Tahun 1990" in h.title for h in hits)
    assert len(hits) == 2


@pytest.mark.anyio
async def test_non_indonesia_returns_empty(monkeypatch):
    def _boom():
        raise AssertionError("must not scrape for a non-Indonesia country")

    monkeypatch.setattr("discovery.adapters.indonesia_bpk._open_client", _boom)
    hits = await IndonesiaBpkAdapter().search(
        country_code="THA", source=_src(), queries=["data"], limit=5
    )
    assert hits == []


def test_localizes_english_pillar_queries_to_indonesian():
    from discovery.adapters.indonesia_bpk import _localize_query
    assert _localize_query("personal data protection act") == "perlindungan data pribadi"
    assert _localize_query("cross-border data transfer ban") == "transfer data pribadi ke luar negeri"
    assert _localize_query("cybersecurity law") == "keamanan siber"
    assert _localize_query("data retention requirement") == "penyimpanan dokumen elektronik"
    # An unmapped query falls back to itself.
    assert _localize_query("xyz random") == "xyz random"
