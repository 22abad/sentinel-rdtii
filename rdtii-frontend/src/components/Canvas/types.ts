import type React from "react";

/** Canvas interaction tool — Select (move/marquee) vs Hand (pan). */
export type CanvasMode = "select" | "hand";

/** One workbench panel rendered as a node on the canvas. */
export type CanvasPanel = {
  id: string;
  title: string;
  /** Shared element — used when `renderElement` is not provided. */
  element?: React.ReactNode;
  /** Per-instance rendering: when set, each canvas instance of this panel
      (the original and every spawned copy) gets its own element built from
      its node id — the basis of independent extraction threads. Falls back
      to the shared `element` when omitted. */
  renderElement?: (instanceId: string) => React.ReactNode;
  width?: number;
  /** Optional selector limiting where React Flow may start dragging the panel. */
  dragHandle?: string;
  /** Edges are data wires: instances of this panel bind to an instance of
      the named upstream panel via edges (copy-aware). Reported through
      onCanvasGraphChange; unbound instances should render a guard. */
  upstreamId?: string;
};

/** A spawnable panel type shown as a button in the toolbar palette. */
export type SpawnType = { id: string; label: string };

export type WorkbenchCanvasNodeKind = "panel" | "note" | "rag" | "material";

export type WorkbenchCanvasPosition = {
  x: number;
  y: number;
};

export type WorkbenchCanvasSize = {
  width?: number;
  height?: number;
};

export type WorkbenchCanvasViewport = WorkbenchCanvasPosition & {
  zoom: number;
};

export type WorkbenchCanvasNode = {
  id: string;
  kind: WorkbenchCanvasNodeKind;
  panelId?: string;
  title?: string;
  text?: string;
  config?: Record<string, unknown>;
  position: WorkbenchCanvasPosition;
  width?: number;
  height?: number;
  removed?: boolean;
};

export type WorkbenchCanvasEdge = {
  id: string;
  source: string;
  target: string;
  kind: "visual";
  label?: string;
  animated?: boolean;
};

export type WorkbenchCanvasLayout = {
  version: 1;
  nodes: WorkbenchCanvasNode[];
  edges: WorkbenchCanvasEdge[];
  viewport?: WorkbenchCanvasViewport;
  updatedAt?: string;
};
