import { useCallback, useState } from "react";
import type {
  IndicatorMapping,
  RejectedExtraction,
  ReviewDecision,
  RunUsageSummary,
  Status,
} from "../../types";
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
  // Demo-critical triage: jump straight to the rows that DON'T need a human
  // ("clean") or the flagged ones, instead of scanning the whole list.
  const [reviewFilter, setReviewFilter] = useState<"all" | "clean" | "review">("all");
  const cleanCount = mappings.filter((m) => !m.requires_human_review).length;
  const reviewCount = mappings.length - cleanCount;
  const reviewFiltered =
    reviewFilter === "all"
      ? mappings
      : mappings.filter((m) => (reviewFilter === "clean") === !m.requires_human_review);
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

      {mappings.length > 0 && (
        <div className="nodrag flex items-center gap-1.5 border-t-[1.5px] border-[#111827] px-[18px] py-2">
          {([
            ["all", `ALL (${mappings.length})`],
            ["clean", `✓ CLEAN (${cleanCount})`],
            ["review", `NEEDS REVIEW (${reviewCount})`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setReviewFilter(key)}
              style={{
                minHeight: 26, padding: "2px 10px", borderRadius: 0, cursor: "pointer",
                border: "1.5px solid #111827",
                fontSize: "0.66rem", fontWeight: 700, letterSpacing: "0.04em",
                background: reviewFilter === key ? "#111827" : "transparent",
                color: reviewFilter === key ? "#fff" : "#111827",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <div>
        <AuditBody
          status={status}
          mappings={reviewFiltered}
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
