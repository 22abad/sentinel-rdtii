import { motion } from "motion/react";
import { mappingKey } from "../../lib/utils";
import { t } from "../../lib/i18n";
import type { IndicatorMapping, ReviewDecision, Status } from "../../types";
import { MappingCard } from "./MappingCard";

type AuditBodyProps = {
  status: Status;
  mappings: IndicatorMapping[];
  totalMappings: number;
  activeKey: string | null;
  decisions: Record<string, ReviewDecision>;
  selectMapping: (key: string) => void;
  setDecision: (key: string, d: ReviewDecision) => void;
};

export function AuditBody({
  status,
  mappings,
  totalMappings,
  activeKey,
  decisions,
  selectMapping,
  setDecision,
}: AuditBodyProps) {
  if (status === "idle") {
    return (
      <p className="empty-state">
        {t("audit.empty.idle")}
      </p>
    );
  }

  if (status === "loading" && mappings.length === 0) {
    return <p className="empty-state">{t("audit.empty.loading")}</p>;
  }

  if (status === "error") {
    return (
      <p className="empty-state error-state">
        {t("audit.empty.error")}
      </p>
    );
  }

  if (mappings.length === 0) {
    return (
      <p className="empty-state">
        {totalMappings === 0
          ? t("audit.empty.none")
          : t("audit.empty.filtered")}
      </p>
    );
  }

  return (
    <ul className="mapping-list">
      {mappings.map((m) => {
        const key = mappingKey(m);
        return (
          <motion.div
            key={key}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <MappingCard
              mapping={m}
              mappingKeyStr={key}
              active={key === activeKey}
              decision={decisions[key] ?? "pending"}
              onSelect={() => selectMapping(key)}
              onDecision={(d) => setDecision(key, d)}
            />
          </motion.div>
        );
      })}
    </ul>
  );
}
