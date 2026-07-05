import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

type RightDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  closeLabel?: string;
  className?: string;
  children: ReactNode;
};

export function RightDrawer({
  open,
  onOpenChange,
  title,
  closeLabel = `Close ${title}`,
  className,
  children,
}: RightDrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="right-drawer-backdrop" />
        <Dialog.Content className={cn("right-drawer", className)}>
          <Dialog.Title className="sr-only">{title}</Dialog.Title>
          <Dialog.Close className="right-drawer-close" aria-label={closeLabel}>
            <X size={18} strokeWidth={2.15} />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
