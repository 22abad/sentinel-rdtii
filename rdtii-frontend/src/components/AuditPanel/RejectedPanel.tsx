import type { RejectedExtraction } from "../../types";
import { t } from "../../lib/i18n";

type RejectedPanelProps = {
  rejected: RejectedExtraction[];
  open: boolean;
  setOpen: (v: boolean) => void;
};

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
          <li key={i} className="rejected-item">
            <div className="rejected-reason">{r.reason}</div>
            {r.candidate_indicator ? (
              <div className="rejected-reason">
                Candidate {r.candidate_indicator} · decision {r.decision ?? "insufficient"}
                {r.supported_indicators?.length
                  ? ` · verifier supported ${r.supported_indicators.join(", ")}`
                  : " · verifier supported NONE"}
              </div>
            ) : null}
            {r.exclusion_reasons?.length ? (
              <ul>
                {r.exclusion_reasons.map((reason, reasonIndex) => (
                  <li key={reasonIndex}>{reason}</li>
                ))}
              </ul>
            ) : null}
            {r.chunk_preview ? (
              <pre className="rejected-preview">{r.chunk_preview}</pre>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
