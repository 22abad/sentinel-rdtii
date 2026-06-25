from __future__ import annotations

import pytest

from discovery.adapters.china import ChinaFlkAdapter, _external_id_from_url
from discovery.adapters.thailand import ThailandOcsAdapter
from discovery.registry import get_sources


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
