import type React from "react";
import type { WorkbenchCanvasNodeKind, WorkbenchCanvasSize } from "./types";

export const PANEL_MIN_SIZE = { width: 320, height: 160 };
export const NOTE_MIN_SIZE = { width: 180, height: 140 };
export const FILE_MIN_SIZE = { width: 220, height: 110 };

export const RESIZER_HANDLE_STYLE: React.CSSProperties = {
  width: 9,
  height: 9,
  border: "2px solid #ffffff",
  borderRadius: 9999,
};

export const RESIZER_LINE_STYLE: React.CSSProperties = {
  borderColor: "#10B981",
  borderRadius: 28,
  borderWidth: 1,
};

export function minSizeForNode(kind: WorkbenchCanvasNodeKind) {
  if (kind === "note") return NOTE_MIN_SIZE;
  return PANEL_MIN_SIZE;
}

export function clampSize(size: WorkbenchCanvasSize, minSize: Required<WorkbenchCanvasSize>): WorkbenchCanvasSize {
  return {
    width: size.width == null ? undefined : Math.max(minSize.width, size.width),
    height: size.height == null ? undefined : Math.max(minSize.height, size.height),
  };
}

export function hasCustomSize(size?: WorkbenchCanvasSize) {
  return size?.width != null || size?.height != null;
}
