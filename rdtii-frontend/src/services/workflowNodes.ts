import { DISCOVERY_BASE_URL, WORKFLOW_API_URL } from "../lib/constants";
import { authHeaders, safeJsonParse } from "../lib/http";
import type {
  DiscoveryCountry,
  DiscoveryRegistry,
  DiscoverySearchResponse,
  DiscoverySourceMode,
  ExtractionResponse,
  LegalCandidate,
} from "../types";

export type WorkflowNodeType =
  | "discovery.search"
  | "source.fetch_text"
  | "extract.mappings"
  | "rag.query";

export type PortDefinition = {
  type: string;
  required?: boolean;
  description?: string;
};

export type NodeTypeDefinition = {
  type: WorkflowNodeType | string;
  label: string;
  category: string;
  description: string;
  inputs: Record<string, PortDefinition>;
  outputs: Record<string, PortDefinition>;
  config_schema: Record<string, unknown>;
  ui: {
    icon?: string;
    color?: string;
    default_width?: number | null;
  };
  supports_streaming: boolean;
};

export type WorkflowArtifact = {
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type NodeResult<TOutputs = Record<string, unknown>> = {
  node_id: string;
  status: "success" | "failed" | "skipped";
  outputs: TOutputs;
  artifacts: WorkflowArtifact[];
  error?: string | null;
};

export type WorkflowRunEvent<TPayload = unknown> = {
  run_id?: string | null;
  node_id?: string | null;
  event: string;
  status: string;
  payload: TPayload;
};

export type NodeRunRequest = {
  node_id?: string;
  config?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  workflow_id?: string;
  run_id?: string;
};

export type DiscoveryNodeRequest = {
  countryCode: string;
  pillars: number[];
  keywords: string;
  sourceMode: DiscoverySourceMode;
  languages: string[];
};

export type DocumentText = {
  source_url: string;
  text: string;
  content_type?: string;
  title?: string;
  pdf_metadata?: Record<string, unknown> | null;
};

export type RagQueryRequest = {
  question: string;
  role?: string;
  context?: string;
  output_format?: string;
  source_text?: string;
  country_code?: string;
  provider?: string;
};

export type RagQueryResponse = {
  answer: string;
  provider: string;
};

export type ExtractMappingsNodeRequest = {
  text?: string;
  sourceUrl?: string;
  document?: DocumentText;
  provider?: string;
  model?: string;
  browserMode?: string;
};

export async function listWorkflowNodeTypes(): Promise<NodeTypeDefinition[]> {
  const res = await fetch(`${WORKFLOW_API_URL}/node-types`, {
    headers: authHeaders(),
  });
  const payload = await readJsonResponse<{ node_types: NodeTypeDefinition[] }>(
    res,
  );
  return payload.node_types;
}

export async function listDiscoveryCountries(): Promise<DiscoveryCountry[]> {
  const res = await fetch(`${DISCOVERY_BASE_URL}/countries`, {
    headers: authHeaders(),
  });
  const payload = await readJsonResponse<{ countries: DiscoveryCountry[] }>(
    res,
  );
  return payload.countries;
}

export async function getDiscoveryConfig(): Promise<DiscoveryRegistry> {
  const res = await fetch(`${DISCOVERY_BASE_URL}/config`, {
    headers: authHeaders(),
  });
  const payload = await readJsonResponse<{ registry: DiscoveryRegistry }>(res);
  return payload.registry;
}

export async function saveDiscoveryConfig(
  registry: DiscoveryRegistry,
): Promise<DiscoveryRegistry> {
  const res = await fetch(`${DISCOVERY_BASE_URL}/config`, {
    method: "PUT",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ registry }),
  });
  const payload = await readJsonResponse<{ registry: DiscoveryRegistry }>(res);
  return payload.registry;
}

export async function runWorkflowNode<TOutputs>(
  nodeType: WorkflowNodeType | string,
  request: NodeRunRequest = {},
  options: { signal?: AbortSignal } = {},
): Promise<NodeResult<TOutputs>> {
  const res = await fetch(
    `${WORKFLOW_API_URL}/nodes/${encodeURIComponent(nodeType)}/run`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        config: {},
        inputs: {},
        runtime: {},
        ...request,
      }),
      signal: options.signal,
    },
  );
  const result = await readJsonResponse<NodeResult<TOutputs>>(res);
  if (result.status !== "success") {
    throw new Error(
      result.error ||
        `Workflow node ${nodeType} finished with status ${result.status}.`,
    );
  }
  return result;
}

export async function* streamWorkflowNode<TPayload = unknown>(
  nodeType: WorkflowNodeType | string,
  request: NodeRunRequest = {},
  options: { signal?: AbortSignal } = {},
): AsyncGenerator<WorkflowRunEvent<TPayload>, void, unknown> {
  const res = await fetch(
    `${WORKFLOW_API_URL}/nodes/${encodeURIComponent(nodeType)}/run/stream`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        config: {},
        inputs: {},
        runtime: {},
        ...request,
      }),
      signal: options.signal,
    },
  );

  if (!res.ok || !res.body) {
    await readJsonResponse(res);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const event = parseSseEvent<TPayload>(chunk);
      if (event) yield event;
    }
  }

  buffer += decoder.decode();
  const trailing = parseSseEvent<TPayload>(buffer);
  if (trailing) yield trailing;
}

export async function runDiscoverySearchNode(
  request: DiscoveryNodeRequest,
): Promise<DiscoverySearchResponse> {
  const result = await runWorkflowNode<DiscoverySearchResponse>(
    "discovery.search",
    {
      node_id: "discovery",
      inputs: {
        country_code: request.countryCode,
        pillars: request.pillars,
        keywords: request.keywords,
        source_mode: request.sourceMode,
        languages: request.languages,
        limit: 12,
        browser_mode: "auto",
      },
    },
  );
  return result.outputs;
}

export async function fetchSourceTextNode(
  sourceUrl: string,
  candidate?: LegalCandidate,
): Promise<DocumentText> {
  const result = await runWorkflowNode<{ document: DocumentText }>(
    "source.fetch_text",
    {
      node_id: "source-fetch",
      inputs: {
        source_url: sourceUrl,
        candidate,
      },
      config: {
        browser_mode: "auto",
      },
    },
  );
  return result.outputs.document;
}

export async function runExtractMappingsNode(
  request: ExtractMappingsNodeRequest,
): Promise<ExtractionResponse> {
  const result = await runWorkflowNode<ExtractionResponse>("extract.mappings", {
    node_id: "extract",
    inputs: {
      text: request.text,
      source_url: request.sourceUrl,
      document: request.document,
    },
    config: {
      provider: request.provider,
      model: request.model,
      browser_mode: request.browserMode ?? "auto",
    },
  });
  return result.outputs;
}

export function streamExtractMappingsNode(request: ExtractMappingsNodeRequest) {
  return streamWorkflowNode("extract.mappings", {
    node_id: "extract",
    inputs: {
      text: request.text,
      source_url: request.sourceUrl,
      document: request.document,
    },
    config: {
      provider: request.provider,
      model: request.model,
      browser_mode: request.browserMode ?? "auto",
    },
  });
}

export async function runRagQueryNode(
  request: RagQueryRequest,
): Promise<RagQueryResponse> {
  const result = await runWorkflowNode<RagQueryResponse>("rag.query", {
    node_id: "rag",
    inputs: request as Record<string, unknown>,
  });
  return result.outputs;
}

async function readJsonResponse<T = unknown>(res: Response): Promise<T> {
  const rawPayload = await res.text();
  const payload = rawPayload ? safeJsonParse(rawPayload) : null;
  if (!res.ok) {
    throw new Error(extractErrorMessage(payload, rawPayload, res.status));
  }
  if (payload === null) {
    throw new Error("Workflow node API returned an empty response.");
  }
  return payload as T;
}

function parseSseEvent<TPayload>(
  chunk: string,
): WorkflowRunEvent<TPayload> | null {
  const dataLines: string[] = [];
  for (const line of chunk.split(/\r?\n/)) {
    if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
    }
  }
  if (dataLines.length === 0) return null;
  return safeJsonParse(
    dataLines.join("\n"),
  ) as WorkflowRunEvent<TPayload> | null;
}

function extractErrorMessage(
  payload: unknown,
  rawPayload: string,
  status: number,
): string {
  return formatWorkflowErrorPayload(
    payload,
    rawPayload || `Workflow node API failed with status ${status}.`,
  );
}

export function formatWorkflowErrorPayload(
  payload: unknown,
  fallback: string,
): string {
  if (isRecord(payload)) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return formatValidationErrors(detail);
    if (isRecord(detail) && typeof detail.message === "string")
      return detail.message;
  }
  return typeof payload === "string" ? payload : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function formatValidationErrors(detail: unknown[]): string {
  const messages = detail
    .map((item) => {
      if (!isRecord(item)) return "";
      const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
      const message = typeof item.msg === "string" ? item.msg : "";
      if (!message) return "";
      return location ? `${location}: ${message}` : message;
    })
    .filter(Boolean);
  return messages.length
    ? messages.join("; ")
    : "Workflow node request validation failed.";
}
