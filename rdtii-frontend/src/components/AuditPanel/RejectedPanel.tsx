import { useState } from "react";
import type { RejectedExtraction } from "../../types";
import { t } from "../../lib/i18n";

type RejectedPanelProps = {
  rejected: RejectedExtraction[];
  open: boolean;
  setOpen: (v: boolean) => void;
};

/** One rejection as an accordion index row — same layout as the mapping
    rows (code · reason · +), in the rejection red. */
function RejectedRow({ r }: { r: RejectedExtraction }) {
  const [open, setOpen] = useState(false);
  return (
    <li className={`mapping-row rejected-row ${open ? "open" : ""}`}>
      <button
        type="button"
        className="mapping-row-head nodrag"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mapping-row-code">
          {r.candidate_indicator ? `P${r.candidate_indicator}` : "—"}
        </span>
        <span className="mapping-row-title" title={r.reason}>
          {r.reason}
        </span>
        <span className="mapping-row-plus" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>

      {open && (
        <div className="mapping-row-body select-text">
          {r.candidate_indicator ? (
            <div className="mapping-row-meta">
              <span>decision {r.decision ?? "insufficient"}</span>
              <span>
                {r.supported_indicators?.length
                  ? `verifier supported ${r.supported_indicators.join(", ")}`
                  : "verifier supported none"}
              </span>
            </div>
          ) : null}

          {r.exclusion_reasons?.length ? (
            <section className="mapping-row-block">
              <h4>Exclusion reasons</h4>
              <ul className="rejected-exclusions">
                {r.exclusion_reasons.map((reason, reasonIndex) => (
                  <li key={reasonIndex}>{reason}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {r.chunk_preview ? (
            <section className="mapping-row-block">
              <h4>Raw material</h4>
              <pre className="rejected-preview">{r.chunk_preview}</pre>
            </section>
          ) : null}
        </div>
      )}
    </li>
  );
}

export function RejectedPanel({ rejected, open, setOpen }: RejectedPanelProps) {
  return (
    <details
      className="rejected-panel"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary>{t("rejected.summary", { count: rejected.length })}</summary>
      <ul>
        {rejected.map((r, i) => (
          <RejectedRow key={i} r={r} />
        ))}
      </ul>
    </details>
  );
}
