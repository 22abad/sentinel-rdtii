from __future__ import annotations

import sys
import types

import pytest

from discovery.adapters.australia import (
    AustraliaLegislationAdapter,
    _external_id_from_url as _australia_external_id_from_url,
    _extract_page_title as _extract_australia_page_title,
    _known_instrument_hits,
    _parse_legislation_api_results,
    _parse_legislation_search_results,
)
from discovery.adapters.china import (
    ChinaFlkAdapter,
    _external_id_from_url,
    _extract_flk_title,
    _known_law_hits as _china_known_law_hits,
)
from discovery.adapters.malaysia import (
    MalaysiaLomAdapter,
    _external_id_from_url as _malaysia_external_id_from_url,
    _extract_lom_title,
    _known_act_hits,
    _parse_lom_api_results,
    _parse_lom_search_results,
)
from discovery.adapters.search_engine import SearchEngineAdapter, strip_site_filter
from discovery.adapters.singapore import (
    SingaporeSsoAdapter,
    _extract_page_title,
    _known_law_hits,
    _parse_sso_search_results,
)
from discovery.adapters.thailand import (
    ThailandOcsAdapter,
    _expanded_ocs_queries,
    _external_id_from_url as _thailand_external_id_from_url,
)
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


class FailingClient:
    async def get(self, _url: str, **_kwargs):
        raise RuntimeError("temporary outage")


class FakeLivePageResponse:
    def __init__(self, value, url: str = "https://example.test") -> None:
        self.text = value if isinstance(value, str) else ""
        self._payload = value if isinstance(value, dict) else None
        self.url = url

    def raise_for_status(self) -> None:
        return None

    def json(self):
        if self._payload is None:
            raise ValueError("response is not JSON")
        return self._payload


class FakeUrlClient:
    def __init__(self, pages: dict[str, object]) -> None:
        self.pages = pages

    async def get(self, url: str, **_kwargs):
        if url not in self.pages:
            raise RuntimeError(f"unexpected url: {url}")
        return FakeLivePageResponse(self.pages[url], url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


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


def test_australia_legislation_parser_extracts_official_links():
    rows = _parse_legislation_search_results(
        """
        <html>
          <body>
            <a href="/Latest/C2004A03712">Privacy Act 1988</a>
            <a href="https://www.legislation.gov.au/Details/C2018A00029">Security of Critical Infrastructure Act 2018</a>
            <a href="https://example.com/not-official">Ignore this</a>
          </body>
        </html>
        """
    )

    assert [row["title"] for row in rows] == [
        "Privacy Act 1988",
        "Security of Critical Infrastructure Act 2018",
    ]
    assert rows[0]["url"] == "https://www.legislation.gov.au/Latest/C2004A03712"
    assert rows[0]["external_id"] == "C2004A03712"


def test_australia_official_api_parser_extracts_title():
    rows = _parse_legislation_api_results({
        "value": [{
            "id": "C2004A03712",
            "name": "Privacy Act 1988",
            "collection": "Act",
            "isInForce": True,
        }],
    })

    assert rows[0]["title"] == "Privacy Act 1988"
    assert rows[0]["url"] == "https://www.legislation.gov.au/C2004A03712/latest/text"


@pytest.mark.anyio
async def test_australia_official_api_result_is_live(monkeypatch):
    api_url = (
        "https://api.prod.legislation.gov.au/v1/titles/"
        "search(criteria='text(%22privacy%20act%22,nameAndText,contains)')"
    )
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_kwargs: FakeUrlClient({api_url: {
            "value": [{"id": "C2004A03712", "name": "Privacy Act 1988"}],
        }}),
    )

    rows = await AustraliaLegislationAdapter()._search_queries(["privacy act"], 5)

    assert rows[0].retrieval_mode == "live"
    assert rows[0].discovery_method == "official_search"


def test_australia_title_extraction_strips_inner_html():
    title = _extract_australia_page_title(
        "<title>Privacy <em>Act</em> 1988 - Federal Register of Legislation</title>"
    )

    assert title == "Privacy Act 1988"


def test_australia_external_id_extracts_compilation_id():
    assert _australia_external_id_from_url("https://www.legislation.gov.au/Latest/C2018A00029") == "C2018A00029"


@pytest.mark.anyio
async def test_australia_known_instrument_stays_fallback_when_verified():
    rows = await _known_instrument_hits(
        FakeUrlClient({
            "https://www.legislation.gov.au/Latest/C2004A03712": (
                "<title>Privacy Act 1988 - Federal Register of Legislation</title>"
            ),
        }),
        "privacy act",
    )

    assert rows
    assert rows[0]["title"] == "Privacy Act 1988"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "not returned by the official search" in rows[0]["warnings"][0]


@pytest.mark.anyio
async def test_australia_known_instrument_keeps_fallback_when_live_verification_fails():
    rows = await _known_instrument_hits(FailingClient(), "privacy act")

    assert rows
    assert rows[0]["title"] == "Privacy Act 1988"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "could not be verified live" in rows[0]["warnings"][0]


@pytest.mark.anyio
async def test_australia_adapter_mock_mode_uses_fixture():
    source = get_sources("AUS")[0]
    rows = await AustraliaLegislationAdapter().search(
        country_code="AUS",
        source=source,
        queries=["site:legislation.gov.au privacy act"],
        limit=2,
        browser_mode="mock",
    )

    assert rows
    assert rows[0].source_adapter == "australia_legislation"
    assert rows[0].retrieval_mode == "fixture"


@pytest.mark.anyio
async def test_australia_adapter_live_failure_marks_fixture_fallback(monkeypatch):
    adapter = AustraliaLegislationAdapter()

    async def fail_search(_queries, _limit):
        raise RuntimeError("legislation down")

    monkeypatch.setattr(adapter, "_search_queries", fail_search)
    source = get_sources("AUS")[0]
    rows = await adapter.search(
        country_code="AUS",
        source=source,
        queries=["site:legislation.gov.au privacy act"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("legislation down" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_australia_adapter_empty_live_results_falls_back(monkeypatch):
    adapter = AustraliaLegislationAdapter()

    async def empty_search(_queries, _limit):
        return []

    monkeypatch.setattr(adapter, "_search_queries", empty_search)
    source = get_sources("AUS")[0]
    rows = await adapter.search(
        country_code="AUS",
        source=source,
        queries=["site:legislation.gov.au privacy act"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("returned no results" in warning for warning in rows[0].warnings)


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


def test_china_flk_title_extraction_finds_known_law_title_in_body():
    title = _extract_flk_title(
        "<html><title>国家法律法规数据库</title><body>中华人民共和国个人信息保护法 目录 正文</body></html>"
    )

    assert title == "中华人民共和国个人信息保护法"


@pytest.mark.anyio
async def test_china_flk_known_law_marks_live_when_verified():
    rows = await _china_known_law_hits(
        FakeUrlClient({
            "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3YjY4M2JhYjAxN2I5MTYxYzQyMjA4M2I%3D": (
                "<html><body>中华人民共和国个人信息保护法</body></html>"
            ),
        }),
        "personal information protection",
    )

    assert rows
    assert rows[0]["title"] == "中华人民共和国个人信息保护法"
    assert rows[0]["retrieval_mode"] == "live"
    assert rows[0]["warnings"] == []


@pytest.mark.anyio
async def test_china_flk_known_law_keeps_fallback_when_live_verification_fails():
    rows = await _china_known_law_hits(FailingClient(), "cybersecurity law")

    assert rows
    assert rows[0]["title"] == "中华人民共和国网络安全法"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "could not be verified live" in rows[0]["warnings"][0]


@pytest.mark.anyio
async def test_china_flk_known_law_rejects_generic_database_title():
    rows = await _china_known_law_hits(
        FakeUrlClient({
            "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3YjY4M2JhYjAxN2I5MTYxYzQyMjA4M2I%3D": (
                "<html><title>国家法律法规数据库</title><body></body></html>"
            ),
        }),
        "personal information protection",
    )

    assert rows[0]["title"] == "中华人民共和国个人信息保护法"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "expected law title" in rows[0]["warnings"][-1]


@pytest.mark.anyio
async def test_china_flk_live_driver_result_replaces_pending_known_law_fallback():
    known_url = (
        "https://flk.npc.gov.cn/detail2.html?"
        "ZmY4MDgxODE3YjY4M2JhYjAxN2I5MTYxYzQyMjA4M2I%3D"
    )

    class LiveDriver:
        async def search_gov_law(self, query: str, limit: int = 10):
            return [{
                "title": "中华人民共和国个人信息保护法",
                "url": known_url,
                "status": "现行有效",
            }]

    adapter = ChinaFlkAdapter()
    rows = await adapter._search_queries(
        LiveDriver(),
        ["site:flk.npc.gov.cn 个人信息保护法"],
        limit=1,
        client=FailingClient(),
    )

    assert len(rows) == 1
    assert rows[0].retrieval_mode == "live"
    assert rows[0].url == known_url
    assert rows[0].warnings == []


@pytest.mark.anyio
async def test_china_flk_keeps_known_law_fallback_when_driver_fills_limit_with_other_hits():
    class UnrelatedDriver:
        async def search_gov_law(self, query: str, limit: int = 10):
            return [{
                "title": "中华人民共和国电子商务法",
                "url": "https://flk.npc.gov.cn/detail2.html?id=ecommerce",
                "status": "现行有效",
            }]

    rows = await ChinaFlkAdapter()._search_queries(
        UnrelatedDriver(),
        ["site:flk.npc.gov.cn 个人信息保护法"],
        limit=1,
        client=FailingClient(),
    )

    assert len(rows) == 1
    assert rows[0].title == "中华人民共和国个人信息保护法"
    assert rows[0].retrieval_mode == "fallback"


@pytest.mark.anyio
async def test_china_flk_does_not_verify_title_found_only_in_script():
    rows = await _china_known_law_hits(
        FakeUrlClient({
            "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3YjY4M2JhYjAxN2I5MTYxYzQyMjA4M2I%3D": (
                "<html><title>国家法律法规数据库</title>"
                "<script>window.lawTitle = '中华人民共和国个人信息保护法';</script>"
                "<body></body></html>"
            ),
        }),
        "personal information protection",
    )

    assert rows[0]["retrieval_mode"] == "fallback"
    assert "expected law title" in rows[0]["warnings"][-1]


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

    async def fail_search(_driver, _queries, _limit, client=None):
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


def test_malaysia_lom_parser_extracts_official_act_links():
    rows = _parse_lom_search_results(
        """
        <html>
          <body>
            <a href="/act-detail.php?act=709&lang=BI&type=principal">Personal Data Protection Act 2010</a>
            <a href="https://lom.agc.gov.my/act-detail.php?act=854&lang=BI&type=principal">Cyber Security Act 2024</a>
            <a href="https://example.com/not-official">Ignore this</a>
          </body>
        </html>
        """
    )

    assert [row["title"] for row in rows] == [
        "Personal Data Protection Act 2010",
        "Cyber Security Act 2024",
    ]
    assert rows[0]["url"] == "https://lom.agc.gov.my/act-detail.php?act=709&lang=BI&type=principal"
    assert rows[0]["external_id"] == "act-709"


def test_malaysia_official_api_parser_extracts_act():
    rows = _parse_lom_api_results({
        "response": {"docs": [{
            "nombor_akta": "709",
            "attr_titlebi": "PERSONAL DATA PROTECTION ACT 2010",
            "_os_url": "https://lom.agc.gov.my/act-detail.php?act=709&lang=BI",
        }]},
    })

    assert rows[0]["title"] == "PERSONAL DATA PROTECTION ACT 2010"
    assert rows[0]["external_id"] == "act-709"


@pytest.mark.anyio
async def test_malaysia_official_api_result_is_live(monkeypatch):
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_kwargs: FakeUrlClient({
            "https://lom.agc.gov.my/fess-proxy.php": {
                "response": {"docs": [{
                    "nombor_akta": "709",
                    "attr_titlebi": "PERSONAL DATA PROTECTION ACT 2010",
                    "_os_url": "https://lom.agc.gov.my/act-detail.php?act=709&lang=BI",
                }]},
            },
        }),
    )

    rows = await MalaysiaLomAdapter()._search_queries(["personal data protection"], 5)

    assert rows[0].retrieval_mode == "live"
    assert rows[0].discovery_method == "official_search"


def test_malaysia_title_extraction_skips_site_header_and_accepts_mixed_case():
    title = _extract_lom_title(
        """
        <html>
          <body>
            <h1>Laws of Malaysia</h1>
            <h2>Personal Data Protection Act 2010</h2>
          </body>
        </html>
        """
    )

    assert title == "Personal Data Protection Act 2010"


def test_malaysia_title_extraction_finds_mixed_case_title_text():
    title = _extract_lom_title(
        "<html><body><main>Cyber Security Act 2024 principal text</main></body></html>"
    )

    assert title == "Cyber Security Act 2024"


def test_malaysia_external_id_extracts_act_number():
    assert _malaysia_external_id_from_url(
        "https://lom.agc.gov.my/act-detail.php?act=854&lang=BI&type=principal"
    ) == "act-854"


@pytest.mark.anyio
async def test_malaysia_known_act_stays_fallback_when_verified():
    rows = await _known_act_hits(
        FakeUrlClient({
            "https://lom.agc.gov.my/act-detail.php?act=709&lang=BI&type=principal": (
                "<h1>Laws of Malaysia</h1><h2>Personal Data Protection Act 2010</h2>"
            ),
        }),
        "personal data protection",
    )

    assert rows
    assert rows[0]["title"] == "Personal Data Protection Act 2010"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "not returned by the official search" in rows[0]["warnings"][0]


@pytest.mark.anyio
async def test_malaysia_known_act_keeps_fallback_when_live_verification_fails():
    rows = await _known_act_hits(FailingClient(), "personal data protection")

    assert rows
    assert rows[0]["title"] == "Personal Data Protection Act 2010"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert "could not be verified live" in rows[0]["warnings"][0]


@pytest.mark.anyio
async def test_malaysia_lom_adapter_mock_mode_uses_fixture():
    source = get_sources("MYS")[0]
    rows = await MalaysiaLomAdapter().search(
        country_code="MYS",
        source=source,
        queries=["site:lom.agc.gov.my personal data protection"],
        limit=2,
        browser_mode="mock",
    )

    assert rows
    assert rows[0].source_adapter == "malaysia_lom"
    assert rows[0].retrieval_mode == "fixture"


@pytest.mark.anyio
async def test_malaysia_lom_live_failure_marks_fixture_fallback(monkeypatch):
    adapter = MalaysiaLomAdapter()

    async def fail_search(_queries, _limit):
        raise RuntimeError("lom down")

    monkeypatch.setattr(adapter, "_search_queries", fail_search)
    source = get_sources("MYS")[0]
    rows = await adapter.search(
        country_code="MYS",
        source=source,
        queries=["site:lom.agc.gov.my cyber security act"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("lom down" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_malaysia_lom_empty_live_results_falls_back(monkeypatch):
    adapter = MalaysiaLomAdapter()

    async def empty_search(_queries, _limit):
        return []

    monkeypatch.setattr(adapter, "_search_queries", empty_search)
    source = get_sources("MYS")[0]
    rows = await adapter.search(
        country_code="MYS",
        source=source,
        queries=["site:lom.agc.gov.my cyber security act"],
        limit=2,
        browser_mode="auto",
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("returned no results" in warning for warning in rows[0].warnings)


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


def test_singapore_sso_parser_deduplicates_view_variants():
    rows = _parse_sso_search_results(
        '<a href="/Act/PDPA2012?ViewType=Advance">Personal Data Protection Act 2012</a>'
        '<a href="/Act/PDPA2012?ViewType=Pdf">Personal Data Protection Act 2012</a>'
    )

    assert [row["url"] for row in rows] == ["https://sso.agc.gov.sg/Act/PDPA2012"]


def test_singapore_sso_title_extraction_removes_site_suffix():
    title = _extract_page_title(
        "<title lang='en'>Personal Data Protection Act 2012 - Singapore Statutes Online</title>"
    )

    assert title == "Personal Data Protection Act 2012"


@pytest.mark.anyio
async def test_singapore_known_law_keeps_fallback_when_live_verification_fails():
    rows = await _known_law_hits(FailingClient(), "personal data protection")

    assert rows
    assert rows[0]["title"] == "Personal Data Protection Act 2012"
    assert rows[0]["retrieval_mode"] == "fallback"
    assert any("could not be verified live" in warning for warning in rows[0]["warnings"])


@pytest.mark.anyio
async def test_singapore_later_official_query_beats_known_fallback(monkeypatch):
    first = "https://sso.agc.gov.sg/Search/Content?Phrase=Cybersecurity+Act"
    second = "https://sso.agc.gov.sg/Search/Content?Phrase=cybersecurity+law"
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_kwargs: FakeUrlClient({
            first: '<a href="/Act/CMA1993">Computer Misuse Act 1993</a>',
            second: '<a href="/Act/CA2018">Cybersecurity Act 2018</a>',
        }),
    )

    rows = await SingaporeSsoAdapter()._search_queries(
        ["Cybersecurity Act", "cybersecurity law"],
        limit=2,
    )

    assert rows[0].title == "Cybersecurity Act 2018"
    assert rows[0].retrieval_mode == "live"
    assert rows[0].discovery_method == "official_search"


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


def test_thailand_expands_english_pdpa_query_to_thai_ocs_title():
    queries = _expanded_ocs_queries("personal data protection law")

    assert queries[0] == "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล"
    assert queries[-1] == "personal data protection law"


def test_thailand_external_id_extracts_spa_doc_fragment():
    assert _thailand_external_id_from_url(
        "https://searchlaw.ocs.go.th/council-of-state/#/public/doc/pdpa-2562"
    ) == "pdpa-2562"


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


@pytest.mark.anyio
async def test_thailand_ocs_runs_original_query_after_expanded_title_hit():
    calls: list[str] = []

    async def search(query: str, max_results: int = 10):
        calls.append(query)
        if query == "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล":
            return [{
                "title": "Personal Data Protection Act B.E. 2562",
                "doc_id": "pdpa-2562",
                "doc_url": "https://searchlaw.ocs.go.th/council-of-state/#/public/doc/pdpa-2562",
            }]
        if query == "cross-border transfer":
            return [{
                "title": "Notification on Cross-Border Personal Data Transfers",
                "doc_id": "cross-border-notification",
                "doc_url": "https://searchlaw.ocs.go.th/council-of-state/#/public/doc/cross-border-notification",
            }]
        return []

    rows = await ThailandOcsAdapter()._search_queries(
        search,
        ["site:ocs.go.th cross-border transfer"],
        limit=5,
    )

    assert calls[-1] == "cross-border transfer"
    assert [row.external_id for row in rows] == ["pdpa-2562", "cross-border-notification"]
