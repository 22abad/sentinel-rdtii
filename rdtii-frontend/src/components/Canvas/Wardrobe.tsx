import React from "react"";
import { Trash2 } from "lucide-react";

export type Wardrobe = {
  files: FileNode;
  element: React.ReactNode;
  width?: number;
  transparent?: boolean;
  onDelete: () => void;
};
