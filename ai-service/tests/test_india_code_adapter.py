"""Tests for the India Code (indiacode.nic.in) discovery adapter."""

from __future__ import annotations

import pytest

from discovery.adapters.india_code import IndiaCodeAdapter, _clean_title
from discovery.schemas import LegalSourceConfig

_SEARCH = """
<table class="table table-hover">
<tr><th id="t1">Date</th><th id="t2">Act No</th><th id="t3">Short Title</th><th id="t4">View</th></tr>
<tr><td headers="t1">11-Aug-2023</td><td headers="t2"><em>22</em></td>
    <td headers="t3">The Digital Personal <font color=#F778A1><B>Data</B></font> Protection Act, 2023.</td>
    <td headers="t4"><a href="/handle/123456789/22037?view_type=search">View...</a></td></tr>
<tr><td headers="t1">09-Jun-2000</td><td headers="t2"><em>21</em></td>
    <td headers="t3">The Information Technology Act, 2000</td>
    <td headers="t4"><a href="/handle/123456789/13116?view_type=search&col=123456789/1362">View...</a></td></tr>
</table>
"""

_HANDLE = {
    "22037": '<a href="/bitstream/123456789/22037/1/a2023-22.pdf">Download</a>',
    "13116": '<a href="/bitstream/123456789/13116/1/it_act_2000.pdf">Download</a>',
}


class _FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        class _R:
            text = ""

        r = _R()
        if "/simple-search" in url:
            r.text = _SEARCH
        else:
            hid = url.rstrip("/").split("/handle/123456789/")[1].split("/")[0].split("?")[0]
            r.text = _HANDLE.get(hid, "")
        return r


def _src():
    return LegalSourceConfig(
        name="India Code", base_url="https://www.indiacode.nic.in",
        domains=["indiacode.nic.in", "www.indiacode.nic.in"], adapter="india_code",
    )


def test_clean_title_strips_highlight_markup():
    raw = "The Digital Personal <font color=#F778A1><B>Data</B></font> Protection Act, 2023."
    assert _clean_title(raw) == "The Digital Personal Data Protection Act, 2023"


@pytest.mark.anyio
async def test_search_resolves_handle_to_bitstream_pdf(monkeypatch):
    monkeypatch.setattr("discovery.adapters.india_code._open_client", _FakeClient)
    hits = await IndiaCodeAdapter().search(
        country_code="IND", source=_src(), queries=["data protection"], limit=10
    )
    assert len(hits) == 2
    dpdp = hits[0]
    assert dpdp.title == "The Digital Personal Data Protection Act, 2023"
    assert dpdp.url == "https://www.indiacode.nic.in/bitstream/123456789/22037/1/a2023-22.pdf"
    assert dpdp.external_id == "22037"
    assert all(h.url.endswith(".pdf") for h in hits)


@pytest.mark.anyio
async def test_non_india_returns_empty(monkeypatch):
    def _boom():
        raise AssertionError("must not scrape for a non-India country")

    monkeypatch.setattr("discovery.adapters.india_code._open_client", _boom)
    hits = await IndiaCodeAdapter().search(
        country_code="IDN", source=_src(), queries=["data"], limit=5
    )
    assert hits == []
