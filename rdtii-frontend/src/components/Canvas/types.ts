import type React from "react";

/** Canvas interaction tool — Select (move/marquee) vs Hand (pan). */
export type CanvasMode = "select" | "hand";

/** One workbench panel rendered as a node on the canvas. */
export type CanvasPanel = {
  id: string;
  title: string;
  element: React.ReactNode;
  width?: number;
};

/** A spawnable panel type shown as a button in the toolbar palette. */
export type SpawnType = { id: string; label: string };

export type WorkbenchCanvasNodeKind = "panel" | "note" | "rag" | "material";

export type WorkbenchCanvasPosition = {
  x: number;
  y: number;
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
