import { ChevronRight } from "lucide-react";
import { useState } from "react";
import type { RunUsageSummary } from "../types";
import { t } from "../lib/i18n";
import { RightDrawer } from "./ui/RightDrawer";

function compactNumber(value: number) {
  return new Intl.NumberFormat(undefined, {
    notation: value >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

function preciseNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatCost(value: number) {
  return `$${value.toFixed(value >= 0.01 ? 3 : 5)}`;
}

function operationLabel(value: string) {
  return value.replace(/_/g, " ");
}

export function UsageSummary({
  usage,
  className = "",
}: {
  usage: RunUsageSummary;
  className?: string;
}) {
  // Session-style presentation inspired by OpenCode: keep usage attached to
  // the extraction result and show a compact summary instead of writing a
  // separate report file for every run. This component is independently built.
  const [open, setOpen] = useState(false);
  const knownTokens = usage.known_input_tokens + usage.known_output_tokens;
  const tokenUsageComplete = usage.calls_with_unknown_usage === 0;
  const tokenValue = `${compactNumber(knownTokens)}${tokenUsageComplete ? "" : "+"}`;
  const preciseTokenValue = `${preciseNumber(knownTokens)}${tokenUsageComplete ? "" : "+"}`;
  const costComplete = usage.cost_usd !== null;
  const costValue = usage.cost_usd !== null
    ? formatCost(usage.cost_usd)
    : usage.known_cost_usd > 0
      ? `${formatCost(usage.known_cost_usd)}+`
      : t("audit.usage.costUnavailable");
  const wallClockSeconds = (usage.wall_clock_ms / 1000).toFixed(1);
  const modelSeconds = (usage.latency_sum_ms / 1000).toFixed(1);
  const operations = Object.entries(usage.operations);

  return (
    <>
      <button
        type="button"
        className={`usage-summary-trigger nodrag ${className}`}
        onClick={() => setOpen(true)}
        aria-label={t("audit.usage.openDetails")}
      >
        <span className="usage-summary-trigger-label">{t("audit.usage.title")}</span>
        <span>{t("audit.usage.tokens", { count: tokenValue })}</span>
        <span aria-hidden="true">·</span>
        <span>{costValue}</span>
        <span aria-hidden="true">·</span>
        <span>{t("audit.usage.seconds", { count: wallClockSeconds })}</span>
        <ChevronRight size={14} aria-hidden="true" />
      </button>

      <RightDrawer
        open={open}
        onOpenChange={setOpen}
        title={t("audit.usage.title")}
        closeLabel={t("audit.usage.closeDetails")}
        className="usage-drawer"
      >
        <div className="usage-drawer-content">
          <header className="usage-drawer-header">
            <p>{t("audit.usage.eyebrow")}</p>
            <h3>{t("audit.usage.title")}</h3>
            <span>{t("audit.usage.description")}</span>
          </header>

          <div className="usage-metric-grid">
            <div className="usage-metric usage-metric-primary">
              <span>{t("audit.usage.totalTokens")}</span>
              <strong>{preciseTokenValue}</strong>
            </div>
            <div className="usage-metric">
              <span>{t("audit.usage.estimatedCost")}</span>
              <strong>{costValue}</strong>
            </div>
            <div className="usage-metric">
              <span>{t("audit.usage.modelCalls")}</span>
              <strong>{preciseNumber(usage.llm_calls)}</strong>
            </div>
            <div className="usage-metric">
              <span>{t("audit.usage.elapsedTime")}</span>
              <strong>{t("audit.usage.seconds", { count: wallClockSeconds })}</strong>
            </div>
          </div>

          <section className="usage-drawer-section">
            <h4>{t("audit.usage.tokenBreakdown")}</h4>
            <dl className="usage-detail-list">
              <div>
                <dt>{t("audit.usage.inputTokens")}</dt>
                <dd>{usage.input_tokens === null ? `${preciseNumber(usage.known_input_tokens)}+` : preciseNumber(usage.input_tokens)}</dd>
              </div>
              <div>
                <dt>{t("audit.usage.outputTokens")}</dt>
                <dd>{usage.output_tokens === null ? `${preciseNumber(usage.known_output_tokens)}+` : preciseNumber(usage.output_tokens)}</dd>
              </div>
            </dl>
          </section>

          <section className="usage-drawer-section">
            <h4>{t("audit.usage.callDetails")}</h4>
            <dl className="usage-detail-list">
              <div>
                <dt>{t("audit.usage.successfulCalls")}</dt>
                <dd>{usage.successful_calls}</dd>
              </div>
              <div>
                <dt>{t("audit.usage.failedCalls")}</dt>
                <dd>{usage.failed_calls}</dd>
              </div>
              <div>
                <dt>{t("audit.usage.modelTime")}</dt>
                <dd>{t("audit.usage.seconds", { count: modelSeconds })}</dd>
              </div>
              {usage.calls_with_unknown_usage > 0 && (
                <div>
                  <dt>{t("audit.usage.unknownCalls")}</dt>
                  <dd>{usage.calls_with_unknown_usage}</dd>
                </div>
              )}
            </dl>
          </section>

          {operations.length > 0 && (
            <section className="usage-drawer-section">
              <h4>{t("audit.usage.operations")}</h4>
              <div className="usage-operation-list">
                {operations.map(([name, count]) => (
                  <div key={name}>
                    <span>{operationLabel(name)}</span>
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
            </section>
          )}

          <p className="usage-cost-note">
            {!tokenUsageComplete
              ? t("audit.usage.partialNote")
              : costComplete
                ? t("audit.usage.costNote")
                : t("audit.usage.costUnavailableNote")}
          </p>
        </div>
      </RightDrawer>
    </>
  );
}
