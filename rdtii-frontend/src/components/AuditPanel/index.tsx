import { useCallback, useEffect, useState } from "react";
import type {
  IndicatorMapping,
  RejectedExtraction,
  ReviewDecision,
  RunUsageSummary,
  Status,
} from "../../types";
import {
  verifyReleaseYear,
  verifyTimestamp,
  type ReleaseYear,
  type TimestampVerification,
} from "../../services/verification";
import { AuditBody } from "./AuditBody";
import { RejectedPanel } from "./RejectedPanel";
import { t } from "../../lib/i18n";
import {
  RDTII_EXCEL_HEADERS,
  downloadBlob,
  exportMappingsExcel,
  mappingsToExcelPreviewRows,
} from "../../services/excelExport";
import { RightDrawer } from "../ui/RightDrawer";
import { UsageSummary } from "../UsageSummary";

const EXPORT_TIMEOUT_MS = 30_000;
const EXPORT_PREVIEW_LIMIT = 5;

function truncateMiddle(value: string, max = 30): string {
  if (value.length <= max) return value;
  return `${value.slice(0, 12)}…${value.slice(-12)}`;
}

/** Document-level facts shared by every quote — Document quality, Release
    year, Source link, Provenance, and Timestamp verification — rendered once
    as bands at the top of the list instead of repeating inside each quote's
    report. Markup/classes copied verbatim from the report so the styling is
    identical. Derived from the first mapping (one document per run). */
function DocumentInfoRows({ mapping }: { mapping: IndicatorMapping }) {
  const features = (mapping.features ?? {}) as Record<string, unknown>;
  const num = (v: unknown) => {
    const n = typeof v === "number" ? v : Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const pdfType = features["_pdf_type"] ?? features["pdf_type"];
  const totalPages = features["total_pages"];
  const ocrPages = features["ocr_pages"];
  const conf = num(features["_ocr_mean_confidence"] ?? features["mean_confidence"]);

  const [year, setYear] = useState<ReleaseYear | null>(null);
  const [timestamp, setTimestamp] = useState<TimestampVerification | null>(null);
  useEffect(() => {
    let alive = true;
    verifyReleaseYear(mapping)
      .then((r) => alive && setYear(r))
      .catch(() => {});
    const existing = mapping.timestamp_verification as unknown as
      | TimestampVerification
      | undefined;
    if (existing && (existing.source_details?.length || existing.verification_log)) {
      setTimestamp(existing);
    } else if (mapping.source_url) {
      verifyTimestamp(mapping.source_url, mapping.last_update ?? "")
        .then((v) => alive && setTimestamp(v))
        .catch(() => {});
    }
    return () => {
      alive = false;
    };
    // Re-resolve only when the document identity changes, not on stream churn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapping.source_legislation, mapping.source_url, mapping.last_update]);

  // ── Provenance (verbatim from the report) ──
  const grade = features["_source_grade"];
  const gradeConfidenceN = (() => {
    const raw = features["_source_grade_confidence"];
    const n = typeof raw === "number" ? raw : Number(raw);
    return Number.isFinite(n) ? Math.round(n * 100) : null;
  })();
  const timeframeStatus = features["_timeframe_status"];
  const timeframeColumn = features["_timeframe_column"];
  const sha = features["source_file_sha256"];
  const pdfPath = features["source_pdf_path"];
  const provenance: { label: string; value: React.ReactNode }[] = [];
  if (grade !== undefined && gradeConfidenceN === null) {
    provenance.push({ label: "Source grade", value: String(grade) });
  }
  if (timeframeStatus !== undefined || timeframeColumn !== undefined) {
    provenance.push({
      label: "Timeframe",
      value: [timeframeColumn, timeframeStatus && `(${timeframeStatus})`]
        .filter(Boolean)
        .join(" "),
    });
  }
  if (typeof sha === "string" && sha) {
    provenance.push({ label: "SHA-256", value: <code title={sha}>{truncateMiddle(sha)}</code> });
  }
  if (typeof pdfPath === "string" && pdfPath) {
    provenance.push({ label: "File", value: <code title={pdfPath}>{truncateMiddle(pdfPath, 40)}</code> });
  }
  // Staleness — document-level (does the dossier still match the live
  // source?). Rendered as its own band, colored by severity.
  const stalenessSeverity =
    features["_staleness_severity"] !== undefined
      ? String(features["_staleness_severity"])
      : null;
  const stalenessReasons = features["_staleness_reasons"]
    ? String(features["_staleness_reasons"])
    : "";
  const stalenessClass =
    stalenessSeverity === null || stalenessSeverity === "none"
      ? "rr-sec-timestamp-ok" // green — fresh
      : stalenessSeverity === "high"
        ? "rr-sec-staleness-high" // red — stale
        : "rr-sec-timestamp-warn"; // yellow — low/medium

  // Reuse the report's band styling (rr-*) so the blocks keep their original
  // look — light-blue quality stat tiles, green release-year band — just
  // hoisted above the result list.
  const pdfTypeStr = pdfType !== undefined ? String(pdfType) : null;
  const stats: { label: string; value: string }[] = [];
  if (pdfTypeStr) stats.push({ label: "Document type", value: pdfTypeStr });
  if (totalPages !== undefined) {
    stats.push({
      label: "OCR coverage",
      value: ocrPages !== undefined ? `${ocrPages}/${totalPages} pp` : `${totalPages} pp`,
    });
  }
  if (conf !== null) stats.push({ label: "OCR confidence", value: `${Math.round(conf * 100)}%` });

  return (
    <div className="reasoning-report doc-info-top select-text">
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

      {year && year.year && (
        <section className="rr-section rr-provenance rr-sec-release">
          <h4>Release year (4 signals · LLM-decided)</h4>
          <div className="rr-provenance-line">
            <span className="rr-provenance-label">{year.year}</span>
            <span className="rr-provenance-value">
              {Math.round(year.confidence * 100)}% · decided by {year.decided_by}
            </span>
          </div>
          {Object.keys(year.candidates).length > 0 && (
            <div className="rr-provenance-line">
              <span className="rr-provenance-label">signals</span>
              <span className="rr-provenance-value">
                {Object.entries(year.candidates)
                  .map(([m, y]) => `${m} ${y}`)
                  .join(", ")}
              </span>
            </div>
          )}
        </section>
      )}

      <section className="rr-section rr-sec-provenance">
        <h4>Source link</h4>
        {mapping.source_url ? (
          <a
            className="doc-info-link"
            href={mapping.source_url}
            target="_blank"
            rel="noreferrer"
            title={mapping.source_url}
          >
            {mapping.source_url}
          </a>
        ) : (
          <span className="rr-provenance-value">—</span>
        )}
      </section>

      {(provenance.length > 0 || gradeConfidenceN !== null) && (
        <section className="rr-section rr-provenance rr-sec-provenance">
          <h4>Provenance</h4>
          {gradeConfidenceN !== null && (
            <div className="rr-batt">
              <div
                className="rr-batt-fill"
                style={{ width: `${gradeConfidenceN}%` }}
              >
                <span className="rr-batt-label">Source grade.</span>
                <span className="rr-batt-value">{gradeConfidenceN}%</span>
              </div>
              {grade !== undefined && (
                <span className="rr-batt-info">{String(grade)}</span>
              )}
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

      {stalenessSeverity !== null && (
        <section className={`rr-section rr-provenance ${stalenessClass}`}>
          <h4>Staleness</h4>
          <div className="rr-provenance-line">
            <span className="rr-provenance-label">{stalenessSeverity}</span>
            {stalenessReasons && (
              <span className="rr-provenance-value">{stalenessReasons}</span>
            )}
          </div>
        </section>
      )}

      {/* Last update — just the resolved date on the yellow band; the
          multi-source verification detail is internal. */}
      {timestamp?.best_date && (
        <section className="rr-section rr-provenance rr-sec-timestamp-warn">
          <h4>Last update</h4>
          <div className="rr-provenance-line">
            <span className="rr-provenance-value">{timestamp.best_date}</span>
          </div>
        </section>
      )}
    </div>
  );
}

type AuditPanelProps = {
  status: Status;
  mappings: IndicatorMapping[];
  exportMappings?: IndicatorMapping[];
  totalMappings: number;
  activeKey: string | null;
  decisions: Record<string, ReviewDecision>;
  selectMapping: (key: string) => void;
  setDecision: (key: string, d: ReviewDecision) => void;
  rejected: RejectedExtraction[];
  showRejected: boolean;
  setShowRejected: (v: boolean) => void;
  country?: string;
  onLoadDemoData?: () => void;
  usage?: RunUsageSummary | null;
};

export function AuditPanel({
  status,
  mappings,
  exportMappings,
  totalMappings,
  activeKey,
  decisions,
  selectMapping,
  setDecision,
  rejected,
  showRejected,
  setShowRejected,
  country = "",
  onLoadDemoData,
  usage,
}: AuditPanelProps) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [showExportPreview, setShowExportPreview] = useState(false);

  // Sort/filter the result list under the top bands. Filter by review status,
  // sort by pillar·indicator (natural order otherwise).
  const [reviewFilter, setReviewFilter] = useState<"all" | "clean" | "review">("all");
  const [sortByPillar, setSortByPillar] = useState(false);
  const cleanCount = mappings.filter((m) => !m.requires_human_review).length;
  const reviewCount = mappings.length - cleanCount;
  const visibleMappings = (() => {
    const filtered =
      reviewFilter === "all"
        ? mappings
        : mappings.filter(
            (m) => (reviewFilter === "clean") === !m.requires_human_review,
          );
    if (!sortByPillar) return filtered;
    return [...filtered].sort(
      (a, b) =>
        a.pillar - b.pillar ||
        String(a.indicator).localeCompare(String(b.indicator), undefined, {
          numeric: true,
        }),
    );
  })();

  const mappingsForExport = exportMappings ?? mappings;
  const previewRows = mappingsToExcelPreviewRows(
    mappingsForExport,
    EXPORT_PREVIEW_LIMIT,
  );

  const handleDownload = useCallback(async () => {
    if (exporting) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      EXPORT_TIMEOUT_MS,
    );
    setExporting(true);
    setExportError("");
    try {
      const result = await exportMappingsExcel(
        {
          mappings: mappingsForExport,
          country,
        },
        { signal: controller.signal },
      );
      downloadBlob(result.blob, result.filename);
    } catch (err) {
      setExportError(exportErrorMessage(err));
    } finally {
      window.clearTimeout(timeout);
      setExporting(false);
    }
  }, [mappingsForExport, country, exporting]);

  const openExportPreview = useCallback(() => {
    setExportError("");
    setShowExportPreview(true);
  }, []);

  const exportPreviewDrawer = (
    <RightDrawer
      open={showExportPreview}
      onOpenChange={setShowExportPreview}
      title={t("audit.exportPreviewTitle")}
      closeLabel={t("audit.exportPreviewCancel")}
      className="export-preview-dialog"
    >
      <div className="export-preview-header">
        <div>
          <h3>{t("audit.exportPreviewTitle")}</h3>
          <p>
            {t("audit.exportPreviewDescription", {
              count: mappingsForExport.length,
            })}
          </p>
        </div>
      </div>
      <div className="export-preview-table-wrap">
        <table className="export-preview-table">
          <thead>
            <tr>
              {RDTII_EXCEL_HEADERS.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewRows.map((row, index) => (
              <tr key={`${row.Indicator}-${index}`}>
                {RDTII_EXCEL_HEADERS.map((header) => (
                  <td key={header}>{row[header]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {mappingsForExport.length > previewRows.length && (
        <p className="export-preview-note">
          {t("audit.exportPreviewTruncated", {
            shown: previewRows.length,
            total: mappingsForExport.length,
          })}
        </p>
      )}
      <div className="export-preview-actions">
        <button
          type="button"
          className="secondary"
          onClick={() => setShowExportPreview(false)}
        >
          {t("audit.exportPreviewCancel")}
        </button>
        <button type="button" onClick={handleDownload} disabled={exporting}>
          {exporting
            ? t("audit.exportExcelLoading")
            : t("audit.exportPreviewConfirm")}
        </button>
      </div>
    </RightDrawer>
  );

  return (
    // Height is content-driven: no max-height cap and no inner scroll box, so
    // the outer frame grows/shrinks with expanded rows. The canvas PanelNode
    // supplies its own scroll container; classic CSS supplies the min-height.
    <section
      className="review-panel swiss-form flex flex-col"
      aria-label={t("audit.aria")}
    >
      <div className="panel-header shrink-0">
        <div>
          <h2>{t("audit.title")}</h2>
          <p>{t("audit.description")}</p>
        </div>
        <div className="nodrag flex items-center gap-2">
          {onLoadDemoData && (
            <button
              type="button"
              className="secondary text-xs"
              onClick={onLoadDemoData}
              title={t("audit.loadDemoTitle")}
            >
              {t("audit.loadDemo")}
            </button>
          )}
          {mappingsForExport.length > 0 && (
            <button
              type="button"
              className="secondary text-xs"
              onClick={openExportPreview}
              title={t("audit.exportPreviewTitle")}
            >
              {t("audit.exportPreviewButton")}
            </button>
          )}
        </div>
      </div>
      {/* usage strip under the title, mirroring the Extract panel's */}
      {usage && (
        <div className="border-t-[1.5px] border-[#111827] px-[18px] py-2.5">
          <UsageSummary usage={usage} />
        </div>
      )}
      {exportPreviewDrawer}
      {exportError && <p className="discovery-error">{exportError}</p>}

      {/* document-level rows above the result list */}
      {mappings.length > 0 && <DocumentInfoRows mapping={mappings[0]} />}

      {/* sort / filter bar — review status + sort by pillar */}
      {mappings.length > 0 && (
        <div className="doc-info-filterbar nodrag">
          {(
            [
              ["all", `ALL (${mappings.length})`],
              ["clean", `✓ CLEAN (${cleanCount})`],
              ["review", `NEEDS REVIEW (${reviewCount})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`doc-info-chip ${reviewFilter === key ? "active" : ""}`}
              onClick={() => setReviewFilter(key)}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            className={`doc-info-chip doc-info-sort ${sortByPillar ? "active" : ""}`}
            title="Sort results by pillar · indicator"
            onClick={() => setSortByPillar((v) => !v)}
          >
            ↕ PILLAR
          </button>
        </div>
      )}

      <div>
        <AuditBody
          status={status}
          mappings={visibleMappings}
          totalMappings={totalMappings}
          activeKey={activeKey}
          decisions={decisions}
          selectMapping={selectMapping}
          setDecision={setDecision}
        />

        {rejected.length > 0 && (
          <RejectedPanel
            rejected={rejected}
            open={showRejected}
            setOpen={setShowRejected}
          />
        )}
      </div>
    </section>
  );
}

function exportErrorMessage(err: unknown): string {
  if (err instanceof Error && err.name === "AbortError") {
    return t("audit.exportExcelTimeout");
  }
  return err instanceof Error ? err.message : t("audit.exportExcelFailed");
}
