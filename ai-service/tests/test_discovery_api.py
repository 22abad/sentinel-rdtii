from __future__ import annotations

from fastapi.testclient import TestClient

from auth import get_current_user
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
    assert any(source["source_type"] == "statute_portal" for source in data["sources"])


def test_discovery_countries_returns_configured_country_metadata():
    client = TestClient(main_module.app)

    response = client.get("/api/discovery/countries")

    assert response.status_code == 200
    countries = response.json()["countries"]
    china = next(country for country in countries if country["country_code"] == "CHN")
    assert china["label"] == "China"
    assert china["source_count"] >= 3
    assert 6 in china["supported_pillars"]


def test_discovery_config_can_be_saved_to_database(monkeypatch):
    from api import discovery as discovery_api

    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "database")
    calls = {}

    def fake_save_registry(registry, *, changed_by=None, change_note=""):
        calls["registry"] = registry
        calls["changed_by"] = changed_by
        calls["change_note"] = change_note
        return registry

    monkeypatch.setattr(discovery_api.discovery_source_persistence, "save_registry", fake_save_registry)
    main_module.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "role": "admin",
    }
    client = TestClient(main_module.app)

    try:
        response = client.put(
            "/api/discovery/config",
            json={
                "registry": {
                    "TST": {
                        "label": "Testland",
                        "languages": ["en"],
                        "sources": [
                            {
                                "name": "Test Statutes",
                                "base_url": "https://laws.example",
                                "domains": ["laws.example"],
                                "adapter": "search_engine",
                                "source_grade": "primary",
                                "source_type": "statute_portal",
                                "languages": ["en"],
                                "pillars": [6],
                                "priority": 100,
                            }
                        ],
                    }
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["registry"]["TST"]["sources"][0]["name"] == "Test Statutes"
        assert calls["changed_by"] == "11111111-1111-1111-1111-111111111111"
        assert calls["change_note"] == "Saved from Discovery Source Manager"
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)


def test_discovery_config_can_be_saved_to_file_backend(tmp_path, monkeypatch):
    registry_file = tmp_path / "sources.yaml"
    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "file")
    monkeypatch.setenv("DISCOVERY_SOURCES_FILE", str(registry_file))
    main_module.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "role": "admin",
    }
    client = TestClient(main_module.app)

    try:
        response = client.put(
            "/api/discovery/config",
            json={
                "registry": {
                    "TST": {
                        "label": "Testland",
                        "languages": ["en"],
                        "sources": [
                            {
                                "name": "Test Statutes",
                                "base_url": "https://laws.example",
                                "domains": ["laws.example"],
                            }
                        ],
                    }
                }
            },
        )

        assert response.status_code == 200
        assert registry_file.exists()
        assert "Test Statutes" in registry_file.read_text()
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)


def test_discovery_config_read_reports_database_unavailable(monkeypatch):
    from api import discovery as discovery_api

    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "database")

    def unavailable():
        raise discovery_api.discovery_source_persistence.DiscoverySourcePersistenceError("missing table")

    monkeypatch.setattr(discovery_api, "get_registry", unavailable)
    client = TestClient(main_module.app)

    response = client.get("/api/discovery/config")

    assert response.status_code == 503
    assert "missing table" in response.json()["detail"]


def test_discovery_config_save_rejects_unknown_backend(monkeypatch):
    from api import discovery as discovery_api

    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "redis")
    calls = {"save_registry": 0}

    def fake_save_registry(*args, **kwargs):
        calls["save_registry"] += 1
        return {}

    monkeypatch.setattr(discovery_api.discovery_source_persistence, "save_registry", fake_save_registry)
    main_module.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "role": "admin",
    }
    client = TestClient(main_module.app)

    try:
        response = client.put(
            "/api/discovery/config",
            json={"registry": {"TST": {"label": "Testland", "sources": []}}},
        )

        assert response.status_code == 503
        assert "Unsupported DISCOVERY_REGISTRY_BACKEND: redis" in response.json()["detail"]
        assert calls["save_registry"] == 0
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)


def test_discovery_config_save_rejects_invalid_config_indicator(monkeypatch):
    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "database")
    main_module.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "role": "admin",
    }
    client = TestClient(main_module.app)

    try:
        response = client.put(
            "/api/discovery/config",
            json={
                "registry": {
                    "TST": {
                        "label": "Testland",
                        "languages": ["en"],
                        "sources": [
                            {
                                "name": "Bad Indicator Source",
                                "base_url": "https://laws.example",
                                "domains": ["laws.example"],
                                "indicators": ["oops"],
                            }
                        ],
                    }
                }
            },
        )
        assert response.status_code == 422
        assert "unsupported source indicator" in response.json()["detail"]
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)


def test_discovery_config_save_rejects_too_long_country_code(monkeypatch):
    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "database")
    main_module.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "role": "admin",
    }
    client = TestClient(main_module.app)

    try:
        response = client.put(
            "/api/discovery/config",
            json={"registry": {"TOOLONG": {"label": "Badland", "sources": []}}},
        )
        assert response.status_code == 422
        assert "Country code must be 3 characters or fewer" in response.json()["detail"]
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)


def test_discovery_config_can_be_saved_by_viewer_role(monkeypatch):
    from api import discovery as discovery_api

    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "database")
    calls = {}

    def fake_save_registry(registry, *, changed_by=None, change_note=""):
        calls["registry"] = registry
        calls["changed_by"] = changed_by
        calls["change_note"] = change_note
        return registry

    monkeypatch.setattr(discovery_api.discovery_source_persistence, "save_registry", fake_save_registry)
    main_module.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test-viewer",
        "role": "viewer",
    }
    client = TestClient(main_module.app)

    try:
        response = client.put(
            "/api/discovery/config",
            json={"registry": {"TST": {"label": "Testland", "sources": []}}},
        )
        assert response.status_code == 200
        assert response.json()["registry"]["TST"]["label"] == "Testland"
        assert calls["changed_by"] == "test-viewer"
    finally:
        main_module.app.dependency_overrides.pop(get_current_user, None)


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
