from __future__ import annotations

import sys
import types

import pytest

from discovery.adapters.china import ChinaFlkAdapter, _external_id_from_url
from discovery.adapters.search_engine import SearchEngineAdapter, strip_site_filter
from discovery.adapters.singapore import (
    SingaporeSsoAdapter,
    _extract_page_title,
    _known_law_hits,
    _parse_sso_search_results,
)
from discovery.adapters.thailand import ThailandOcsAdapter
from discovery.registry import get_sources


class FakeSearchBackend:
    async def search(self, query: str, limit: int):
        from discovery.schemas import RawSearchHit

        assert "site:" in query
        return [
            RawSearchHit(
                title="Live PDPC result",
                url="https://www.pdpc.gov.sg/help-and-resources/2024/live-result",
                snippet="Live result from configured search backend.",
            )
        ][:limit]


class FailingSearchBackend:
    async def search(self, _query: str, _limit: int):
        raise RuntimeError("backend down")


class FakeSsoClient:
    async def get(self, _url: str):
        raise RuntimeError("temporary outage")


class FakeChinaDriver:
    async def search_gov_law(self, query: str, limit: int = 10):
        assert "site:" not in query
        return [
            {
                "rank": 1,
                "title": "中华人民共和国个人信息保护法",
                "url": "https://flk.npc.gov.cn/detail2.html?id=pipl",
                "status": "现行有效",
                "publish_date": "2021-08-20",
                "type": "法律",
                "department": "全国人民代表大会常务委员会",
            }
        ][:limit]


@pytest.mark.anyio
async def test_china_flk_adapter_maps_opencli_results():
    adapter = ChinaFlkAdapter()
    rows = await adapter._search_queries(
        FakeChinaDriver(),
        ["site:flk.npc.gov.cn 数据出境安全评估 law"],
        limit=5,
    )

    assert len(rows) == 1
    assert rows[0].title == "中华人民共和国个人信息保护法"
    assert rows[0].url == "https://flk.npc.gov.cn/detail2.html?id=pipl"
    assert rows[0].position == 1
    assert rows[0].raw["status"] == "现行有效"
    assert rows[0].external_id == "id=pipl"


def test_china_flk_external_id_uses_query_token():
    assert _external_id_from_url("https://flk.npc.gov.cn/detail2.html?abc%3D") == "abc%3D"


@pytest.mark.anyio
async def test_china_flk_adapter_mock_mode_uses_fixture():
    source = get_sources("CHN")[0]
    rows = await ChinaFlkAdapter().search(
        country_code="CHN",
        source=source,
        queries=["site:flk.npc.gov.cn 个人信息保护法"],
        limit=2,
        browser_mode="mock",
    )

    assert rows
    assert rows[0].source_adapter == "china_flk"
    assert rows[0].retrieval_mode == "fixture"


@pytest.mark.anyio
async def test_china_flk_live_failure_marks_fixture_fallback(monkeypatch):
    adapter = ChinaFlkAdapter()

    async def fail_search(_driver, _queries, _limit):
        raise RuntimeError("driver down")

    monkeypatch.setattr(adapter, "_search_queries", fail_search)
    source = get_sources("CHN")[0]
    rows = await adapter.search(
        country_code="CHN",
        source=source,
        queries=["site:flk.npc.gov.cn 个人信息保护法"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("driver down" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_generic_search_adapter_non_mock_marks_fixture_fallback(monkeypatch):
    monkeypatch.delenv("DISCOVERY_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("DISCOVERY_USE_FIXTURES", raising=False)
    source = get_sources("SGP")[1]
    rows = await SearchEngineAdapter().search(
        country_code="SGP",
        source=source,
        queries=["site:pdpc.gov.sg data protection officer"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("not configured" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_generic_search_adapter_uses_configured_live_backend(monkeypatch):
    monkeypatch.delenv("DISCOVERY_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("DISCOVERY_USE_FIXTURES", raising=False)
    source = get_sources("SGP")[1]
    rows = await SearchEngineAdapter(search_backend=FakeSearchBackend()).search(
        country_code="SGP",
        source=source,
        queries=["site:pdpc.gov.sg data protection officer"],
        limit=2,
        browser_mode="auto",
    )

    assert len(rows) == 1
    assert rows[0].source_name == "Personal Data Protection Commission"
    assert rows[0].source_adapter == "search_engine"
    assert rows[0].retrieval_mode == "live"
    assert rows[0].query == "site:pdpc.gov.sg data protection officer"


@pytest.mark.anyio
async def test_generic_search_adapter_injected_backend_failure_falls_back_without_env(monkeypatch):
    monkeypatch.delenv("DISCOVERY_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("DISCOVERY_USE_FIXTURES", raising=False)
    source = get_sources("SGP")[1]
    rows = await SearchEngineAdapter(search_backend=FailingSearchBackend()).search(
        country_code="SGP",
        source=source,
        queries=["site:pdpc.gov.sg data protection officer"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("backend down" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_generic_search_adapter_missing_serpapi_key_falls_back(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SEARCH_BACKEND", "serpapi")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("DISCOVERY_USE_FIXTURES", raising=False)
    source = get_sources("SGP")[1]
    rows = await SearchEngineAdapter().search(
        country_code="SGP",
        source=source,
        queries=["site:pdpc.gov.sg data protection officer"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("SERPAPI_API_KEY is not set" in warning for warning in rows[0].warnings)


def test_strip_site_filter_handles_cjk_prefix_without_space():
    assert strip_site_filter("数据安全site:sso.agc.gov.sg") == "数据安全"
    assert strip_site_filter("site:sso.agc.gov.sg personal data") == "personal data"


def test_singapore_sso_parser_extracts_official_law_links():
    rows = _parse_sso_search_results(
        """
        <html>
          <body>
            <a href="Act/PDPA2012">Personal Data Protection Act 2012</a>
            <a href="/SL/PDPA2012-S362-2021">Personal Data Protection Regulations</a>
            <a href="https://example.com/not-law">Ignore this</a>
          </body>
        </html>
        """
    )

    assert [row["title"] for row in rows] == [
        "Personal Data Protection Act 2012",
        "Personal Data Protection Regulations",
    ]
    assert rows[0]["url"] == "https://sso.agc.gov.sg/Act/PDPA2012"


def test_singapore_sso_title_extraction_removes_site_suffix():
    title = _extract_page_title(
        "<title lang='en'>Personal Data Protection Act 2012 - Singapore Statutes Online</title>"
    )

    assert title == "Personal Data Protection Act 2012"


@pytest.mark.anyio
async def test_singapore_known_law_keeps_fallback_when_live_verification_fails():
    rows = await _known_law_hits(FakeSsoClient(), "personal data protection")

    assert rows
    assert rows[0]["title"] == "Personal Data Protection Act 2012"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "could not be verified live" in rows[0]["warnings"]


@pytest.mark.anyio
async def test_singapore_sso_mock_mode_uses_fixture():
    source = get_sources("SGP")[0]
    rows = await SingaporeSsoAdapter().search(
        country_code="SGP",
        source=source,
        queries=["site:sso.agc.gov.sg personal data protection"],
        limit=2,
        browser_mode="mock",
    )

    assert rows
    assert rows[0].source_adapter == "singapore_sso"
    assert rows[0].retrieval_mode == "fixture"


@pytest.mark.anyio
async def test_thailand_ocs_live_failure_marks_fixture_fallback(monkeypatch):
    async def fail_search(_query: str, max_results: int = 10):
        raise RuntimeError("ocs down")

    fake_crawler = types.ModuleType("crawler")
    fake_crawler.search_ocs_law = fail_search
    monkeypatch.setitem(sys.modules, "crawler", fake_crawler)
    source = get_sources("THA")[0]
    rows = await ThailandOcsAdapter().search(
        country_code="THA",
        source=source,
        queries=["site:ocs.go.th personal data protection law"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("ocs down" in warning for warning in rows[0].warnings)


async def fake_ocs_search(query: str, max_results: int = 10):
    assert "site:" not in query
    return [
        {
            "title": "Personal Data Protection Act B.E. 2562",
            "doc_id": "pdpa-2562",
            "doc_url": "https://searchlaw.ocs.go.th/council-of-state/#/public/doc/pdpa-2562",
            "lang": "th",
            "source": "ocs.go.th",
        }
    ][:max_results]


@pytest.mark.anyio
async def test_thailand_ocs_adapter_maps_search_results():
    adapter = ThailandOcsAdapter()
    rows = await adapter._search_queries(
        fake_ocs_search,
        ["site:ocs.go.th personal data protection law"],
        limit=5,
    )

    assert len(rows) == 1
    assert rows[0].title == "Personal Data Protection Act B.E. 2562"
    assert rows[0].external_id == "pdpa-2562"
    assert rows[0].source_adapter == "thailand_ocs"
