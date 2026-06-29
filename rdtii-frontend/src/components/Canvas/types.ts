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
