import { formatFeatureValue } from "../../lib/utils";
import type { IndicatorMapping } from "../../types";

/**
 * Grouped, human-readable view of everything the pipeline computed for one
 * mapping: the LLM's scoring features, validation flags, document/OCR
 * quality, and source provenance — instead of a flat feature-chip dump.
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

function pick(features: Record<string, FeatureValue>, keys: Set<string>) {
  return Object.entries(features).filter(([k]) => keys.has(k));
}

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

function truncateMiddle(value: string, max = 26): string {
  if (value.length <= max) return value;
  return `${value.slice(0, 10)}…${value.slice(-10)}`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="reasoning-section">
      <h4>{title}</h4>
      {children}
    </div>
  );
}

function KeyValueTable({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <table className="reasoning-table">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ReasoningReport({ mapping }: { mapping: IndicatorMapping }) {
  const features = mapping.features ?? {};

  const scoringEntries = Object.entries(features).filter(
    ([k]) => !DOC_QUALITY_KEYS.has(k) && !PROVENANCE_KEYS.has(k),
  );

  // ── Document quality (humanized) ──
  const pdfType = firstValue(features, "_pdf_type", "pdf_type");
  const ocrConfidence = asPercent(firstValue(features, "_ocr_mean_confidence", "mean_confidence"));
  const totalPages = firstValue(features, "total_pages");
  const ocrPages = firstValue(features, "ocr_pages");
  const docRows: [string, React.ReactNode][] = [];
  if (pdfType !== undefined) docRows.push(["Document type", String(pdfType)]);
  if (totalPages !== undefined) {
    docRows.push([
      "OCR coverage",
      ocrPages !== undefined ? `${ocrPages}/${totalPages} pages` : `${totalPages} pages`,
    ]);
  }
  if (ocrConfidence) docRows.push(["OCR confidence", ocrConfidence]);

  // ── Source provenance ──
  const grade = firstValue(features, "_source_grade");
  const gradeConfidence = asPercent(firstValue(features, "_source_grade_confidence"));
  const timeframeStatus = firstValue(features, "_timeframe_status");
  const timeframeColumn = firstValue(features, "_timeframe_column");
  const sha = firstValue(features, "source_file_sha256");
  const pdfPath = firstValue(features, "source_pdf_path");
  const provenanceRows: [string, React.ReactNode][] = [];
  if (grade !== undefined) {
    provenanceRows.push([
      "Source grade",
      gradeConfidence ? `${grade} (${gradeConfidence} confidence)` : String(grade),
    ]);
  }
  if (timeframeStatus !== undefined || timeframeColumn !== undefined) {
    provenanceRows.push([
      "Timeframe",
      [timeframeColumn, timeframeStatus && `(${timeframeStatus})`].filter(Boolean).join(" "),
    ]);
  }
  if (typeof sha === "string" && sha) {
    provenanceRows.push(["File SHA-256", <code title={sha}>{truncateMiddle(sha)}</code>]);
  }
  if (typeof pdfPath === "string" && pdfPath) {
    provenanceRows.push(["Source file", <code title={pdfPath}>{truncateMiddle(pdfPath, 34)}</code>]);
  }

  return (
    <div className="reasoning-report select-text">
      {mapping.requires_human_review && (mapping.flag_reasons?.length ?? 0) > 0 && (
        <Section title="Validation flags">
          <ul className="reasoning-flags">
            {mapping.flag_reasons?.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </Section>
      )}

      {scoringEntries.length > 0 && (
        <Section title="Indicator features (scoring inputs)">
          <KeyValueTable
            rows={scoringEntries.map(([k, v]) => [k, formatFeatureValue(v)] as [string, React.ReactNode])}
          />
        </Section>
      )}

      {docRows.length > 0 && (
        <Section title="Document quality">
          <KeyValueTable rows={docRows} />
        </Section>
      )}

      {provenanceRows.length > 0 && (
        <Section title="Source provenance">
          <KeyValueTable rows={provenanceRows} />
        </Section>
      )}
    </div>
  );
}
