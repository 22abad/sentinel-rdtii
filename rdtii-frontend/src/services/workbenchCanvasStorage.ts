import { WORKBENCH_CANVAS_API_URL } from "../lib/constants";
import { getStoredToken } from "../hooks/useAuth";
import type { WorkbenchCanvasLayout } from "../components/Canvas";

export const WORKBENCH_CANVAS_LAYOUT_STORAGE_KEY = "rdtii.workbench.canvas.v1";
const DEFAULT_SCOPE_KEY = "default";
const LOAD_TIMEOUT_MS = 5000;

type CanvasLayoutResponse = {
  scope_key: string;
  layout: WorkbenchCanvasLayout | null;
  updated_at?: string | null;
};

let backendWriteQueue = Promise.resolve();

export function readLocalWorkbenchCanvasLayout(): WorkbenchCanvasLayout | null {
  if (typeof window === "undefined") return null;
  try {
    const key = localStorageKey();
    if (!key) return null;
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return isWorkbenchCanvasLayout(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveLocalWorkbenchCanvasLayout(layout: WorkbenchCanvasLayout) {
  if (typeof window === "undefined") return;
  try {
    const key = localStorageKey();
    if (!key) return;
    window.localStorage.setItem(key, JSON.stringify(layout));
  } catch {
    // Persistence is best-effort; the workbench remains usable if storage is full or blocked.
  }
}

export async function loadWorkbenchCanvasLayout(scopeKey = DEFAULT_SCOPE_KEY): Promise<WorkbenchCanvasLayout | null> {
  const token = getStoredToken();
  const localLayout = readLocalWorkbenchCanvasLayout();
  if (!token) return localLayout;

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), LOAD_TIMEOUT_MS);
  try {
    const response = await fetch(`${WORKBENCH_CANVAS_API_URL}?scope_key=${encodeURIComponent(scopeKey)}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Canvas layout backend read failed.");
    const payload = (await response.json()) as CanvasLayoutResponse;
    const backendLayout = normalizeBackendLayout(payload);
    if (backendLayout) {
      return newerLayout(backendLayout, localLayout);
    }
  } catch {
    // Fall back to local layout if the backend is offline, unauthenticated, or not migrated yet.
  } finally {
    window.clearTimeout(timeout);
  }

  return localLayout;
}

export function syncWorkbenchCanvasLayout(layout: WorkbenchCanvasLayout, scopeKey = DEFAULT_SCOPE_KEY) {
  const token = getStoredToken();
  if (!token) return Promise.resolve();

  backendWriteQueue = backendWriteQueue
    .catch(() => undefined)
    .then(async () => {
      const response = await fetch(WORKBENCH_CANVAS_API_URL, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          scope_key: scopeKey,
          layout,
        }),
      });
      if (!response.ok) throw new Error("Canvas layout backend write failed.");
    })
    .catch(() => {
      // Local persistence has already succeeded; backend sync can retry on the next save.
    });

  return backendWriteQueue;
}

function normalizeBackendLayout(payload: CanvasLayoutResponse): WorkbenchCanvasLayout | null {
  if (!isWorkbenchCanvasLayout(payload.layout)) return null;
  return {
    ...payload.layout,
    updatedAt: payload.updated_at ?? payload.layout.updatedAt,
  };
}

function newerLayout(backendLayout: WorkbenchCanvasLayout, localLayout: WorkbenchCanvasLayout | null) {
  if (!localLayout) return backendLayout;
  return layoutTime(localLayout) > layoutTime(backendLayout) ? localLayout : backendLayout;
}

function layoutTime(layout: WorkbenchCanvasLayout) {
  const time = Date.parse(layout.updatedAt ?? "");
  return Number.isFinite(time) ? time : 0;
}

function isWorkbenchCanvasLayout(value: unknown): value is WorkbenchCanvasLayout {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<WorkbenchCanvasLayout>;
  return candidate.version === 1 && Array.isArray(candidate.nodes) && Array.isArray(candidate.edges);
}

function localStorageKey() {
  const token = getStoredToken();
  if (!token) return WORKBENCH_CANVAS_LAYOUT_STORAGE_KEY;
  const userId = getStoredUserId(token);
  return userId ? `${WORKBENCH_CANVAS_LAYOUT_STORAGE_KEY}.${userId}` : null;
}

function getStoredUserId(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.sub === "string" && payload.sub ? payload.sub : null;
  } catch {
    return null;
  }
}
