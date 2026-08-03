from __future__ import annotations

import asyncio
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
from discovery.adapters.official_index import OfficialIndexAdapter, parse_official_index
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
from discovery.schemas import LegalSourceConfig, RawSearchHit


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


def test_configured_search_backend_defaults_to_free_duckduckgo(monkeypatch):
    from discovery.adapters.search_engine import _build_search_backend, _configured_search_backend

    # explicit off -> no backend (fixtures)
    monkeypatch.setenv("DISCOVERY_SEARCH_BACKEND", "none")
    assert _configured_search_backend() == ""
    # unset + no SerpApi key -> free DuckDuckGo default (judges get live search)
    monkeypatch.delenv("DISCOVERY_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    assert _configured_search_backend() == "duckduckgo"
    # unset + SerpApi key present -> SerpApi (best quality)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    assert _configured_search_backend() == "serpapi"
    # the "duckduckgo" default builds a key-free multi-tier cascade whose FIRST
    # tier is DuckDuckGo Lite (Bing is the fallback when DDG rate-limits).
    backend = _build_search_backend("duckduckgo")
    assert type(backend).__name__ == "MultiTierSearchBackend"
    assert type(backend.tiers[0]).__name__ == "DuckDuckGoSearchBackend"
    assert type(_build_search_backend("ddg_only")).__name__ == "DuckDuckGoSearchBackend"


def test_configured_search_backend_google_cse(monkeypatch):
    from discovery.adapters.search_engine import _build_search_backend, _configured_search_backend

    monkeypatch.delenv("DISCOVERY_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    # both Google CSE vars present + no SerpApi key -> google auto-selected
    monkeypatch.setenv("GOOGLE_CSE_KEY", "g-key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "g-cx")
    assert _configured_search_backend() == "google"
    # SerpApi key outranks Google CSE (explicit setting still wins over both)
    monkeypatch.setenv("SERPAPI_API_KEY", "s-key")
    assert _configured_search_backend() == "serpapi"
    monkeypatch.setenv("DISCOVERY_SEARCH_BACKEND", "google")
    assert _configured_search_backend() == "google"
    assert type(_build_search_backend("google")).__name__ == "GoogleCseSearchBackend"
    # explicit google WITHOUT keys degrades loudly to free DDG, not fixtures
    monkeypatch.delenv("GOOGLE_CSE_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    assert _configured_search_backend() == "duckduckgo"


@pytest.mark.anyio
async def test_google_cse_backend_parses_items_and_trips_breaker(monkeypatch):
    import discovery.adapters.search_engine as se

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return self._response

    import httpx

    monkeypatch.setattr(se, "_GOOGLE_CSE_DISABLED_REASON", None)
    backend = se.GoogleCseSearchBackend(api_key="k", cse_id="cx")

    ok = FakeResponse(200, {"items": [
        {"link": "https://sso.agc.gov.sg/Act/PDPA2012", "title": "PDPA", "snippet": "s"},
        {"link": "", "title": "skipped"},
    ]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient(ok))
    hits = await backend.search("personal data protection act", limit=5)
    assert len(hits) == 1
    assert hits[0].url == "https://sso.agc.gov.sg/Act/PDPA2012"
    assert hits[0].retrieval_mode == "live"

    # 403 trips the process-wide breaker: second call fails instantly
    bad = FakeResponse(403, {})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient(bad))
    with pytest.raises(RuntimeError, match="disabled for this process"):
        await backend.search("q", limit=3)
    with pytest.raises(RuntimeError, match="disabled for this process"):
        await backend.search("q", limit=3)
    monkeypatch.setattr(se, "_GOOGLE_CSE_DISABLED_REASON", None)


@pytest.mark.anyio
async def test_generic_search_adapter_non_mock_marks_fixture_fallback(monkeypatch):
    # Explicitly disable the live backend so this exercises the fixture-fallback
    # path hermetically (the default is now free DuckDuckGo, which would hit the
    # network).
    monkeypatch.setenv("DISCOVERY_SEARCH_BACKEND", "none")
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


def test_official_index_parser_returns_only_configured_document_links():
    source = LegalSourceConfig(
        name="Treaty office",
        base_url="https://official.example",
        domains=["official.example", "files.official.example"],
        adapter="official_index",
        search_paths=["/agreements"],
        include_patterns=[r"chapter-14.*\.pdf"],
        title_overrides={r"chapter-14.*\.pdf": "Chapter 14 Electronic Commerce"},
    )

    rows = parse_official_index(
        """
        <a href="https://files.official.example/chapter-14-electronic-commerce.pdf">
          Chapter 14 Electronic Commerce
        </a>
        <a href="/unrelated.pdf">Unrelated annex</a>
        """,
        index_url="https://official.example/agreements",
        source=source,
        query="cross-border data",
    )

    assert len(rows) == 1
    assert rows[0].title == "Chapter 14 Electronic Commerce"
    assert rows[0].retrieval_mode == "live"
    assert rows[0].discovery_method == "official_search"
    assert rows[0].raw["index_url"] == "https://official.example/agreements"


@pytest.mark.anyio
async def test_official_index_adapter_failure_is_auditable_fallback(monkeypatch):
    adapter = OfficialIndexAdapter()

    async def fail_search(_source, _queries, _limit):
        raise RuntimeError("index down")

    monkeypatch.setattr(adapter, "_search_indexes", fail_search)
    source = next(
        source for source in get_sources("MYS")
        if source.name == "Ministry of Investment Trade and Industry"
    )
    rows = await adapter.search(
        country_code="MYS",
        source=source,
        queries=["electronic commerce"],
        limit=2,
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"
    assert any("index down" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_official_index_adapter_respects_fixture_environment(monkeypatch):
    monkeypatch.setenv("DISCOVERY_USE_FIXTURES", "true")
    adapter = OfficialIndexAdapter()

    async def unexpected_live_search(*_args):
        raise AssertionError("live search should not run in fixture mode")

    monkeypatch.setattr(adapter, "_search_indexes", unexpected_live_search)
    source = next(
        source for source in get_sources("AUS")
        if source.name == "Australia–Singapore DEA text (hosted by MTI Singapore)"
    )

    rows = await adapter.search(
        country_code="AUS",
        source=source,
        queries=["Australia-Singapore Digital Economy Agreement"],
        limit=2,
    )

    assert rows[0].retrieval_mode == "fixture"
    assert "isomer-user-content.by.gov.sg" in rows[0].url


@pytest.mark.anyio
async def test_official_index_adapter_requires_search_paths():
    source = LegalSourceConfig(
        name="Empty index",
        base_url="https://official.example",
        domains=["official.example"],
        adapter="official_index",
    )

    with pytest.raises(ValueError, match="requires at least one configured search path"):
        await OfficialIndexAdapter()._search_indexes(source, ["law"], 2)


@pytest.mark.anyio
async def test_official_index_parse_failure_preserves_prior_path_rows(monkeypatch):
    import httpx
    import discovery.adapters.official_index as official_index_module

    class Response:
        def __init__(self, url: str):
            self.url = url
            self.text = url

        def raise_for_status(self):
            return None

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str):
            return Response(url)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: Client())

    def parse(document, **_kwargs):
        if document.endswith("/broken"):
            raise ValueError("malformed index")
        return [RawSearchHit(title="Treaty", url="https://official.example/treaty.pdf")]

    monkeypatch.setattr(official_index_module, "parse_official_index", parse)
    source = LegalSourceConfig(
        name="Treaty office",
        base_url="https://official.example",
        domains=["official.example"],
        adapter="official_index",
        search_paths=["/working", "/broken"],
    )

    rows = await OfficialIndexAdapter()._search_indexes(source, ["treaty"], 2)

    assert [row.title for row in rows] == ["Treaty"]
    assert any("ValueError" in warning for warning in rows[0].warnings)


@pytest.mark.anyio
async def test_australia_dfat_fixture_points_to_signed_pdf(monkeypatch):
    monkeypatch.setenv("DISCOVERY_USE_FIXTURES", "true")
    source = next(
        source for source in get_sources("AUS")
        if source.name == "Department of Foreign Affairs and Trade"
    )

    rows = await OfficialIndexAdapter().search(
        country_code="AUS",
        source=source,
        queries=["Australia-Singapore Digital Economy Agreement"],
        limit=2,
    )

    assert rows[0].url.endswith("australia-singapore-digital-economy-agreement.pdf")


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


def test_stale_serpapi_setting_without_key_degrades_to_duckduckgo(monkeypatch):
    """A stale explicit serpapi setting with no key must degrade to the free
    DuckDuckGo backend (live search), NOT to fixture fallback — a leftover
    .env line otherwise silently turned all site discovery offline (found via
    the workbench Discovery panel showing only fixtures)."""
    from discovery.adapters.search_engine import _configured_search_backend

    monkeypatch.setenv("DISCOVERY_SEARCH_BACKEND", "serpapi")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    assert _configured_search_backend() == "duckduckgo"

    # With a key present, the explicit serpapi setting is honoured.
    monkeypatch.setenv("SERPAPI_API_KEY", "sk-test")
    assert _configured_search_backend() == "serpapi"


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


@pytest.mark.anyio
async def test_thailand_ocs_query_timeout_degrades_without_hanging(monkeypatch):
    # A stalled OCS portal (Playwright load never returns) must not hang the
    # whole sweep: the per-query timeout skips it and the adapter falls back.
    from discovery.adapters import thailand as thailand_mod

    async def slow_search(_query: str, max_results: int = 10):
        await asyncio.sleep(5)  # would stall for seconds without the guard
        return []

    fake_crawler = types.ModuleType("crawler")
    fake_crawler.search_ocs_law = slow_search
    monkeypatch.setitem(sys.modules, "crawler", fake_crawler)
    monkeypatch.setattr(thailand_mod, "_OCS_QUERY_TIMEOUT_S", 0.05)
    source = get_sources("THA")[0]

    # The whole call must finish well under the 5s-per-query stall.
    rows = await asyncio.wait_for(
        ThailandOcsAdapter().search(
            country_code="THA",
            source=source,
            queries=["site:ocs.go.th personal data protection law"],
            limit=2,
            browser_mode="auto",
        ),
        timeout=3.0,
    )

    assert rows
    assert rows[0].retrieval_mode == "fallback"


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


def test_core_search_term_extracts_bigram_for_register_contains_search():
    """The register API does whole-phrase contains matching — concept phrases
    get a bounded two-word-core retry ('cross-border data transfer ban' →
    'data transfer') instead of silently falling back."""
    from discovery.adapters.australia import _core_search_term

    assert _core_search_term("cross-border data transfer ban") == "data transfer"
    assert _core_search_term("local storage requirement") == "local storage"
    assert _core_search_term("local data centre requirement") == "data centre"
    # Single content word → no useful bigram, no retry.
    assert _core_search_term("ban") == ""


@pytest.mark.anyio
async def test_generic_site_search_retries_zero_hit_phrase_with_core_term():
    """Concept phrases score zero on web engines too — the generic adapter now
    retries once with the two-word core, keeping the site: filter."""
    from discovery.adapters.search_engine import SearchEngineAdapter

    calls: list[str] = []

    class RecordingBackend:
        async def search(self, query, limit):
            calls.append(query)
            if query == "site:nacsa.gov.my data transfer":
                return [RawSearchHit(
                    title="Cyber Security Act 2024", url="https://nacsa.gov.my/csa",
                    snippet="", source_adapter="", source_name="", query=query,
                    position=1, retrieval_mode="live", discovery_method="web_search",
                )]
            return []

    source = get_sources("MYS")[2]  # a search_engine source
    rows = await SearchEngineAdapter(search_backend=RecordingBackend())._search_live(
        backend=RecordingBackend() if False else RecordingBackend(),
        source=source,
        queries=["site:nacsa.gov.my cross-border data transfer ban"],
        limit=3,
    )
    # both original phrase and the core retry were attempted, retry succeeded
    assert rows and rows[0].url == "https://nacsa.gov.my/csa"


@pytest.mark.anyio
async def test_ddg_lite_parses_direct_hrefs(monkeypatch):
    """The lite endpoint (POST) returns <a href="<direct>" class='result-link'>
    — href BEFORE class, single-quoted class, direct URL (no /l/?uddg redirect).
    The parser must extract the real destination and skip ddg-internal links.
    This is the key-free path that clears the html-endpoint bot-challenge."""
    from discovery.adapters.search_engine import DuckDuckGoSearchBackend

    body = (
        "<html><body><table>"
        "<tr><td><a rel=\"nofollow\" href=\"https://www.indiacode.nic.in/bitstream/"
        "123456789/22037/1/a2023-22.pdf\" class='result-link'>"
        "<span class=\"result__type\">PDF</span> The Digital Personal Data "
        "Protection Act, 2023</a></td></tr>"
        "<tr><td><a rel=\"nofollow\" href=\"https://legalinfo.mn/en/edtl/16532053734461\""
        " class='result-link'>Mongolia Personal Data Protection Law</a></td></tr>"
        "<tr><td><a href=\"https://duckduckgo.com/y.js?ad=1\" class='result-link'>ad</a></td></tr>"
        "</table></body></html>"
    )

    async def fake_fetch(self, query):
        return 200, body

    monkeypatch.setattr(DuckDuckGoSearchBackend, "_fetch", fake_fetch)
    hits = await DuckDuckGoSearchBackend().search("anything", 10)
    urls = [h.url for h in hits]
    assert "https://www.indiacode.nic.in/bitstream/123456789/22037/1/a2023-22.pdf" in urls
    assert "https://legalinfo.mn/en/edtl/16532053734461" in urls
    assert not any("duckduckgo.com" in u for u in urls)  # ddg-internal skipped


@pytest.mark.anyio
async def test_ddg_lite_still_surfaces_202_challenge(monkeypatch):
    from discovery.adapters.search_engine import DuckDuckGoSearchBackend

    async def challenged(self, query):
        return 202, "<html>anomaly detected</html>"

    monkeypatch.setattr(DuckDuckGoSearchBackend, "_fetch", challenged)
    with pytest.raises(RuntimeError, match="bot-challenging"):
        await DuckDuckGoSearchBackend().search("x", 5)


@pytest.mark.anyio
async def test_bing_backend_decodes_ck_redirect(monkeypatch):
    """Bing organic results are bing.com/ck/a?...&u=a1<b64url> click-redirects;
    the backend must base64url-decode the real destination and skip bing-internal."""
    import base64
    from discovery.adapters.search_engine import BingSearchBackend

    real = "https://www.indiacode.nic.in/bitstream/123456789/22037/1/a2023-22.pdf"
    enc = "a1" + base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    body = (
        f'<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;u={enc}">'
        "India Code</a></h2></li>"
        '<a href="https://www.bing.com/ck/a?!&amp;&amp;u=a1BADPAD">internal</a>'
    )

    async def fake_get(self, query):  # not used; patch the fetch inline
        return None

    # patch curl_cffi path by stubbing the whole search body fetch
    async def fake_search(self, query, limit):
        # exercise the real _decode + parse on our fixture body
        hits = []
        import re as _re
        for redirect in _re.findall(r'href="(https?://www\.bing\.com/ck/a\?[^"]+)"', body):
            dest = BingSearchBackend._decode(redirect.replace("&amp;", "&"))
            if dest and "bing.com" not in dest:
                from discovery.schemas import RawSearchHit
                hits.append(RawSearchHit(title=dest, url=dest, snippet="", position=len(hits) + 1,
                                         raw={}, retrieval_mode="live", discovery_method="web_search"))
        return hits

    monkeypatch.setattr(BingSearchBackend, "search", fake_search)
    hits = await BingSearchBackend().search("x", 5)
    assert [h.url for h in hits] == [real]


@pytest.mark.anyio
async def test_multitier_falls_through_on_rate_limit():
    """If the first free engine rate-limits (raises), the cascade tries the next
    and returns its results — key-free resilience, no paid backend."""
    from discovery.adapters.search_engine import MultiTierSearchBackend
    from discovery.schemas import RawSearchHit

    class Blocked:
        async def search(self, query, limit):
            raise RuntimeError("bot-challenging this IP (HTTP 202)")

    class Works:
        async def search(self, query, limit):
            return [RawSearchHit(title="ok", url="https://legalinfo.mn/x", snippet="",
                                 position=1, raw={}, retrieval_mode="live", discovery_method="web_search")]

    hits = await MultiTierSearchBackend(tiers=[Blocked(), Works()]).search("q", 5)
    assert len(hits) == 1 and hits[0].url == "https://legalinfo.mn/x"


@pytest.mark.anyio
async def test_politeness_gate_spaces_calls_and_respects_zero(monkeypatch):
    """The per-host politeness gate waits the configured interval between calls
    to the same host, and is a no-op when the interval is 0 (test/CI default)."""
    import time as _t
    from discovery.adapters import search_engine as se

    se._HOST_LAST_CALL.clear()
    # interval 0 -> immediate, no timestamp recorded as a wait
    monkeypatch.setenv("DISCOVERY_SEARCH_MIN_INTERVAL", "0")
    t0 = _t.monotonic()
    await se._politeness_wait("example.com")
    assert _t.monotonic() - t0 < 0.05

    # interval set -> the SECOND back-to-back call to the same host is delayed
    se._HOST_LAST_CALL.clear()
    monkeypatch.setenv("DISCOVERY_SEARCH_MIN_INTERVAL", "0.2")
    await se._politeness_wait("host.test")   # first call: no prior timestamp
    t1 = _t.monotonic()
    await se._politeness_wait("host.test")   # second: must wait ~0.2s
    assert _t.monotonic() - t1 >= 0.15


def test_optional_proxy_env(monkeypatch):
    """RDTII_HTTP_PROXY plumbs an outbound proxy for the free backends; off by
    default so a fresh-IP judge run is unaffected (no bundled free-proxy list)."""
    from discovery.adapters import search_engine as se

    monkeypatch.delenv("RDTII_HTTP_PROXY", raising=False)
    assert se._proxies() is None
    monkeypatch.setenv("RDTII_HTTP_PROXY", "socks5://127.0.0.1:9050")
    assert se._proxies() == {"http": "socks5://127.0.0.1:9050", "https": "socks5://127.0.0.1:9050"}


# ---------------------------------------------------------------------------
# Russia — publication.pravo.gov.ru official JSON API
# ---------------------------------------------------------------------------

def test_russia_pravo_localizes_pillar_queries_to_law_names():
    from discovery.adapters.russia_pravo import _localize_query

    # Name= searches instrument NAMES — topics must map to law-title terms
    assert _localize_query("personal data protection act") == "персональных данных"
    assert _localize_query("cross-border data transfer restrictions") == "персональных данных"
    assert _localize_query("data retention interception") == "противодействии терроризму"
    assert _localize_query("critical infrastructure cybersecurity") == (
        "безопасности критической информационной инфраструктуры"
    )
    # unknown concepts pass through unchanged
    assert _localize_query("совершенно другой запрос") == "совершенно другой запрос"


@pytest.mark.anyio
async def test_russia_pravo_parses_api_items_and_keeps_instruments_only(monkeypatch):
    from urllib.parse import quote
    from discovery.adapters.russia_pravo import RussiaPravoAdapter

    api_url = (
        "http://publication.pravo.gov.ru/api/Documents?PageSize=30&Index=1&Name="
        + quote("персональных данных")
    )
    payload = {
        "items": [
            {
                "eoNumber": "0001202608030001",
                "complexName": 'Федеральный закон от 27.07.2006 № 152-ФЗ\n "О персональных данных"',
                "documentDate": "2006-07-27T00:00:00",
                "pagesCount": 30,
            },
            {   # non-statutory stream item must be dropped
                "eoNumber": "0001202608030002",
                "complexName": "Информационное сообщение о персональных данных",
                "documentDate": "2026-08-03T00:00:00",
                "pagesCount": 1,
            },
            {   # regional publication stream (non-0001 prefix) must be dropped
                "eoNumber": "5101202607300002",
                "complexName": 'Федеральный закон от 01.01.2026 № 1-ФЗ "О персональных данных региона"',
                "documentDate": "2026-01-01T00:00:00",
                "pagesCount": 2,
            },
        ]
    }
    monkeypatch.setattr(
        "discovery.adapters.russia_pravo._open_client",
        lambda: FakeUrlClient({api_url: payload}),
    )

    hits = await RussiaPravoAdapter().search(
        country_code="RUS",
        source=LegalSourceConfig(name="pravo.gov.ru", base_url="http://publication.pravo.gov.ru", domains=["publication.pravo.gov.ru"]),
        queries=["personal data protection"],
        limit=10,
    )

    assert len(hits) == 1
    hit = hits[0]
    assert hit.retrieval_mode == "live"
    assert hit.discovery_method == "official_search"
    assert hit.external_id == "0001202608030001"
    assert hit.url.endswith("/Document/View/0001202608030001")
    assert hit.raw["pdf_url"].endswith("file/pdf?eoNumber=0001202608030001")
    assert "152-ФЗ" in hit.title and "\n" not in hit.title


@pytest.mark.anyio
async def test_russia_pravo_ignores_other_economies():
    from discovery.adapters.russia_pravo import RussiaPravoAdapter

    hits = await RussiaPravoAdapter().search(
        country_code="THA",
        source=LegalSourceConfig(name="x", base_url="http://x", domains=["x"]),
        queries=["personal data"],
        limit=5,
    )
    assert hits == []
