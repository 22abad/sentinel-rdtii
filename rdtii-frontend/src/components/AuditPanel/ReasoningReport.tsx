import { AlertTriangle, Check, X as XIcon } from "lucide-react";
import { formatScore, scoreClass } from "../../lib/utils";
import type { IndicatorMapping } from "../../types";

/**
 * Per-MAPPING view: score, review flags, provision, scoring features.
 * Document-level identity (source grade, timeframe, staleness, release
 * year, timestamp, OCR quality) lives in DocumentDossier — consolidated
 * once per document, never repeated (or contradicted) per card.
 */

type FeatureValue = boolean | number | string;

// Document/OCR quality metadata merged into `features` by the extraction
// pipeline (scalar pdf_metadata) — shown in the DocumentDossier, not here.
const DOC_QUALITY_KEYS = new Set([
  "mean_confidence",
  "ocr_ratio",
  "pdf_type",
  "total_pages",
  "ocr_pages",
  "text_pages",
  "_ocr_mean_confidence",
  "_ocr_ratio",
  "_pdf_type",
]);

// Reproducibility / source-grading / staleness provenance — document-level,
// shown in the DocumentDossier.
const PROVENANCE_KEYS = new Set([
  "source_file_sha256",
  "source_pdf_path",
  "_source_grade",
  "_source_grade_confidence",
  "_timeframe_status",
  "_timeframe_column",
  "_staleness_reasons",
  "_staleness_severity",
]);

/** Human label from a snake_case feature key. */
function humanize(key: string): string {
  return key.replace(/^_/, "").replace(/_/g, " ");
}

function FeatureChip({ value }: { value: FeatureValue }) {
  if (typeof value === "boolean" || value === "true" || value === "false") {
    const yes = value === true || value === "true";
    return (
      <span className={`rr-chip ${yes ? "rr-chip-yes" : "rr-chip-no"}`}>
        {yes ? <Check size={13} strokeWidth={3} /> : <XIcon size={13} strokeWidth={3} />}
        {yes ? "yes" : "no"}
      </span>
    );
  }
  return <span className="rr-chip rr-chip-neutral">{String(value)}</span>;
}

export function ReasoningReport({ mapping }: { mapping: IndicatorMapping }) {
  const features = mapping.features ?? {};

  const scoringEntries = Object.entries(features).filter(
    ([k]) => !DOC_QUALITY_KEYS.has(k) && !PROVENANCE_KEYS.has(k),
  );
  const flags = mapping.requires_human_review ? mapping.flag_reasons ?? [] : [];

  return (
    <div className="reasoning-report select-text">
      {/* Score card at the top: Batteristatus-style — the fill spans the
          0–1 range (score 1 = fully filled), colored by score tier. */}
      <section className="rr-section rr-sec-score">
        <div className="rr-batt">
          <div
            className={`rr-batt-fill rr-score-fill-${scoreClass(mapping.score)}`}
            style={{ width: `${mapping.score * 100}%` }}
          >
            <span className="rr-batt-label">Score.</span>
            <span className="rr-batt-value">{formatScore(mapping.score)}</span>
          </div>
          <span className="rr-batt-info">0 – 1</span>
        </div>
      </section>

      {flags.length > 0 && (
        <div className="rr-callout">
          <div className="rr-callout-title">
            <AlertTriangle size={15} />
            Flagged for human review
          </div>
          <ul>
            {flags.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {mapping.quote_context &&
        mapping.quote_context.trim() !== mapping.verbatim_quote.trim() && (
          <section className="rr-section rr-sec-provision">
            <h4>Provision</h4>
            <p className="rr-provision">
              {(() => {
                const ctx = mapping.quote_context as string;
                const q = mapping.verbatim_quote;
                const i = ctx.indexOf(q);
                if (i < 0) return ctx;
                return (
                  <>
                    <span className="rr-provision-context">{ctx.slice(0, i)}</span>
                    <mark className="rr-provision-quote">{q}</mark>
                    <span className="rr-provision-context">{ctx.slice(i + q.length)}</span>
                  </>
                );
              })()}
            </p>
          </section>
        )}

      {scoringEntries.length > 0 && (
        <section className="rr-section rr-sec-scoring">
          <h4>Scoring inputs</h4>
          <div className="rr-feature-list">
            {scoringEntries.map(([k, v]) => (
              <div key={k} className="rr-feature-line">
                <span className="rr-feature-name">{humanize(k)}</span>
                <FeatureChip value={v} />
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
