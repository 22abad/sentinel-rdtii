import type React from "react";

import type { FileNodeData } from "./FileNode";

export type Wardrobe = {
  files: FileNodeData;
  element: React.ReactNode;
  width?: number;
  transparent?: boolean;
  onDelete: () => void;
};
