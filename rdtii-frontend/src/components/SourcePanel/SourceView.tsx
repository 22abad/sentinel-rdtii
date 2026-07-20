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
  /** Bar label rendered on the same line as the pager (e.g. "Audit Highlight"). */
  title?: string;
};

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Length-preserving normalisation: fold the character variants that routinely
// differ between an LLM's verbatim_quote and the raw source (curly vs straight
// quotes, en/em dash vs hyphen, non-breaking space, ASCII case) WITHOUT
// changing string length, so an index found in normalised space maps straight
// back onto the original text. One UTF-16 unit in → one out (astral chars pass
// through unchanged), which keeps the 1:1 mapping intact.
function normChar(ch: string): string {
  const code = ch.charCodeAt(0);
  if (code >= 65 && code <= 90) return ch.toLowerCase(); // A–Z, always 1:1
  if (code === 0x00a0 || code === 0x2007 || code === 0x202f) return " "; // nbsp
  switch (ch) {
    case "‘":
    case "’":
    case "ʼ":
      return "'";
    case "“":
    case "”":
      return '"';
    case "–":
    case "—":
      return "-";
    default:
      return ch;
  }
}
function normalize(s: string): string {
  let out = "";
  for (let i = 0; i < s.length; i++) out += normChar(s[i]);
  return out;
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
  // Last resort: fold the character variants (curly/straight quotes, dashes,
  // nbsp, ASCII case) that routinely differ between the LLM's verbatim and the
  // raw source. normalize() is length-preserving, so indices map straight back.
  const nt = normalize(text);
  const nq = normalize(quote);
  const nidx = nt.indexOf(nq);
  if (nidx >= 0) return [nidx, nidx + quote.length];
  try {
    const pattern = nq.trim().split(/\s+/).map(escapeRegExp).join("\\s+");
    const m = new RegExp(pattern).exec(nt);
    if (m) return [m.index, m.index + m[0].length];
  } catch {
    // give up
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

export function SourceView({ text, activeMapping, sourceRef, onClick, title }: SourceViewProps) {
  const pages = useMemo(() => splitPages(text), [text]);
  const multi = pages.length > 1;
  const [page, setPage] = useState(0);

  // Resolve the quote against EVERY page with the same tolerant matcher the
  // highlight uses (offsets are blob-relative, so per-page they're only a
  // hint — the content search is what actually lands it). The page that
  // resolves is the one to show; its span is the highlight.
  const quote = activeMapping?.verbatim_quote ?? "";
  const perPage = useMemo(
    () =>
      activeMapping
        ? pages.map((p) =>
            locateQuote(p.body, quote, activeMapping.quote_start, activeMapping.quote_end),
          )
        : pages.map(() => null),
    [pages, activeMapping, quote],
  );

  // Jump to the page that actually contains the clicked quote.
  useEffect(() => {
    if (!multi || !quote.trim()) return;
    const idx = perPage.findIndex((loc) => loc !== null);
    if (idx >= 0) setPage(idx);
  }, [perPage, multi, quote]);
  useEffect(() => {
    if (page > pages.length - 1) setPage(0);
  }, [pages.length, page]);

  const pageIdx = Math.min(page, pages.length - 1);
  const current = pages[pageIdx] ?? { title: null, body: text };
  const body = current.body;
  const located = perPage[pageIdx] ?? null;

  return (
    <>
      <div className="source-bar source-bar--pager">
        <span>{title}</span>
        {multi && (
        <div className="source-pager nodrag">
          <button
            type="button"
            className="source-pager-arrow"
            aria-label="Previous document"
            disabled={page === 0}
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.max(0, p - 1));
            }}
          >
            ←
          </button>
          <span className="source-pager-label">
            {page + 1}/{pages.length}
            {current.title ? ` “${current.title}”` : ""}
          </span>
          <button
            type="button"
            className="source-pager-arrow"
            aria-label="Next document"
            disabled={page >= pages.length - 1}
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.min(pages.length - 1, p + 1));
            }}
          >
            →
          </button>
        </div>
        )}
      </div>
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
