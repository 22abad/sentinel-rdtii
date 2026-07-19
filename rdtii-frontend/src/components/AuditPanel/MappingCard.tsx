import { useState } from "react";
import { QUOTE_TRUNCATE } from "../../lib/constants";
import { formatScore } from "../../lib/utils";
import { t } from "../../lib/i18n";
import type { IndicatorMapping, ReviewDecision } from "../../types";
import { ReasoningReport } from "./ReasoningReport";

type MappingCardProps = {
  mapping: IndicatorMapping;
  mappingKeyStr: string;
  active: boolean;
  decision: ReviewDecision;
  onSelect: () => void;
  onDecision: (d: ReviewDecision) => void;
};

/**
 * RAD-style accordion row (Swiss index list): collapsed, a row shows only
 * "P6.2 · Legislation Title · +". Clicking expands the tidied-up report
 * inline — score/meta, verbatim quote, impact, the reasoning report (inline,
 * no drawer), source link, and the approve/reject decision.
 */
export function MappingCard({
  mapping,
  mappingKeyStr,
  active,
  decision,
  onSelect,
  onDecision,
}: MappingCardProps) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const hasReport =
    Object.keys(mapping.features ?? {}).length > 0 ||
    (mapping.flag_reasons?.length ?? 0) > 0;

  const quoteIsLong = mapping.verbatim_quote.length > QUOTE_TRUNCATE;
  const visibleQuote =
    quoteIsLong && !expanded
      ? `${mapping.verbatim_quote.slice(0, QUOTE_TRUNCATE)}…`
      : mapping.verbatim_quote;

  // Row title: the PROVISION, not the law name. Every row of one document
  // repeats (a per-chunk variant of) the same law name — zero information,
  // while the clause + quote is what actually distinguishes rows. The
  // document's identity lives once in the DocumentDossier.
  const clause = mapping.article_clause?.trim();
  const quoteSnippet = mapping.verbatim_quote.replace(/\s+/g, " ").trim();
  const rowTitle =
    [clause, quoteSnippet && `“${quoteSnippet.slice(0, 90)}${quoteSnippet.length > 90 ? "…" : ""}”`]
      .filter(Boolean)
      .join(" · ") ||
    mapping.source_legislation ||
    t("mapping.untitled");

  return (
    <li
      className={`mapping-row ${open ? "open" : ""} ${active ? "active-mapping" : ""} decision-${decision}`}
      data-testid={`mapping-card-${mappingKeyStr}`}
    >
      <button
        type="button"
        className="mapping-row-head nodrag"
        aria-expanded={open}
        aria-label={`Mapping ${mapping.indicator}, score ${formatScore(mapping.score)}`}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) onSelect();
        }}
      >
        <span className="mapping-row-code">P{mapping.indicator}</span>
        <span className="mapping-row-title">{rowTitle}</span>
        {decision !== "pending" && (
          <span className={`mapping-row-decision ${decision}`}>
            {decision === "approved" ? t("mapping.approve") : t("mapping.reject")}
          </span>
        )}
        <span className="mapping-row-plus" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>

      {open && (
        <div className="mapping-row-body select-text">
          {/* single meta row — score lives in the report's Score card now */}
          <div className="mapping-row-meta">
            <span>
              {mapping.last_update || t("mapping.dateUnknown")}
              {mapping.scope !== "unknown" ? ` · ${mapping.scope}` : null}
            </span>
            <span>
              {t("mapping.via")} {mapping.extraction_provider || "unknown"}
            </span>
            {mapping.requires_human_review && (
              <span className="review-flag">{t("mapping.needsReview")}</span>
            )}
          </div>

          <section className="mapping-row-block">
            <h4>Raw material</h4>
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
          </section>

          {mapping.impact ? (
            <section className="mapping-row-block">
              <h4>AI reason</h4>
              <p className="impact">{mapping.impact}</p>
            </section>
          ) : null}

          {hasReport ? (
            <div className="mapping-row-report">
              <ReasoningReport mapping={mapping} />
            </div>
          ) : null}

          <div className="mapping-row-actions">
            {mapping.source_url ? (
              <a
                className="mapping-row-source"
                href={mapping.source_url}
                target="_blank"
                rel="noreferrer"
              >
                {t("mapping.source")} ↗
              </a>
            ) : (
              <span className="mapping-row-source muted">
                {t("mapping.noSourceUrl")}
              </span>
            )}
            <button
              type="button"
              className={`secondary ${decision === "rejected" ? "active-reject" : ""}`}
              onClick={() =>
                onDecision(decision === "rejected" ? "pending" : "rejected")
              }
            >
              {t("mapping.reject")}
            </button>
            <button
              type="button"
              className={decision === "approved" ? "active-approve" : ""}
              onClick={() =>
                onDecision(decision === "approved" ? "pending" : "approved")
              }
            >
              {t("mapping.approve")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
