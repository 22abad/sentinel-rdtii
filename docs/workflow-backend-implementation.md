# Workflow Backend Implementation Design

本文档说明如何把当前 RDTII AI Mapper 后端拆成 workflow 节点模块，以对接 PR #19 中的 React Flow 画布式前端。

核心原则：前端画布负责布局和交互，后端 workflow 负责能力注册、节点执行、数据传递、审计记录。不要让 React Flow 的 UI 状态污染后端执行协议。

## 1. 背景和目标

PR #19 把 Workbench 改成了自由画布：

- 固定业务面板：Discovery、Source、Audit、Found PDFs
- 可复制面板：Discovery / Source / Audit copy
- 用户 note：本地可编辑便签
- RAG chat：临时聊天面板
- React Flow edges：目前只是前端展示连线，没有后端执行语义

现有后端已经有可复用能力：

- Discovery: `DiscoveryService.search()`
- Text fetching: crawler、PDF reader、`/api/fetch-text`
- Extraction: `/api/extract/stream`、`stream_extraction()`、`MASOrchestrator`
- Review persistence: `/api/mappings/review`
- RAG: `/api/rag/query`
- Validation: source、timestamp、coverage
- Export: Excel export

目标是增加一层 workflow backend，而不是重写这些能力。

## 2. Implementation Strategy

建议先做 executor wrapper，再做真正的 graph workflow engine。

原因：

- PR #19 当前是 component-driven canvas：节点里放的是 `React.ReactNode`，还不是可序列化的 `type + config + ui` workflow node。
- 现有后端能力已经能跑，先包装成统一 executor 可以最快获得用户可见价值。
- executor wrapper 是后续 n8n-style workflow engine 的地基；engine 后面只负责排序、连线、传参，不直接掺业务逻辑。

Recommended build order:

```text
Phase 0: Node executor wrappers
  -> each backend capability has one uniform run/stream interface

Phase 1: Node registry API
  -> frontend can discover executable node types

Phase 2: Frontend data-driven node model + optional layout persistence
  -> React Flow nodes become serializable workflow nodes

Phase 3: Graph workflow engine
  -> edges become real data flow

Phase 4: Run history and artifacts
  -> audit, replay, rerun, export trace
```

This means the first backend PR should not depend on the frontend already being a real workflow editor. It should make `Discovery`, `Fetch Text`, `Extract`, `Review`, and `RAG` executable through one consistent backend abstraction.

## 3. Scope

### In Scope

- 定义后端节点类型和节点输入输出契约
- 提供节点类型注册表 API，供前端动态生成 toolbar/palette
- 支持单节点运行和单节点 streaming run
- 保存 canvas layout，包括节点位置、连线、note 内容。This depends on frontend data-driven nodes.
- 支持后续 DAG workflow 串流运行
- 保留现有 REST/SSE API 兼容性

### Out of Scope for MVP

- 复杂多人协作编辑
- 分布式任务队列
- 可视化版本 diff
- 任意 Python 代码节点
- 对所有旧 API 的一次性迁移

## 4. Frontend Dependency

True workflow persistence requires a frontend node model change.

Current PR #19 shape:

```ts
type CanvasPanel = {
  id: string;
  title: string;
  element: React.ReactNode;
  width?: number;
};
```

This is good for a canvas UI MVP, but it cannot be persisted as workflow execution data because `element` is a live React object.

Target shape:

```ts
type WorkflowCanvasNode = {
  id: string;
  type: string;
  label?: string;
  config: Record<string, unknown>;
  ui: {
    position: { x: number; y: number };
    width?: number;
    height?: number;
  };
};
```

Until this frontend conversion exists:

- backend executor wrappers can still be implemented and exposed
- existing panel buttons can call executor endpoints
- full layout persistence should be treated as a contract, not as an end-to-end working feature
- graph execution cannot rely on frontend edges as data flow yet

## 5. Design Principles

1. UI state 和 execution state 分离。
   - UI state: position、selected、width、panel chrome、minimap、zoom
   - Execution state: node type、config、inputs、outputs、run status

2. 节点类型由后端注册表定义。
   - 前端不 hardcode 后端可执行能力。
   - 后端返回 display metadata，前端可以决定如何渲染。

3. 现有 API 先被 wrapper 复用。
   - 第一阶段不要重写 extraction/discovery/review。
   - 节点 executor 直接调用现有 service 函数。

4. Edges 表示数据流，不表示 UI 连线。
   - 后端只消费有效 edge。
   - 无效 edge 应在运行前校验并返回清晰错误。

5. 所有节点输出都作为 artifact 保存。
   - 便于审计、回放、debug、导出。

## 6. Proposed Backend Directory Structure

```text
ai-service/
  api/
    workflows.py

  workflows/
    __init__.py
    schemas.py
    registry.py
    engine.py
    store.py
    events.py
    errors.py
    nodes/
      __init__.py
      base.py
      discovery.py
      fetch_text.py
      extract.py
      review.py
      rag.py
      validation.py
      export.py
      note.py
```

### Responsibilities

`api/workflows.py`

- FastAPI router
- Exposes node type, workflow layout, node run, workflow run endpoints
- Converts HTTP exceptions and SSE responses

`workflows/schemas.py`

- Pydantic request/response models
- Shared contract between frontend and backend

`workflows/registry.py`

- Static node registry
- Maps `node.type` to executor class
- Provides metadata for frontend palette

`workflows/engine.py`

- Validates graph
- Builds execution plan
- Runs nodes in topological order
- Routes upstream outputs into downstream inputs
- Emits run events

`workflows/store.py`

- Persistence interface
- MVP can use Postgres JSONB
- Development fallback may be file or in-memory, but production should use DB

`workflows/nodes/base.py`

- Base executor interface
- Standardizes `run(context, config, inputs) -> NodeResult`

## 7. Core Data Model

### Canvas Workflow

```python
class Workflow(BaseModel):
    id: str
    name: str
    owner_id: str | None = None
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    viewport: WorkflowViewport | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### Workflow Node

```python
class WorkflowNode(BaseModel):
    id: str
    type: str
    label: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    ui: NodeUiState = Field(default_factory=NodeUiState)
```

`ui` is persisted for the frontend, but ignored by executors.

```python
class NodeUiState(BaseModel):
    position: dict[str, float] = Field(default_factory=dict)
    width: int | None = None
    height: int | None = None
    collapsed: bool = False
```

### Workflow Edge

```python
class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    source_output: str | None = None
    target_input: str | None = None
```

If `source_output` or `target_input` is omitted, the engine can use node type defaults.

### Node Type Definition

```python
class NodeTypeDefinition(BaseModel):
    type: str
    label: str
    category: str
    description: str
    inputs: dict[str, PortDefinition] = Field(default_factory=dict)
    outputs: dict[str, PortDefinition] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    ui: NodeTypeUi = Field(default_factory=NodeTypeUi)
```

Example:

```json
{
  "type": "extract.mappings",
  "label": "Extract mappings",
  "category": "ai",
  "description": "Extract RDTII indicator mappings from document text.",
  "inputs": {
    "document": { "type": "DocumentText", "required": true },
    "provider": { "type": "ProviderConfig", "required": false }
  },
  "outputs": {
    "mappings": { "type": "IndicatorMapping[]" },
    "rejected": { "type": "RejectedExtraction[]" },
    "source_text": { "type": "string" }
  }
}
```

### Node Result

```python
class NodeResult(BaseModel):
    node_id: str
    status: Literal["success", "failed", "skipped"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[WorkflowArtifact] = Field(default_factory=list)
    error: str | None = None
```

### Run Event

All streaming workflow events should use one envelope:

```json
{
  "run_id": "run_123",
  "node_id": "extract-1",
  "event": "mapping",
  "status": "running",
  "payload": {}
}
```

This lets the frontend update a node by `node_id`, even while the extraction service streams internal events.

## 8. API Design

### 8.1 List Node Types

```http
GET /api/workflows/node-types
```

Response:

```json
{
  "node_types": [
    {
      "type": "discovery.search",
      "label": "Discovery",
      "category": "source",
      "description": "Find candidate legal sources for country and RDTII indicators.",
      "inputs": {},
      "outputs": {
        "candidates": { "type": "LegalCandidate[]" }
      }
    }
  ]
}
```

Frontend use:

- Build toolbar/palette dynamically
- Display node config forms
- Validate allowed connections before sending to backend

### 8.2 Create Workflow

```http
POST /api/workflows
```

Request:

```json
{
  "name": "Singapore pillar 6 research"
}
```

Response:

```json
{
  "id": "wf_123",
  "name": "Singapore pillar 6 research",
  "nodes": [],
  "edges": []
}
```

### 8.3 Get Workflow

```http
GET /api/workflows/{workflow_id}
```

Returns saved graph layout and optional latest run summary.

### 8.4 Save Workflow Layout

```http
PUT /api/workflows/{workflow_id}/layout
```

Request:

```json
{
  "nodes": [
    {
      "id": "discovery-1",
      "type": "discovery.search",
      "label": "Discovery",
      "config": {
        "country_code": "SGP",
        "pillars": [6, 7],
        "source_mode": "official_first"
      },
      "ui": {
        "position": { "x": 40, "y": 40 },
        "width": 800
      }
    }
  ],
  "edges": [],
  "viewport": {
    "x": 0,
    "y": 0,
    "zoom": 1
  }
}
```

Important: this endpoint stores UI state but does not execute anything.

### 8.5 Run Single Node

```http
POST /api/workflows/nodes/{node_type}/run
```

Request:

```json
{
  "node_id": "discovery-1",
  "config": {
    "country_code": "SGP",
    "pillars": [6, 7],
    "source_mode": "official_first"
  },
  "inputs": {}
}
```

Response:

```json
{
  "node_id": "discovery-1",
  "status": "success",
  "outputs": {
    "candidates": []
  }
}
```

This is the recommended MVP execution endpoint for non-streaming nodes.

For streaming nodes such as `extract.mappings`, use:

```http
POST /api/workflows/nodes/{node_type}/run/stream
```

The streaming endpoint returns the same workflow event envelope used by full workflow runs, with `run_id` optional for standalone node execution.

### 8.6 Run Workflow Stream

```http
POST /api/workflows/{workflow_id}/runs/stream
```

Request:

```json
{
  "start_node_ids": ["discovery-1"],
  "target_node_ids": ["audit-1"],
  "runtime": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash"
  }
}
```

Response:

```text
Content-Type: text/event-stream

event: node_started
data: {"run_id":"run_123","node_id":"discovery-1","event":"node_started","payload":{}}

event: node_output
data: {"run_id":"run_123","node_id":"discovery-1","event":"node_output","payload":{"candidates":[]}}

event: mapping
data: {"run_id":"run_123","node_id":"extract-1","event":"mapping","payload":{}}

event: workflow_done
data: {"run_id":"run_123","event":"workflow_done","payload":{"status":"success"}}
```

## 9. Node Types for MVP

### 9.1 `discovery.search`

Purpose:

- Search official and fallback legal sources.

Implementation:

- Reuse `DiscoveryService.search()`
- Input model can reuse `DiscoverySearchRequest`

Inputs:

- none for graph mode, or optional `country_code`, `pillars`, `indicators`

Config:

- `country_code`
- `pillars`
- `indicators`
- `keywords`
- `source_mode`
- `languages`
- `limit`

Outputs:

- `candidates: LegalCandidate[]`
- `queries: string[]`
- `sources: LegalSourceConfig[]`

### 9.2 `source.fetch_text`

Purpose:

- Fetch URL or PDF candidate into normalized text.

Implementation:

- Extract shared helper from `/api/fetch-text`
- Reuse `crawler.fetch_legal_content`
- Reuse `pdf_reader.read_pdf`

Inputs:

- `candidate: LegalCandidate`
- or `source_url: string`

Config:

- `browser_mode: auto | direct | playwright | opencli`

Outputs:

- `document: DocumentText`

Example output:

```json
{
  "document": {
    "source_url": "https://...",
    "text": "...",
    "pdf_metadata": {},
    "content_type": "text"
  }
}
```

### 9.3 `extract.mappings`

Purpose:

- Run RDTII extraction over document text.

Implementation:

- Reuse `stream_extraction()` for SSE
- Reuse `run_extraction()` for non-streaming
- Reuse provider selection logic from `api/extraction.py`

Inputs:

- `document: DocumentText`

Config:

- `provider`
- `model`
- `browser_mode`

Outputs:

- `mappings: IndicatorMapping[]`
- `rejected: RejectedExtraction[]`
- `source_text: string`
- `provider: string`

Streaming behavior:

- Wrap existing extraction events inside workflow event envelope.
- Preserve `mapping`, `rejected`, `progress`, `warning`, `done`.

### 9.4 `review.persist_mapping`

Purpose:

- Persist approved or rejected mappings to Postgres.

Implementation:

- Move core DB transaction logic from `/api/mappings/review` into service function
- API and node executor both call that service

Inputs:

- `mapping: IndicatorMapping`
- `decision: approved | rejected`

Config:

- `country_code`
- `reviewer_notes`

Outputs:

- `mapping_id`
- `status`

### 9.5 `rag.query`

Purpose:

- Ask questions over current source text, mappings, or notes.

Implementation:

- Reuse `/api/rag/query` logic

Inputs:

- `source_text`
- `mappings`
- `note`

Config:

- `question`
- `role`
- `output_format`
- `provider`
- `country_code`

Outputs:

- `answer`
- `retrieved_chunks`
- `retrieval_count`

### 9.6 `validation.source`

Purpose:

- Grade source authority and reliability.

Implementation:

- Reuse validation API/service
- Reuse `source_validator.grade_source`

Inputs:

- `source_url`
- `title`
- `text_snippet`

Outputs:

- `grade`
- `confidence`
- `reasons`

### 9.7 `validation.timestamp`

Purpose:

- Verify last update / promulgation / amendment date.

Inputs:

- `source_url`
- `last_update`

Outputs:

- `verified`
- `best_date`
- `verification_log`

### 9.8 `export.excel`

Purpose:

- Export mappings to RDTII spreadsheet format.

Implementation:

- Reuse `/api/excel/export`

Inputs:

- `mappings`

Config:

- `country_code`
- `filename`

Outputs:

- `download_url`
- `file_path`

### 9.9 `note.manual`

Purpose:

- Persist user notes from canvas.

Execution:

- Does not auto-run by default.
- Can provide `note.text` as input to `rag.query` or analyst nodes later.

Outputs:

- `note`

## 10. Executor Interface

```python
class WorkflowContext(BaseModel):
    workflow_id: str | None = None
    run_id: str | None = None
    user_id: str | None = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class NodeExecutor(ABC):
    type: str

    @abstractmethod
    async def run(
        self,
        *,
        node: WorkflowNode,
        inputs: dict[str, Any],
        context: WorkflowContext,
    ) -> NodeResult:
        ...

    async def stream(
        self,
        *,
        node: WorkflowNode,
        inputs: dict[str, Any],
        context: WorkflowContext,
    ) -> AsyncIterator[WorkflowRunEvent]:
        result = await self.run(node=node, inputs=inputs, context=context)
        yield WorkflowRunEvent.node_output(context.run_id, node.id, result.outputs)
```

Most nodes implement `run`. Extraction should implement `stream` to preserve progressive mapping updates.

## 11. Graph Execution Algorithm

MVP workflow run should support DAG only.

Steps:

1. Load workflow by id.
2. Validate all `node.type` values exist in registry.
3. Validate all edges point to known nodes.
4. Validate edge port compatibility.
5. Reject cycles.
6. Build topological order.
7. For each node:
   - gather inputs from upstream node outputs
   - merge explicit runtime inputs
   - execute node
   - save outputs as artifacts
   - emit node events
8. Emit final workflow status.

Cycle error example:

```json
{
  "detail": {
    "code": "workflow_cycle",
    "message": "Workflow graph contains a cycle.",
    "nodes": ["extract-1", "rag-1"]
  }
}
```

## 12. Persistence Model

### Migration Strategy

Use the repository's existing SQL migration style. Do not introduce Alembic or SQLAlchemy just for workflow tables.

Add a new migration file:

```text
rdtii-database/db/migrate_004_workflows.sql
```

This keeps workflow persistence aligned with the current raw `psycopg2` style used by auth and review endpoints. Service code should still hide SQL details behind `workflows/store.py`, so a later migration to SQLAlchemy or another persistence layer remains possible.

### Tables

```sql
CREATE TABLE workflows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NULL REFERENCES users(id),
  name TEXT NOT NULL,
  graph JSONB NOT NULL DEFAULT '{"nodes":[],"edges":[]}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  owner_id UUID NULL REFERENCES users(id),
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ NULL,
  error TEXT NULL
);

CREATE TABLE workflow_node_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL,
  node_type TEXT NOT NULL,
  status TEXT NOT NULL,
  inputs JSONB NOT NULL DEFAULT '{}',
  outputs JSONB NOT NULL DEFAULT '{}',
  error TEXT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ NULL
);

CREATE TABLE workflow_artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Executor-wrapper MVP does not require these tables. Layout persistence can start with only `workflows`. Add run tables when full workflow execution lands.

## 13. Frontend Integration Contract

### React Flow Node Mapping

Frontend React Flow node:

```ts
type RFNode = {
  id: string;
  type: "panel" | "note";
  position: { x: number; y: number };
  data: {
    workflowType: string;
    label: string;
    config: Record<string, unknown>;
  };
};
```

Backend workflow node:

```json
{
  "id": "discovery-1",
  "type": "discovery.search",
  "label": "Discovery",
  "config": {},
  "ui": {
    "position": { "x": 40, "y": 40 },
    "width": 800
  }
}
```

Frontend should convert React Flow shape to backend shape before saving.

### What Frontend Should Not Send as Execution Data

- `element`
- `selected`
- `dragging`
- `zIndex`
- React component names
- toolbar mode
- minimap state

These can exist in layout if needed, but executors must ignore them.

## 14. Suggested Implementation Phases

### Phase 0: Executor Wrappers

Deliverables:

- `workflows/schemas.py`
- `workflows/nodes/base.py`
- `workflows/nodes/discovery.py`
- `workflows/nodes/fetch_text.py`
- `workflows/nodes/extract.py`
- `workflows/nodes/rag.py`
- `workflows/registry.py`
- `api/workflows.py`
- `POST /api/workflows/nodes/{node_type}/run`
- `POST /api/workflows/nodes/{node_type}/run/stream` for streaming nodes
- Include router in `api/app.py`
- Unit tests with mocked services

This phase gives the existing Workbench panels a consistent backend node execution layer without requiring graph execution or layout persistence.

### Phase 1: Node Registry API

Deliverables:

- `GET /api/workflows/node-types`
- Static node definitions for executor-backed nodes
- Tests for registry response shape

Frontend can discover backend-supported nodes and gradually replace hardcoded toolbar options.

### Phase 2: Data-Driven Frontend Nodes and Layout Persistence

Deliverables:

- frontend nodes converted from `element: React.ReactNode` to `type + config + ui`
- `POST /api/workflows`
- `GET /api/workflows/{id}`
- `PUT /api/workflows/{id}/layout`
- `rdtii-database/db/migrate_004_workflows.sql`
- tests for saving and loading workflow layout

Frontend can save and reload a serializable canvas. Edges may still be visual-only in this phase.

### Phase 3: Workflow Streaming Execution

Deliverables:

- `workflows/engine.py`
- `POST /api/workflows/{id}/runs/stream`
- Topological sort
- Edge port validation
- SSE event envelope
- Extraction streaming wrapped by node id

Frontend can run `Discovery -> FetchText -> Extract -> Audit`.

### Phase 4: Run History and Audit Artifacts

Deliverables:

- `workflow_runs`
- `workflow_node_runs`
- `workflow_artifacts`
- run detail endpoint
- rerun from node
- compare current layout to previous run

This phase is important for UN auditability, but should not block MVP.

## 15. Reusing Existing Code

Current code should be refactored gently:

1. Extract shared provider selection helper from `api/extraction.py`.
2. Extract shared fetch text service from `/api/fetch-text`.
3. Extract review persistence transaction from `api/review.py`.
4. Keep old endpoints working by calling the new service functions.
5. Add workflow nodes as wrappers around service functions.

Recommended service additions:

```text
ai-service/services/
  document_fetch.py
  provider_config.py
  review_persistence.py
```

Example:

```python
async def fetch_document_text(source_url: str, browser_mode: str = "auto") -> DocumentText:
    ...
```

Then both `/api/fetch-text` and `source.fetch_text` use it.

## 16. Error Handling

Use stable error codes:

```text
unknown_node_type
invalid_node_config
missing_required_input
invalid_edge
port_type_mismatch
workflow_cycle
node_execution_failed
artifact_not_found
```

Error response:

```json
{
  "detail": {
    "code": "missing_required_input",
    "message": "Node extract-1 requires input document.",
    "node_id": "extract-1",
    "input": "document"
  }
}
```

## 17. Testing Strategy

### Unit Tests

- registry contains expected node types
- schemas reject invalid nodes/edges
- graph validation rejects missing target node
- graph validation rejects cycle
- single node execution calls expected service
- extract node streaming wraps `mapping`, `rejected`, and `progress` events

### Integration Tests

- save workflow layout and load it back
- run discovery node with fixture adapters
- run fetch text node with mocked crawler result
- run extract node with mocked provider
- stream workflow emits node events in order

### Backward Compatibility Tests

- `/api/discovery/search` still works
- `/api/fetch-text` still works
- `/api/extract/stream` still works
- `/api/mappings/review` still works

## 18. MVP Acceptance Criteria

Phase 0 is done when:

- backend has uniform executors for Discovery, Fetch Text, Extract, RAG
- non-streaming node run endpoint works
- extract streaming node run endpoint preserves progressive mappings
- old Workbench APIs still work

Phase 1 is done when:

- frontend can fetch node type definitions from backend
- old Workbench APIs still work

Phase 2 is done when:

- frontend nodes are serializable as `type + config + ui`
- frontend can save and reload a canvas
- saved layout includes nodes, edges, positions, notes
- user can run Discovery node from canvas
- user can run Fetch Text node from canvas
- user can run Extract node from canvas
- node output appears in the corresponding panel

Phase 3 is done when:

- user can connect Discovery -> Fetch Text -> Extract
- one click starts a workflow run
- extraction progress and mappings stream into the Extract/Audit node
- failed nodes show local error state without crashing the canvas

## 19. Open Questions

1. Should workflows be user-owned from day one?
   - Recommended: yes if auth is enabled, nullable owner for dev bypass.

2. Should note nodes be executable?
   - Recommended: not by default. They become context providers only when connected to RAG or Analyst nodes.

3. Should edges allow multiple candidates to fan out into multiple fetch/extract runs?
   - Recommended: not in MVP. Start with selected candidate, then add batch fan-out later.

4. Should workflow execution be synchronous SSE or background job?
   - Recommended: SSE for MVP, background queue later.

5. Should React Flow edge handles map to typed ports?
   - Recommended: yes in Phase 3. Phase 2 can store plain source/target edges.

## 20. Recommended First PR

The first PR should be small:

1. Add `workflows/schemas.py`.
2. Add `workflows/nodes/base.py`.
3. Add executor wrappers for `discovery.search`, `source.fetch_text`, `extract.mappings`, and `rag.query`.
4. Add `workflows/registry.py` mapping node type to executor.
5. Add `api/workflows.py` with single-node run endpoints.
6. Include router in `api/app.py`.
7. Add tests for executor wrappers and endpoint response shape.

Do not modify extraction behavior in the first PR. Wrap existing behavior and keep old endpoints alive.

That keeps integration safe, gives the frontend user-visible node execution early, and leaves full graph execution for a later PR.
