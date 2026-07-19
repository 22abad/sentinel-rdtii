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

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Locate the quote in the text. Offsets are a hint, not gospel: a cached
 * extraction may have been produced from a whitespace-variant of the same
 * document (the cache key is whitespace-normalised), so stored offsets can
 * land past the end of — or misaligned within — the text on screen. When the
 * hint doesn't reproduce the quote, fall back to finding the verbatim itself:
 * exact first, then whitespace-tolerant.
 */
function locateQuote(
  text: string,
  quote: string,
  hintStart: number,
  hintEnd: number,
): [number, number] | null {
  const start = Math.max(0, Math.min(hintStart, text.length));
  const end = Math.max(start, Math.min(hintEnd, text.length));
  if (quote && text.slice(start, end) === quote) return [start, end];
  if (!quote.trim()) return start === end ? null : [start, end];
  const idx = text.indexOf(quote);
  if (idx >= 0) return [idx, idx + quote.length];
  try {
    const pattern = quote.trim().split(/\s+/).map(escapeRegExp).join("\\s+");
    const m = new RegExp(pattern).exec(text);
    if (m) return [m.index, m.index + m[0].length];
  } catch {
    // quote too pathological for a regex — give up on highlighting
  }
  return start === end ? null : [start, end];
}

export function SourceView({ text, activeMapping, sourceRef, onClick }: SourceViewProps) {
  if (!activeMapping) {
    return (
      <div ref={sourceRef} className="source-view" tabIndex={0} onClick={onClick}>
        {text}
      </div>
    );
  }

  const located = locateQuote(
    text,
    activeMapping.verbatim_quote ?? "",
    activeMapping.quote_start,
    activeMapping.quote_end,
  );

  if (!located) {
    return (
      <div ref={sourceRef} className="source-view" tabIndex={0} onClick={onClick}>
        {text}
      </div>
    );
  }

  const [start, end] = located;
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
