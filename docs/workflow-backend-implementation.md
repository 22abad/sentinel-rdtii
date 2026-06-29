# Workbench Canvas Implementation Design

本文档说明如何把 RDTII AI Mapper 的 Workbench 做成可保存的自由画布，用来组织研究材料、面板位置、notes、RAG chat 和视觉连线。

核心原则：**业务流程保持不变，画布只提供自由摆放和材料组织能力。**

This is closer to Figma/FigJam than n8n. React Flow is used as an infinite workbench canvas, not as the source of truth for execution order.

The existing executor wrapper layer remains useful, but its role is narrower:

- Canvas layout = where panels, notes, chats, and materials live.
- Executor wrapper = how a panel button calls backend capabilities.
- Visual edges = research/storytelling aids, not data-flow dependencies.

## 1. 背景和目标

PR #19 把 Workbench 改成了自由画布：

- 固定业务面板：Discovery、Source、Audit、Found PDFs
- 可复制面板：Discovery / Source / Audit copy
- 用户 note：本地可编辑便签
- RAG chat：临时聊天面板
- React Flow edges：视觉组织连线，帮助用户解释材料关系，不决定执行顺序

现有后端已经有可复用能力：

- Discovery: `DiscoveryService.search()`
- Text fetching: crawler、PDF reader、`/api/fetch-text`
- Extraction: `/api/extract/stream`、`stream_extraction()`、`MASOrchestrator`
- Review persistence: `/api/mappings/review`
- RAG: `/api/rag/query`
- Validation: source、timestamp、coverage
- Export: Excel export

目标不是把产品做成 n8n-style automation workflow，而是：

1. 保持现有核心研究流程稳定：`Discovery -> Source -> Extract -> Audit`。
2. 允许用户在无限画布上自由摆放和保存研究材料。
3. 让面板按钮可以通过 executor wrapper 调用后端能力。
4. 后续可选地增加 backend persistence，让画布跨设备/跨会话保存。

## 2. Implementation Strategy

建议把实现分成两条互补但独立的线：

### A. Executor-Backed Panels

This is already implemented by the Phase 0 backend PR.

It provides:

- `GET /api/workflows/node-types`
- `POST /api/workflows/nodes/{node_type}/run`
- `POST /api/workflows/nodes/{node_type}/run/stream`

These endpoints are useful when a canvas panel needs to trigger backend work, but they do not imply that edges define execution.

### B. Canvas Layout Persistence

This is the next product-aligned direction.

It saves:

- panel positions
- note contents
- visual edges
- spawned RAG chats
- panel visibility/removal
- viewport position/zoom

It does not save:

- React component instances
- execution state as graph truth
- data-flow dependencies
- LLM run history

Recommended build order:

```text
Phase 0: Executor wrappers
  -> already done; panels can call backend capabilities through a uniform interface

Phase 1: Local canvas persistence
  -> save/restore WorkbenchCanvas layout in localStorage

Phase 2: Backend canvas persistence
  -> save/restore layout through DB-backed API

Phase 3: Canvas material model
  -> support notes, evidence/material cards, pinned source snippets, screenshots

Optional Future: Graph execution
  -> only if the product later chooses automation semantics
```

The immediate next PR should be local canvas persistence, not graph execution.

## 3. Scope

### In Scope

- 保存和恢复 Workbench canvas layout
- 保存用户添加的 notes、RAG chat nodes、visual edges、viewport
- 保持核心业务流程和现有面板行为不变
- 允许面板按钮继续调用 existing APIs 或 executor wrapper APIs
- 保留现有 REST/SSE API 兼容性

### Out of Scope for MVP

- 复杂多人协作编辑
- 分布式任务队列
- 可视化版本 diff
- 任意 Python 代码节点
- graph/DAG execution engine
- 让 React Flow edges 决定执行顺序
- 对所有旧 API 的一次性迁移

## 4. Frontend Model

Canvas persistence requires a serializable canvas model.

Current PR #19 shape:

```ts
type CanvasPanel = {
  id: string;
  title: string;
  element: React.ReactNode;
  width?: number;
};
```

This is good for rendering existing panels, but `element` is a live React object and cannot be persisted.

Target shape:

```ts
type WorkbenchCanvasNode = {
  id: string;
  kind: "panel" | "note" | "rag" | "material";
  panelId?: "discovery" | "source" | "audit" | "foundPdfs";
  title?: string;
  text?: string;
  config?: Record<string, unknown>;
  position: { x: number; y: number };
  width?: number;
  height?: number;
  removed?: boolean;
};
```

Notes:

- `kind` describes what the canvas item is.
- `panelId` maps a persisted node back to an existing Workbench panel.
- `config` is optional panel UI/configuration state, not an execution graph contract.
- visual edges can be persisted, but they should be treated as annotation/organization aids.

## 5. Design Principles

1. UI state 和 execution state 分离。
   - UI state: position、selected、width、panel chrome、minimap、zoom
   - Execution state: existing hooks/API state such as extraction progress and audit mappings

2. 核心工作流保持不变。
   - Discovery、Source、Extract、Audit 的业务顺序不由 edges 决定。
   - Canvas layout only changes how users arrange and inspect materials.

3. Executor wrapper 是面板能力层，不是自动化引擎。
   - Panels may call executor endpoints.
   - The canvas does not need to run a whole graph.

4. Edges are visual.
   - They may express "this note explains this source" or "this evidence supports this mapping".
   - They do not route data unless a future product decision explicitly changes that.

5. Persistence starts with layout, not run history.
   - LocalStorage is enough for the first frontend validation.
   - Backend DB persistence can follow once the layout shape is stable.

## 6. Current Backend Boundary

```text
ai-service/
  api/
    workflows.py

  workflows/
    __init__.py
    schemas.py
    registry.py
    nodes/
      __init__.py
      base.py
      discovery.py
      fetch_text.py
      extract.py
      rag.py
```

### Responsibilities

`api/workflows.py`

- FastAPI router
- exposes executor-backed node run endpoints
- converts HTTP exceptions and SSE responses
- does not persist canvas layout
- does not execute a graph

`workflows/schemas.py`

- Pydantic request/response models for executor-backed panel actions
- shared response envelope for streaming node runs

`workflows/registry.py`

- static executor registry
- maps `node.type` to executor class
- provides metadata for panel/action discovery

`workflows/nodes/base.py`

- Base executor interface
- Standardizes `run(context, config, inputs) -> NodeResult`

### Future Canvas Persistence Boundary

For backend layout persistence, add a separate module later:

```text
ai-service/
  api/
    workbench_canvas.py
  workbench_canvas/
    schemas.py
    store.py
```

This should stay separate from `workflows/` because canvas layout is not workflow execution.

## 7. Core Data Model

### Workbench Canvas Layout

```ts
type WorkbenchCanvasLayout = {
  version: 1;
  nodes: WorkbenchCanvasNode[];
  edges: WorkbenchCanvasEdge[];
  viewport?: {
    x: number;
    y: number;
    zoom: number;
  };
  updatedAt?: string;
};
```

### Workbench Canvas Node

```ts
type WorkbenchCanvasNode = {
  id: string;
  kind: "panel" | "note" | "rag" | "material";
  panelId?: "discovery" | "source" | "audit" | "foundPdfs";
  title?: string;
  text?: string;
  config?: Record<string, unknown>;
  position: { x: number; y: number };
  width?: number;
  height?: number;
  removed?: boolean;
};
```

### Workbench Canvas Edge

```ts
type WorkbenchCanvasEdge = {
  id: string;
  source: string;
  target: string;
  kind: "visual";
  label?: string;
};
```

Edges deliberately do not include `source_output`, `target_input`, or port mapping in the product's current direction.

### Executor Node Type Definition

The `inputs` and `outputs` fields are descriptive metadata for palettes, docs, and panel adapters. They are not typed route validation, and they do not imply edge/port routing.

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
    "document": { "type": "DocumentText", "required": false }
  },
  "outputs": {
    "mappings": { "type": "IndicatorMapping[]" },
    "rejected": { "type": "RejectedExtraction[]" },
    "source_text": { "type": "string" }
  }
}
```

### Executor Node Result

```python
class NodeResult(BaseModel):
    node_id: str
    status: Literal["success", "failed", "skipped"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[WorkflowArtifact] = Field(default_factory=list)
    error: str | None = None
```

### Executor Run Event

All streaming executor events use one envelope:

```json
{
  "run_id": "run_123",
  "node_id": "extract-1",
  "event": "mapping",
  "status": "running",
  "payload": {}
}
```

This lets a panel update by `node_id`, even while extraction streams internal events. It is not a graph-run contract.

## 8. API Design

### 8.1 Executor API Already Available

```http
GET /api/workflows/node-types
POST /api/workflows/nodes/{node_type}/run
POST /api/workflows/nodes/{node_type}/run/stream
```

Use this when a panel wants to run backend work through the executor wrapper.

Example discovery request:

```json
{
  "node_id": "discovery-1",
  "config": {
    "country_code": "SGP",
    "pillars": [6, 7],
    "browser_mode": "mock",
    "limit": 5
  }
}
```

### 8.2 Local Canvas Persistence

Recommended next PR: save `WorkbenchCanvasLayout` to browser storage first.

```ts
const STORAGE_KEY = "rdtii.workbench.canvas.v1";
localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
```

This validates the product behavior without adding database or ownership complexity.

### 8.3 Future Backend Canvas API

Only after the local layout shape is stable:

```http
GET /api/workbench-canvas
PUT /api/workbench-canvas
```

or, if multiple boards are needed:

```http
GET /api/workbench-canvases
POST /api/workbench-canvases
GET /api/workbench-canvases/{id}
PUT /api/workbench-canvases/{id}
```

Request body:

```json
{
  "name": "Singapore pillar 6 research",
  "layout": {
    "version": 1,
    "nodes": [],
    "edges": [],
    "viewport": { "x": 0, "y": 0, "zoom": 1 }
  }
}
```

## 9. Implemented Executor Types

### 9.1 `discovery.search`

Purpose:

- Search official and fallback legal sources.

Implementation:

- Reuse `DiscoveryService.search()`
- Input model can reuse `DiscoverySearchRequest`

Inputs:

- none required; all search parameters can come from node config or panel state

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

### 9.4 `rag.query`

Purpose:

- Ask questions over current source text, mappings, or notes.

Implementation:

- Reuse `/api/rag/query` logic

Inputs:

- `source_text`
- `document`

Config:

- `question`
- `role`
- `context`
- `country_code`

Outputs:

- `answer`
- `provider`

### Existing endpoints not wrapped as executors

These capabilities already exist and should stay outside the executor registry unless a concrete panel integration needs them:

- `review.persist_mapping`: covered by `/api/mappings/review`
- `validation.source`: covered by validation/source helper APIs
- `validation.timestamp`: covered by timestamp verification APIs
- `export.excel`: covered by `/api/excel/export`

`note.manual` is not an executor. In the canvas model it is `kind: "note"` and belongs to layout persistence.

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
        yield WorkflowRunEvent(
            run_id=context.run_id,
            node_id=node.id,
            event="node_started",
            payload={"node_type": node.type},
        )
        result = await self.run(node=node, inputs=inputs, context=context)
        yield WorkflowRunEvent(
            run_id=context.run_id,
            node_id=node.id,
            event="node_output",
            status=result.status,
            payload=result.model_dump(),
        )
```

Most nodes implement `run` and inherit this default stream behavior. `extract.mappings` and `rag.query` override `stream` to preserve progressive mapping/token updates, then emit a terminal `node_output`.

## 11. Persistence Model

### LocalStorage First

The recommended next step is local canvas persistence:

```text
rdtii.workbench.canvas.v1
```

Store the serialized `WorkbenchCanvasLayout` after:

- moving nodes
- creating/deleting notes
- spawning/removing panels
- connecting/removing visual edges
- changing viewport

Use a debounce so drag operations do not write on every pointer movement.

### Backend Persistence Later

Once the local shape is stable, use the repository's existing SQL migration style. Do not introduce Alembic or SQLAlchemy just for canvas layout tables.

Add a migration such as:

```text
rdtii-database/db/migrate_004_workbench_canvases.sql
```

Suggested table:

```sql
CREATE TABLE workbench_canvases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NULL REFERENCES users(id),
  name TEXT NOT NULL DEFAULT 'Default workbench',
  layout JSONB NOT NULL DEFAULT '{"version":1,"nodes":[],"edges":[]}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

No `workflow_runs`, `workflow_node_runs`, or run artifact tables are needed for the current product direction.

## 12. Frontend Integration Contract

### React Flow Node Mapping

React Flow can still render custom `panel` and `note` node components. The serializable layer should sit next to rendering state:

```ts
type RFNode = {
  id: string;
  type: "panel" | "note";
  position: { x: number; y: number };
  data: {
    kind: "panel" | "note" | "rag" | "material";
    panelId?: "discovery" | "source" | "audit" | "foundPdfs";
    title?: string;
    text?: string;
    config?: Record<string, unknown>;
  };
};
```

Persisted layout node:

```json
{
  "id": "source",
  "kind": "panel",
  "panelId": "source",
  "position": { "x": 40, "y": 360 },
  "width": 460
}
```

Note node:

```json
{
  "id": "note-1",
  "kind": "note",
  "title": "Evidence note",
  "text": "Check official gazette date.",
  "position": { "x": 720, "y": 280 },
  "width": 240
}
```

### What Frontend Should Not Persist

- `element`
- `selected`
- `dragging`
- transient hover state
- raw React component names
- toolbar mode
- minimap mask state
- LLM stream buffers

### What Frontend Should Persist

- node id
- node kind
- panel id
- note title/text
- position
- width/height when user-controlled
- removed/visible state
- visual edges
- viewport

## 13. Suggested Implementation Phases

### Phase 0: Executor Wrappers

Status: done.

Backend provides executor-backed panel actions:

- `discovery.search`
- `source.fetch_text`
- `extract.mappings`
- `rag.query`

This stays useful even though the product is not becoming n8n.

### Phase 1: Local Canvas Persistence

Deliverables:

- `WorkbenchCanvas` serializes nodes, visual edges, and viewport.
- Layout saves to localStorage.
- Layout restores on reload.
- Notes persist across reload.
- Reset button can clear saved layout and restore defaults.
- No backend API or database changes.

This is the recommended next PR.

### Phase 2: Backend Canvas Persistence

Deliverables:

- `workbench_canvases` DB table.
- `GET /api/workbench-canvas`
- `PUT /api/workbench-canvas`
- Auth-aware owner id when auth is enabled, nullable owner for dev bypass.
- Frontend replaces localStorage save/load with backend save/load, keeping localStorage fallback.

### Phase 3: Material Cards

Deliverables:

- Evidence/source snippet card
- Saved candidate URL card
- PDF/material card
- Optional screenshot/card attachment placeholder

This turns the canvas into a richer research board without changing the core extraction flow.

### Optional Future: Graph Execution

Only consider this if the product later chooses automation semantics.

For now:

- no topological sort
- no typed edge ports
- no `source_output` / `target_input`
- no workflow run tables
- no edge-driven execution

## 14. Reusing Existing Code

Current code should stay conservative:

1. Keep old endpoints working.
2. Let existing panels continue using `useDiscovery`, `useExtraction`, and existing hooks.
3. Use executor endpoints where they reduce duplication or make panel actions cleaner.
4. Do not replace the extraction/audit state model just to satisfy the canvas.
5. Keep layout persistence separate from execution code.

## 15. Error Handling

Canvas persistence errors should not break the core Workbench flow.

Recommended behavior:

- If localStorage save fails, show a small non-blocking warning or silently degrade.
- If backend save fails later, keep local copy and retry.
- If layout load fails, fall back to default panel positions.
- If a persisted panel kind is unknown, skip it and preserve the rest of the layout.

## 16. Testing Strategy

### Frontend Unit Tests

- serialize default canvas layout
- restore panel positions
- restore note title/text
- reset saved layout
- ignore unknown node kinds

### Frontend Interaction Tests

- drag panel, reload, position remains
- add note, reload, note remains
- delete panel, reload, panel stays removed
- reset layout restores default panels

### Backward Compatibility Tests

- existing Discovery panel still searches
- existing Source panel still extracts/fetches
- existing Audit panel still displays mappings
- executor API tests still pass

## 17. MVP Acceptance Criteria

Phase 1 is done when:

- user can move panels and refresh without losing positions
- user can add/edit notes and refresh without losing notes
- visual edges can be saved/restored if enabled
- reset returns the board to default layout
- extraction/audit behavior is unchanged

Phase 2 is done when:

- same layout persists across browser sessions through backend storage
- authenticated users get their own saved canvas
- localStorage can still serve as fallback

## 18. Open Questions

1. Should there be one default board per user or multiple named boards?
   - Recommended: one default board first.

2. Should visual edges be saved in Phase 1?
   - Recommended: yes if already available in React Flow state, but keep `kind: "visual"`.

3. Should notes be included in exported audit outputs?
   - Recommended: not in MVP. Treat notes as workspace context.

4. Should backend canvas layout store current extraction results?
   - Recommended: no. Store layout only; extraction results remain existing app state/database responsibility.

## 19. Recommended Next PR

Build local canvas persistence only:

1. Add a serializable `WorkbenchCanvasLayout` type.
2. Convert current canvas state to/from that layout shape.
3. Save layout to localStorage with debounce.
4. Restore layout on Workbench load.
5. Persist custom notes and removed/spawned panels.
6. Add/reset saved layout behavior.

Do not modify the core extraction workflow. Do not add graph execution.
