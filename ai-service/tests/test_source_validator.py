from __future__ import annotations

from source_validator import grade_source


def test_discovery_registry_primary_domains_are_authoritative():
    urls = [
        "https://flk.npc.gov.cn/detail2.html?id=pipl",
        "https://www.cac.gov.cn/2022-07/07/c_1658811536396503.htm",
        "https://searchlaw.ocs.go.th/council-of-state/#/public/doc/123",
        "https://www.ocs.go.th/searchlaw",
        "https://www.etda.or.th/th/laws",
        "https://www.pdpc.or.th/laws",
    ]

    for url in urls:
      result = grade_source(url=url, title="Personal Data Protection Act")
      assert result["grade"] == "primary", url
      assert result["is_primary"] is True, url


def test_source_validator_uses_host_not_path_for_official_domains():
    result = grade_source(
        url="https://example.test/redirect/sso.agc.gov.sg",
        title="Random page",
    )

    assert result["grade"] != "primary"
    assert result["is_primary"] is False


def test_source_validator_marks_known_secondary_domain():
    result = grade_source(
        url="https://www.lexology.com/library/detail.aspx?g=example",
        title="Commentary on Personal Data Protection Act",
    )

    assert result["grade"] == "secondary"
    assert result["is_primary"] is False
