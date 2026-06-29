from __future__ import annotations

from workflows.nodes import (
    DiscoverySearchExecutor,
    ExtractMappingsExecutor,
    FetchTextExecutor,
    NodeExecutor,
    RagQueryExecutor,
)
from workflows.schemas import NodeTypeDefinition, NodeTypeUi, PortDefinition


_NODE_TYPES: dict[str, NodeTypeDefinition] = {
    "discovery.search": NodeTypeDefinition(
        type="discovery.search",
        label="Discovery",
        category="source",
        description="Find candidate legal sources for a country and RDTII indicators.",
        outputs={"candidates": PortDefinition(type="LegalCandidate[]")},
        config_schema={
            "type": "object",
            "required": ["country_code"],
            "properties": {
                "country_code": {"type": "string"},
                "pillars": {"type": "array", "items": {"type": "integer"}},
                "indicators": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "string"},
                "source_mode": {"type": "string"},
                "browser_mode": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
        ui=NodeTypeUi(icon="search", color="#0f766e", default_width=800),
    ),
    "source.fetch_text": NodeTypeDefinition(
        type="source.fetch_text",
        label="Fetch Text",
        category="source",
        description="Fetch a URL, PDF, or DOCX candidate into normalized text.",
        inputs={
            "candidate": PortDefinition(type="LegalCandidate", required=False),
            "source_url": PortDefinition(type="string", required=False),
        },
        outputs={"document": PortDefinition(type="DocumentText")},
        config_schema={
            "type": "object",
            "properties": {
                "source_url": {"type": "string"},
                "browser_mode": {"type": "string", "default": "auto"},
            },
        },
        ui=NodeTypeUi(icon="file-text", color="#2563eb", default_width=460),
    ),
    "extract.mappings": NodeTypeDefinition(
        type="extract.mappings",
        label="Extract Mappings",
        category="ai",
        description="Extract RDTII indicator mappings from document text.",
        inputs={"document": PortDefinition(type="DocumentText", required=False)},
        outputs={
            "mappings": PortDefinition(type="IndicatorMapping[]"),
            "rejected": PortDefinition(type="RejectedExtraction[]"),
            "source_text": PortDefinition(type="string"),
        },
        config_schema={
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "source_url": {"type": "string"},
                "browser_mode": {"type": "string", "default": "auto"},
            },
        },
        ui=NodeTypeUi(icon="sparkles", color="#7c3aed", default_width=520),
        supports_streaming=True,
    ),
    "rag.query": NodeTypeDefinition(
        type="rag.query",
        label="RAG Query",
        category="ai",
        description="Ask a grounded question over source text, mappings, or notes.",
        inputs={
            "source_text": PortDefinition(type="string", required=False),
            "document": PortDefinition(type="DocumentText", required=False),
        },
        outputs={
            "answer": PortDefinition(type="string"),
            "provider": PortDefinition(type="string"),
        },
        config_schema={
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string"},
                "role": {"type": "string"},
                "context": {"type": "string"},
                "country_code": {"type": "string"},
            },
        },
        ui=NodeTypeUi(icon="message-square", color="#9333ea", default_width=460),
        supports_streaming=True,
    ),
}


_EXECUTOR_CLASSES: dict[str, type[NodeExecutor]] = {
    "discovery.search": DiscoverySearchExecutor,
    "source.fetch_text": FetchTextExecutor,
    "extract.mappings": ExtractMappingsExecutor,
    "rag.query": RagQueryExecutor,
}


def list_node_types() -> list[NodeTypeDefinition]:
    return list(_NODE_TYPES.values())


def get_node_type(node_type: str) -> NodeTypeDefinition | None:
    return _NODE_TYPES.get(node_type)


def get_executor(node_type: str) -> NodeExecutor:
    executor_class = _EXECUTOR_CLASSES.get(node_type)
    if executor_class is None:
        raise KeyError(node_type)
    return executor_class()
