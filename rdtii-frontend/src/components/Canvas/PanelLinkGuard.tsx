import type React from "react";
import { Unlink } from "lucide-react";

/**
 * Gates a panel's content behind its data wire. While `connected` is true the
 * children render normally; when the edge is deleted the content dims and an
 * overlay explains how to restore it. Content stays mounted so panel state
 * survives a reconnect.
 */
export function PanelLinkGuard({
  connected,
  upstreamLabel,
  panelLabel,
  children,
}: {
  connected: boolean;
  upstreamLabel: string;
  panelLabel: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ position: "relative", height: "100%" }}>
      <div
        style={
          connected
            ? undefined
            : { filter: "blur(2px) grayscale(0.6)", opacity: 0.45, pointerEvents: "none", userSelect: "none" }
        }
        aria-hidden={!connected}
      >
        {children}
      </div>

      {!connected && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            padding: 24,
            textAlign: "center",
            background: "rgba(255,255,255,0.55)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: "#fef3c7",
              color: "#92400e",
            }}
          >
            <Unlink size={20} />
          </div>
          <p style={{ fontSize: "0.85rem", fontWeight: 700, color: "#1f2933", margin: 0 }}>
            {panelLabel} is disconnected
          </p>
          <p style={{ fontSize: "0.75rem", color: "#5a6573", margin: 0, maxWidth: 280 }}>
            Draw a link from <strong>{upstreamLabel}</strong> to <strong>{panelLabel}</strong> to
            resume showing results.
          </p>
        </div>
      )}
    </div>
  );
}
