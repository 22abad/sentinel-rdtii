import type { ExtractionResponse, ReviewDecision, Status } from "../types";

// Parity with the old useState initial (constants.sampleText === "").
// Inlined so this module has no Vite-only imports and stays unit-testable.
const INITIAL_TEXT = "";

/**
 * Thread-keyed extraction state store.
 *
 * Each extraction "thread" (Phase 2: one per Source panel instance) owns its
 * full run state. Panels subscribe to a thread via `useSyncExternalStore`
 * (see useExtractionThread), so state survives panel unmount/remount and can
 * be shared across sibling canvas nodes (Source ↔ Audit) without prop
 * threading.
 *
 * Provider/model selection is deliberately NOT here — it is app-global and
 * stays inside the hook (localStorage-backed).
 */

export const DEFAULT_THREAD_ID = "default";

export type ExtractionThreadState = {
  country: string;
  pillarFilter: string;
  sourceUrl: string;
  text: string;
  status: Status;
  error: string;
  warning: string;
  response: ExtractionResponse | null;
  isStopping: boolean;
  activeKey: string | null;
  decisions: Record<string, ReviewDecision>;
  showRejected: boolean;
  extractionProgress: { current: number; total: number; phase: string };
  batchProgress: { current: number; total: number; currentUrl: string };
  foundPdfs: string[];
  detectedCountry: { code: string; name: string; detected: boolean } | null;
};

function initialThreadState(): ExtractionThreadState {
  return {
    country: "CHN",
    pillarFilter: "all",
    sourceUrl: "",
    text: INITIAL_TEXT,
    status: "idle",
    error: "",
    warning: "",
    response: null,
    isStopping: false,
    activeKey: null,
    decisions: {},
    showRejected: false,
    extractionProgress: { current: 0, total: 0, phase: "" },
    batchProgress: { current: 0, total: 0, currentUrl: "" },
    foundPdfs: [],
    detectedCountry: null,
  };
}

const threads = new Map<string, ExtractionThreadState>();
const listeners = new Map<string, Set<() => void>>();

export function getThreadSnapshot(threadId: string): ExtractionThreadState {
  let state = threads.get(threadId);
  if (!state) {
    state = initialThreadState();
    threads.set(threadId, state);
  }
  return state;
}

export function subscribeThread(threadId: string, callback: () => void): () => void {
  let set = listeners.get(threadId);
  if (!set) {
    set = new Set();
    listeners.set(threadId, set);
  }
  set.add(callback);
  return () => {
    set.delete(callback);
  };
}

export function updateThread(
  threadId: string,
  patch:
    | Partial<ExtractionThreadState>
    | ((prev: ExtractionThreadState) => Partial<ExtractionThreadState>),
): void {
  const prev = getThreadSnapshot(threadId);
  const resolved = typeof patch === "function" ? patch(prev) : patch;
  threads.set(threadId, { ...prev, ...resolved });
  listeners.get(threadId)?.forEach((callback) => callback());
}

// ── Non-reactive per-thread side channels ────────────────────────────────
// Mutable ref-shaped objects (stable identity per thread) so existing hook
// code using `ref.current` works unchanged.

const abortRefs = new Map<string, { current: AbortController | null }>();

export function getThreadAbortRef(threadId: string): { current: AbortController | null } {
  let ref = abortRefs.get(threadId);
  if (!ref) {
    ref = { current: null };
    abortRefs.set(threadId, ref);
  }
  return ref;
}

const detectTimerRefs = new Map<string, { current: ReturnType<typeof setTimeout> | null }>();

export function getThreadDetectTimerRef(
  threadId: string,
): { current: ReturnType<typeof setTimeout> | null } {
  let ref = detectTimerRefs.get(threadId);
  if (!ref) {
    ref = { current: null };
    detectTimerRefs.set(threadId, ref);
  }
  return ref;
}
