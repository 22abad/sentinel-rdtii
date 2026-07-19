import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";

/**
 * Stacked file cards with the ChatInput's spring choreography: collapsed
 * cards peek behind the front one; a pill toggle fans them out. Shared by
 * the chat bar's upload queue and the session node's document tray.
 */

export const CARD_H = 56;
export const CARD_GAP = 10;

export function extColor(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "#ef4444";
  if (["txt", "md"].includes(ext)) return "#3b82f6";
  if (["jpg", "jpeg", "png"].includes(ext)) return "#8b5cf6";
  return "#10B981";
}

export function extLabel(filename: string): string {
  return filename.split(".").pop()?.toUpperCase() ?? "FILE";
}

export type FileCardItem = {
  id: string;
  name: string;
  subtitle?: string;
  /** Right-side controls (remove / unlink / delete …). */
  actions?: React.ReactNode;
};

export function FileCardStack({ items }: { items: FileCardItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const n = items.length;
  const peek = Math.min(n - 1, 2); // ghost cards peeking behind the front one
  const collapsedH = n === 0 ? 0 : CARD_H + peek * 8;
  const expandedH = n === 0 ? 0 : n * CARD_H + (n - 1) * CARD_GAP;
  const containerH = expanded ? expandedH : collapsedH;

  if (n === 0) return null;

  return (
    // Bottom padding keeps the toggle's drop shadow inside ancestor clips.
    <div style={{ display: "flex", flexDirection: "column", gap: 0, paddingBottom: 12 }}>
      {/* Stacked cards area */}
      <div
        style={{
          position: "relative",
          width: "100%",
          height: containerH,
          transition: "height 0.35s cubic-bezier(0.4,0,0.2,1)",
        }}
      >
        <AnimatePresence>
          {items.map((item, i) => {
            const color = extColor(item.name);
            const label = extLabel(item.name);
            const expandedY = i * (CARD_H + CARD_GAP);
            const translateY = expanded ? expandedY : i * 8;
            const scale = expanded ? 1 : Math.max(1 - i * 0.04, 0.88);
            const opacity = expanded ? 1 : i > 2 ? 0 : 1 - i * 0.15;

            return (
              <motion.div
                key={item.id}
                style={{ position: "absolute", left: 0, right: 0, height: CARD_H, zIndex: n - i }}
                initial={{ x: 40, opacity: 0 }}
                animate={{ x: 0, y: translateY, scale, opacity }}
                exit={{ x: 60, opacity: 0, transition: { duration: 0.2, ease: "easeIn" } }}
                transition={{ type: "spring", stiffness: 260, damping: 26, delay: expanded ? i * 0.04 : (n - 1 - i) * 0.04 }}
              >
                <div style={{ height: "100%", background: "#f3f1ea", border: "1.5px solid #111827", borderRadius: 0, padding: "10px 14px", display: "flex", alignItems: "center", gap: 12, boxShadow: "none" }}>
                  <div style={{ width: 36, height: 36, borderRadius: 0, background: color, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontSize: "0.6rem", fontWeight: 800, color: "#fff" }}>{label}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#1f2933", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.name}</div>
                    {item.subtitle ? (
                      <div style={{ fontSize: "0.7rem", color: "#9ca3af", marginTop: 1 }}>{item.subtitle}</div>
                    ) : null}
                  </div>
                  {item.actions}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Expand / collapse toggle */}
      {n > 1 && (
        <motion.button
          type="button"
          className="nodrag"
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((v) => !v);
          }}
          style={{
            marginTop: 10,
            alignSelf: "center",
            position: "relative",
            minHeight: 0,
            padding: "8px 36px 8px 20px",
            background: "#f3f1ea",
            borderRadius: 0,
            border: "1.5px solid #111827",
            boxShadow: "none",
            fontSize: "0.75rem",
            fontWeight: 600,
            color: "#1f2933",
            cursor: "pointer",
          }}
          whileHover={{ y: -2 }}
          whileTap={{ scale: 0.97 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          layout
        >
          {expanded ? "Collapse" : `Show all ${n} file${n !== 1 ? "s" : ""}`}
          <motion.span
            style={{
              position: "absolute",
              right: 14,
              top: "50%",
              marginTop: -5,
              width: 7,
              height: 7,
              borderTop: "2px solid #1f2933",
              borderLeft: "2px solid #1f2933",
              display: "block",
            }}
            initial={false}
            animate={{ rotate: expanded ? 45 : 225, y: expanded ? 2 : -2 }}
            transition={{ duration: 0.3, ease: "linear" }}
          />
        </motion.button>
      )}
    </div>
  );
}
