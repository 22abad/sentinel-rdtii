from __future__ import annotations

from fastapi.testclient import TestClient

import main as main_module


def test_discovery_search_returns_ranked_candidates():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/discovery/search",
        json={
            "country_code": "SGP",
            "pillars": [6, 7],
            "limit": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["country_code"] == "SGP"
    assert data["queries"]
    assert data["diagnostics"]["mode"] == "auto_with_adapter_fallbacks"
    assert data["diagnostics"]["raw_hits"] >= len(data["candidates"])
    assert "filtered_low_relevance" in data["diagnostics"]
    assert data["candidates"]
    scores = [candidate["rank_score"] for candidate in data["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert all(candidate["url"] for candidate in data["candidates"])
    assert all(candidate["source_grade"] for candidate in data["candidates"])


def test_discovery_sources_returns_registry_entries():
    client = TestClient(main_module.app)

    response = client.get("/api/discovery/sources/CHN")

    assert response.status_code == 200
    data = response.json()
    assert data["country_code"] == "CHN"
    assert any(source["adapter"] == "china_flk" for source in data["sources"])


def test_discovery_official_first_does_not_emit_fake_secondary_leads():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/discovery/search",
        json={
            "country_code": "SGP",
            "pillars": [6, 7],
            "source_mode": "official_first",
            "include_secondary_leads": True,
            "browser_mode": "mock",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["diagnostics"]["source_mode"] == "official_first"
    assert all("example-secondary.test" not in candidate["url"] for candidate in data["candidates"])


def test_discovery_mock_does_not_emit_known_dead_imda_fixture():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/discovery/search",
        json={
            "country_code": "SGP",
            "pillars": [7],
            "browser_mode": "mock",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert all("imda.gov.sg/regulations-and-licensing-listing/telecommunications/codes-of-practice" not in candidate["url"] for candidate in data["candidates"])


def test_discovery_language_filter_skips_non_matching_sources():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/discovery/search",
        json={
            "country_code": "CHN",
            "pillars": [6],
            "languages": ["en"],
            "browser_mode": "mock",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["diagnostics"]["languages"] == ["en"]
    assert any("National Laws and Regulations Database" in item for item in data["diagnostics"]["sources_skipped"])
    assert any("Cyberspace Administration of China" in item for item in data["diagnostics"]["sources_skipped"])
    assert all(candidate["source_name"] == "State Council" for candidate in data["candidates"])


def test_discovery_search_unknown_country_returns_404():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/discovery/search",
        json={"country_code": "ZZZ", "pillars": [6]},
    )

    assert response.status_code == 404


def test_discovery_rejects_unsupported_pillar():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/discovery/search",
        json={"country_code": "SGP", "pillars": [1]},
    )

    assert response.status_code == 422
