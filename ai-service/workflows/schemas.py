from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class PortDefinition(BaseModel):
    type: str
    required: bool = False
    description: str = ""


class NodeTypeUi(BaseModel):
    icon: str = ""
    color: str = ""
    default_width: int | None = None


class NodeTypeDefinition(BaseModel):
    type: str
    label: str
    category: str
    description: str
    inputs: dict[str, PortDefinition] = Field(default_factory=dict)
    outputs: dict[str, PortDefinition] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    ui: NodeTypeUi = Field(default_factory=NodeTypeUi)
    supports_streaming: bool = False


class NodeUiState(BaseModel):
    position: dict[str, float] = Field(default_factory=dict)
    width: int | None = None
    height: int | None = None
    collapsed: bool = False


class WorkflowNode(BaseModel):
    id: str
    type: str
    label: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    ui: NodeUiState = Field(default_factory=NodeUiState)


class WorkflowContext(BaseModel):
    workflow_id: str | None = None
    run_id: str | None = None
    user_id: str | None = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class WorkflowArtifact(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NodeResult(BaseModel):
    node_id: str
    status: Literal["success", "failed", "skipped"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[WorkflowArtifact] = Field(default_factory=list)
    error: str | None = None


class WorkflowRunEvent(BaseModel):
    run_id: str | None = None
    node_id: str | None = None
    event: str
    status: str = "running"
    payload: Any = Field(default_factory=dict)

    def to_sse(self) -> str:
        return f"event: {self.event}\ndata: {json.dumps(self.model_dump(), default=str)}\n\n"


class NodeRunRequest(BaseModel):
    node_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None
    run_id: str | None = None


class NodeTypesResponse(BaseModel):
    node_types: list[NodeTypeDefinition]
