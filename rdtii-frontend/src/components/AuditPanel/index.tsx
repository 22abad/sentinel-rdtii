import { useCallback, useState } from "react";
import type {
  IndicatorMapping,
  RejectedExtraction,
  ReviewDecision,
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
}: AuditPanelProps) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [showExportPreview, setShowExportPreview] = useState(false);
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
    <section
      className="review-panel self-start flex flex-col max-h-[calc(100vh-40px)]"
      aria-label={t("audit.aria")}
    >
      <div className="panel-header shrink-0">
        <div>
          <h2>{t("audit.title")}</h2>
          <p>{t("audit.description")}</p>
        </div>
        <div className="flex items-center gap-2">
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
      {exportPreviewDrawer}
      {exportError && <p className="discovery-error">{exportError}</p>}

      <div className="flex-1 overflow-y-auto min-h-0">
        <AuditBody
          status={status}
          mappings={mappings}
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
