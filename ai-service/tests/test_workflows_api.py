from __future__ import annotations

from fastapi.testclient import TestClient

import main as main_module


def test_workflow_node_types_exposes_phase_zero_nodes():
    client = TestClient(main_module.app)

    response = client.get("/api/workflows/node-types")

    assert response.status_code == 200
    node_types = {item["type"]: item for item in response.json()["node_types"]}
    assert "discovery.search" in node_types
    assert "source.fetch_text" in node_types
    assert "extract.mappings" in node_types
    assert "rag.query" in node_types
    assert node_types["extract.mappings"]["supports_streaming"] is True
    assert "provider" not in node_types["rag.query"]["config_schema"]["properties"]


def test_workflow_unknown_node_type_returns_404():
    client = TestClient(main_module.app)

    response = client.post("/api/workflows/nodes/nope.run/run", json={})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_node_type"


def test_workflow_run_maps_extraction_error_to_503(monkeypatch):
    from providers.base import ExtractionError
    from workflows.schemas import NodeResult

    class FailingExecutor:
        async def run(self, *, node, inputs, context) -> NodeResult:
            raise ExtractionError("provider unavailable")

    import api.workflows as workflow_api

    monkeypatch.setattr(workflow_api, "get_executor", lambda _node_type: FailingExecutor())
    client = TestClient(main_module.app)

    response = client.post("/api/workflows/nodes/extract.mappings/run", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "provider unavailable"


def test_workflow_discovery_node_runs_with_mock_browser_mode():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/workflows/nodes/discovery.search/run",
        json={
            "node_id": "discovery-1",
            "config": {
                "country_code": "SGP",
                "pillars": [6, 7],
                "browser_mode": "mock",
                "limit": 5,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "discovery-1"
    assert data["status"] == "success"
    assert data["outputs"]["country_code"] == "SGP"
    assert data["outputs"]["candidates"]


def test_workflow_discovery_node_validation_error_returns_422():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/workflows/nodes/discovery.search/run",
        json={
            "config": {
                "country_code": "SGP",
                "pillars": [1],
            },
        },
    )

    assert response.status_code == 422


def test_workflow_discovery_node_unknown_country_returns_404():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/workflows/nodes/discovery.search/run",
        json={
            "config": {
                "country_code": "ZZZ",
                "pillars": [6],
                "browser_mode": "mock",
            },
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No discovery sources configured for ZZZ."


def test_workflow_fetch_text_node_uses_document_fetch_helper(monkeypatch):
    from services.document_fetch import DocumentText
    from workflows.nodes import fetch_text as fetch_node

    async def fake_fetch_document_text(source_url: str, browser_mode: str = "auto") -> DocumentText:
        return DocumentText(
            source_url=source_url,
            text=f"Fetched with {browser_mode}",
            content_type="text",
        )

    monkeypatch.setattr(fetch_node, "fetch_document_text", fake_fetch_document_text)
    client = TestClient(main_module.app)

    response = client.post(
        "/api/workflows/nodes/source.fetch_text/run",
        json={
            "node_id": "fetch-1",
            "inputs": {"candidate": {"url": "https://example.test/law"}},
            "config": {"browser_mode": "mock"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "fetch-1"
    assert data["outputs"]["document"]["source_url"] == "https://example.test/law"
    assert data["outputs"]["document"]["text"] == "Fetched with mock"


def test_workflow_stream_endpoint_wraps_default_executor_events():
    client = TestClient(main_module.app)

    with client.stream(
        "POST",
        "/api/workflows/nodes/discovery.search/run/stream",
        json={
            "node_id": "discovery-stream-1",
            "config": {
                "country_code": "SGP",
                "pillars": [6],
                "browser_mode": "mock",
                "limit": 2,
            },
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: node_started" in body
    assert "event: node_output" in body
    assert '"node_id": "discovery-stream-1"' in body


def test_extract_stream_emits_terminal_node_output(monkeypatch):
    from workflows.nodes import extract as extract_node

    class FakeProvider:
        name = "fake-provider"

    async def fake_stream_extraction(text, provider, pdf_metadata=None):
        yield 'event: started\ndata: {"source_text": "hello law"}\n\n'
        yield 'event: mapping\ndata: {"indicator": "6.1"}\n\n'
        yield 'event: rejected\ndata: {"reason": "bad quote"}\n\n'
        yield 'event: done\ndata: {"mappings_count": 1, "rejected_count": 1, "provider": "fake-provider"}\n\n'

    monkeypatch.setattr(extract_node, "configured_provider", lambda *_args: FakeProvider())
    monkeypatch.setattr(extract_node, "stream_extraction", fake_stream_extraction)
    client = TestClient(main_module.app)

    with client.stream(
        "POST",
        "/api/workflows/nodes/extract.mappings/run/stream",
        json={
            "node_id": "extract-stream-1",
            "inputs": {"text": "hello law"},
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: mapping" in body
    assert "event: rejected" in body
    assert "event: done" in body
    assert "event: node_output" in body
    assert '"mappings": [{"indicator": "6.1"}]' in body
    assert '"rejected": [{"reason": "bad quote"}]' in body
