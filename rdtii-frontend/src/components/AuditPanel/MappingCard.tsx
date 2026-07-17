import { useState } from "react";
import { QUOTE_TRUNCATE } from "../../lib/constants";
import { formatScore, scoreClass } from "../../lib/utils";
import { t } from "../../lib/i18n";
import type { IndicatorMapping, ReviewDecision } from "../../types";
import { ReasoningReport } from "./ReasoningReport";
import { RightDrawer } from "../ui/RightDrawer";

type MappingCardProps = {
  mapping: IndicatorMapping;
  mappingKeyStr: string;
  active: boolean;
  decision: ReviewDecision;
  onSelect: () => void;
  onDecision: (d: ReviewDecision) => void;
};

export function MappingCard({
  mapping,
  mappingKeyStr,
  active,
  decision,
  onSelect,
  onDecision,
}: MappingCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const hasReport =
    Object.keys(mapping.features ?? {}).length > 0 ||
    (mapping.flag_reasons?.length ?? 0) > 0;

  const quoteIsLong = mapping.verbatim_quote.length > QUOTE_TRUNCATE;
  const visibleQuote =
    quoteIsLong && !expanded
      ? `${mapping.verbatim_quote.slice(0, QUOTE_TRUNCATE)}…`
      : mapping.verbatim_quote;

  return (
    <li
      className={`mapping-card ${active ? "active-mapping" : ""} decision-${decision}`}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={active}
      aria-label={`Mapping ${mapping.indicator}, score ${formatScore(mapping.score)}`}
      data-testid={`mapping-card-${mappingKeyStr}`}
    >
      <div className="card-row">
        <span className="indicator-badge">
          P{mapping.pillar} · {mapping.indicator}
        </span>
        <span className={`score-badge ${scoreClass(mapping.score)}`}>
          {formatScore(mapping.score)}
        </span>
      </div>

      <div className="card-titles">
        <h3>{mapping.source_legislation || t("mapping.untitled")}</h3>
        <p className="muted">
          {mapping.last_update || t("mapping.dateUnknown")}
          {mapping.scope !== "unknown" ? ` · ${mapping.scope}` : null}
        </p>
      </div>

      <div className="taxonomy-row">
        {mapping.cluster ? <span className="taxonomy-chip cluster">{mapping.cluster}</span> : null}
        {mapping.name ? <span className="taxonomy-chip name">{mapping.name}</span> : null}
        {mapping.policy_description ? <span className="taxonomy-chip policy">{mapping.policy_description}</span> : null}
        {mapping.cov_name ? <span className="taxonomy-chip cov">{mapping.cov_name}</span> : null}
        {mapping.region ? <span className="taxonomy-chip region">{mapping.region}</span> : null}
        {mapping.coverage ? <span className="taxonomy-chip coverage">{mapping.coverage}</span> : null}
      </div>

      <blockquote className="quote select-text">
        "{visibleQuote}"
        {quoteIsLong ? (
          <button
            type="button"
            className="link-button"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
          >
            {expanded ? t("mapping.showLess") : t("mapping.showMore")}
          </button>
        ) : null}
      </blockquote>

      {hasReport ? (
        <div className="reasoning-toggle-row">
          <button
            type="button"
            className="secondary reasoning-toggle"
            aria-haspopup="dialog"
            aria-expanded={reportOpen}
            onClick={(e) => {
              e.stopPropagation();
              setReportOpen(true);
            }}
          >
            {t("mapping.reasoningReport")}
          </button>
          <RightDrawer
            open={reportOpen}
            onOpenChange={setReportOpen}
            title={t("mapping.reasoningReport")}
            className="reasoning-drawer"
          >
            <div className="reasoning-drawer-header">
              <span className="indicator-badge">
                P{mapping.pillar} · {mapping.indicator}
              </span>
              <span className={`score-badge ${scoreClass(mapping.score)}`}>
                {formatScore(mapping.score)}
              </span>
              <h3>{mapping.source_legislation || t("mapping.untitled")}</h3>
            </div>
            <ReasoningReport mapping={mapping} />
          </RightDrawer>
        </div>
      ) : null}

      {mapping.impact ? (
        <p className="impact">
          <strong>{t("mapping.scoreReason")}</strong> {mapping.impact}
        </p>
      ) : null}

      <div className="card-footer">
        <div className="card-footer-left">
          {mapping.source_url ? (
            <a
              href={mapping.source_url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              {t("mapping.source")} ↗
            </a>
          ) : (
            <span className="muted">{t("mapping.noSourceUrl")}</span>
          )}
          {mapping.requires_human_review ? (
            <span className="review-flag">{t("mapping.needsReview")}</span>
          ) : null}
        </div>
        <span className="muted small">
          {t("mapping.via")} {mapping.extraction_provider || "unknown"}
        </span>
      </div>

      <div className="card-actions">
        <button
          type="button"
          className={`secondary ${decision === "rejected" ? "active-reject" : ""}`}
          onClick={(e) => {
            e.stopPropagation();
            onDecision(decision === "rejected" ? "pending" : "rejected");
          }}
        >
          {t("mapping.reject")}
        </button>
        <button
          type="button"
          className={decision === "approved" ? "active-approve" : ""}
          onClick={(e) => {
            e.stopPropagation();
            onDecision(decision === "approved" ? "pending" : "approved");
          }}
        >
          {t("mapping.approve")}
        </button>
      </div>
    </li>
  );
}
