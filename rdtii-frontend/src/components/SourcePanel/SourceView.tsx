import type React from "react";
import { scoreClass } from "../../lib/utils";
import type { IndicatorMapping } from "../../types";
import { t } from "../../lib/i18n";

type SourceViewProps = {
  text: string;
  activeMapping: IndicatorMapping | null;
  sourceRef: React.RefObject<HTMLDivElement>;
  onClick?: () => void;
};

export function SourceView({ text, activeMapping, sourceRef, onClick }: SourceViewProps) {
  if (!activeMapping) {
    return (
      <div ref={sourceRef} className="source-view" tabIndex={0} onClick={onClick}>
        {text}
      </div>
    );
  }

  const start = Math.max(0, Math.min(activeMapping.quote_start, text.length));
  const end = Math.max(start, Math.min(activeMapping.quote_end, text.length));

  if (start === end) {
    return (
      <div ref={sourceRef} className="source-view" tabIndex={0} onClick={onClick}>
        {text}
      </div>
    );
  }

  const before = text.slice(0, start);
  const middle = text.slice(start, end);
  const after = text.slice(end);

  return (
    <div
      ref={sourceRef}
      className="source-view active-highlight"
      tabIndex={0}
      onClick={onClick}
      title={t("source.switchToEditTitle")}
    >
      {before}
      <mark className={`mark ${scoreClass(activeMapping.score)}-mark`}>{middle}</mark>
      {after}
    </div>
  );
}
