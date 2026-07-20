import type React from "react";
import { useEffect, useMemo, useState } from "react";
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
 * document (the cache key is whitespace-normalised), and — for multi-file
 * runs — offsets are relative to the whole concatenated blob, not the single
 * page we display. When the hint doesn't reproduce the quote, fall back to
 * finding the verbatim itself: exact first, then whitespace-tolerant.
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
  return null;
}

type Page = { title: string | null; body: string };

// Multi-file source text is one blob: `=== filename ===\n<content>` sections
// joined by blank lines. Split it into per-document pages so the highlight
// tracker works within one document at a time.
function splitPages(text: string): Page[] {
  const parts = text.split(/^=== (.+?) ===$/m); // [pre, title, body, title, body, …]
  if (parts.length <= 1) return [{ title: null, body: text }];
  const pages: Page[] = [];
  if (parts[0]?.trim()) pages.push({ title: null, body: parts[0] });
  for (let i = 1; i < parts.length; i += 2) {
    pages.push({
      title: parts[i],
      body: (parts[i + 1] ?? "").replace(/^\n+/, ""),
    });
  }
  return pages.length ? pages : [{ title: null, body: text }];
}

export function SourceView({ text, activeMapping, sourceRef, onClick }: SourceViewProps) {
  const pages = useMemo(() => splitPages(text), [text]);
  const multi = pages.length > 1;
  const [page, setPage] = useState(0);

  // Jump to the page that actually contains the clicked quote.
  const quote = (activeMapping?.verbatim_quote ?? "").trim();
  useEffect(() => {
    if (!multi || !quote) return;
    const idx = pages.findIndex((p) => p.body.includes(quote));
    if (idx >= 0) setPage(idx);
  }, [quote, pages, multi]);
  useEffect(() => {
    if (page > pages.length - 1) setPage(0);
  }, [pages.length, page]);

  const current =
    pages[Math.min(page, pages.length - 1)] ?? { title: null, body: text };
  const body = current.body;

  const located = activeMapping
    ? locateQuote(
        body,
        activeMapping.verbatim_quote ?? "",
        activeMapping.quote_start,
        activeMapping.quote_end,
      )
    : null;

  return (
    <>
      {multi && (
        <div className="source-pager nodrag">
          <button
            type="button"
            disabled={page === 0}
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.max(0, p - 1));
            }}
          >
            ‹ Prev
          </button>
          <span className="source-pager-label">
            {page + 1}/{pages.length}
            {current.title ? ` · ${current.title}` : ""}
          </span>
          <button
            type="button"
            disabled={page >= pages.length - 1}
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.min(pages.length - 1, p + 1));
            }}
          >
            Next ›
          </button>
        </div>
      )}
      <div
        ref={sourceRef}
        className={`source-view ${located ? "active-highlight" : ""}`}
        tabIndex={0}
        onClick={onClick}
        title={activeMapping ? t("source.switchToEditTitle") : undefined}
      >
        {located ? (
          <>
            {body.slice(0, located[0])}
            <mark className={`mark ${scoreClass(activeMapping!.score)}-mark`}>
              {body.slice(located[0], located[1])}
            </mark>
            {body.slice(located[1])}
          </>
        ) : (
          body
        )}
      </div>
    </>
  );
}
