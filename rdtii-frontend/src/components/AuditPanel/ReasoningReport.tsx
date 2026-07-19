import { AlertTriangle, Check, X as XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import type { IndicatorMapping } from "../../types";
import {
  verifyReleaseYear,
  verifyTimestamp,
  type ReleaseYear,
  type TimestampVerification,
} from "../../services/verification";

/**
 * Grouped, scannable view of everything the pipeline computed for one
 * mapping: validation flags as callouts, document quality as stat tiles,
 * scoring features as value-chip rows, provenance as a muted footer.
 */

type FeatureValue = boolean | number | string;

// Document/OCR quality metadata merged into `features` by the extraction
// pipeline (scalar pdf_metadata) — context, not scoring inputs.
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

// Reproducibility / source-grading provenance.
const PROVENANCE_KEYS = new Set([
  "source_file_sha256",
  "source_pdf_path",
  "_source_grade",
  "_source_grade_confidence",
  "_timeframe_status",
  "_timeframe_column",
]);

function firstValue(features: Record<string, FeatureValue>, ...keys: string[]): FeatureValue | undefined {
  for (const key of keys) {
    if (key in features) return features[key];
  }
  return undefined;
}

function asPercent(value: FeatureValue | undefined): string | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : null;
}

function truncateMiddle(value: string, max = 30): string {
  if (value.length <= max) return value;
  return `${value.slice(0, 12)}…${value.slice(-12)}`;
}

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

  // Mirrors the TUI report: release year (4 signals, LLM-decided) + forensic
  // timestamp, resolved on demand.
  const [releaseYear, setReleaseYear] = useState<ReleaseYear | null>(null);
  const [timestamp, setTimestamp] = useState<TimestampVerification | null>(null);
  useEffect(() => {
    let alive = true;
    verifyReleaseYear(mapping)
      .then((r) => alive && setReleaseYear(r))
      .catch(() => {});
    const existing = mapping.timestamp_verification as unknown as
      | TimestampVerification
      | undefined;
    if (existing && (existing.source_details?.length || existing.verification_log)) {
      setTimestamp(existing);
    } else if (mapping.source_url) {
      verifyTimestamp(mapping.source_url, mapping.last_update ?? "")
        .then((t) => alive && setTimestamp(t))
        .catch(() => {});
    }
    return () => {
      alive = false;
    };
  }, [mapping]);

  const scoringEntries = Object.entries(features).filter(
    ([k]) => !DOC_QUALITY_KEYS.has(k) && !PROVENANCE_KEYS.has(k),
  );
  const flags = mapping.requires_human_review ? mapping.flag_reasons ?? [] : [];

  // ── Document quality stat tiles ──
  const pdfType = firstValue(features, "_pdf_type", "pdf_type");
  const ocrConfidence = asPercent(firstValue(features, "_ocr_mean_confidence", "mean_confidence"));
  const totalPages = firstValue(features, "total_pages");
  const ocrPages = firstValue(features, "ocr_pages");
  const stats: { label: string; value: string }[] = [];
  if (pdfType !== undefined) stats.push({ label: "Document type", value: String(pdfType) });
  if (totalPages !== undefined) {
    stats.push({
      label: "OCR coverage",
      value: ocrPages !== undefined ? `${ocrPages}/${totalPages} pp` : `${totalPages} pp`,
    });
  }
  if (ocrConfidence) stats.push({ label: "OCR confidence", value: ocrConfidence });

  // ── Provenance footer rows ──
  const grade = firstValue(features, "_source_grade");
  // Numeric grade confidence (0-100) for the big percent display + color fill.
  const gradeConfidenceN = (() => {
    const raw = firstValue(features, "_source_grade_confidence");
    const n = typeof raw === "number" ? raw : Number(raw);
    return Number.isFinite(n) ? Math.round(n * 100) : null;
  })();
  const timeframeStatus = firstValue(features, "_timeframe_status");
  const timeframeColumn = firstValue(features, "_timeframe_column");
  const sha = firstValue(features, "source_file_sha256");
  const pdfPath = firstValue(features, "source_pdf_path");
  const provenance: { label: string; value: React.ReactNode }[] = [];
  if (grade !== undefined) {
    provenance.push({ label: "Source grade", value: String(grade) });
  }
  if (timeframeStatus !== undefined || timeframeColumn !== undefined) {
    provenance.push({
      label: "Timeframe",
      value: [timeframeColumn, timeframeStatus && `(${timeframeStatus})`].filter(Boolean).join(" "),
    });
  }
  if (typeof sha === "string" && sha) {
    provenance.push({ label: "SHA-256", value: <code title={sha}>{truncateMiddle(sha)}</code> });
  }
  if (typeof pdfPath === "string" && pdfPath) {
    provenance.push({ label: "File", value: <code title={pdfPath}>{truncateMiddle(pdfPath, 40)}</code> });
  }

  return (
    <div className="reasoning-report select-text">
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

      {stats.length > 0 && (
        <section className="rr-section rr-sec-quality">
          <h4>Document quality</h4>
          <div className="rr-stat-grid">
            {stats.map((s) => (
              <div key={s.label} className="rr-stat">
                <span className="rr-stat-value">{s.value}</span>
                <span className="rr-stat-label">{s.label}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {provenance.length > 0 && (
        <section className="rr-section rr-provenance rr-sec-provenance">
          <h4>Provenance</h4>
          {gradeConfidenceN !== null && (
            <div
              className="rr-percent"
              style={{ "--pct": `${gradeConfidenceN}%` } as React.CSSProperties}
            >
              <span className="rr-percent-value">{gradeConfidenceN}%</span>
              <span className="rr-percent-label">source-grade confidence</span>
            </div>
          )}
          {provenance.map((row) => (
            <div key={row.label} className="rr-provenance-line">
              <span className="rr-provenance-label">{row.label}</span>
              <span className="rr-provenance-value">{row.value}</span>
            </div>
          ))}
        </section>
      )}

      {releaseYear && releaseYear.year && (
        <section className="rr-section rr-provenance rr-sec-release">
          <h4>Release year (4 signals · LLM-decided)</h4>
          <div className="rr-provenance-line">
            <span className="rr-provenance-label">{releaseYear.year}</span>
            <span className="rr-provenance-value">
              {Math.round(releaseYear.confidence * 100)}% · decided by{" "}
              {releaseYear.decided_by}
            </span>
          </div>
          {Object.keys(releaseYear.candidates).length > 0 && (
            <div className="rr-provenance-line">
              <span className="rr-provenance-label">signals</span>
              <span className="rr-provenance-value">
                {Object.entries(releaseYear.candidates)
                  .map(([m, y]) => `${m} ${y}`)
                  .join(", ")}
              </span>
            </div>
          )}
        </section>
      )}

      {timestamp && (
        <section
          className={`rr-section rr-provenance ${timestamp.verified ? "rr-sec-timestamp-ok" : "rr-sec-timestamp-warn"}`}
        >
          <h4>Timestamp verification (forensic)</h4>
          <div className="rr-provenance-line">
            <span className="rr-provenance-label">
              {timestamp.verified ? "✓ corroborated" : "unconfirmed"}
            </span>
            <span className="rr-provenance-value">
              best date {timestamp.best_date || "—"}
            </span>
          </div>
          {timestamp.source_details.map((s, i) => (
            <div key={i} className="rr-provenance-line">
              <span className="rr-provenance-label">{s.source}</span>
              <span className="rr-provenance-value">
                {s.date || "—"} ({s.status})
              </span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
