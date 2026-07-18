import { type CSSProperties, useLayoutEffect, useRef, useState } from "react";
import "@fontsource/boldonse/400.css";

// Standalone brand-logo display — a type-specimen panel (the reference layout).
// No background grid. The wordmark is set at a fixed 200px and each glyph is its
// own inline-block cell, so a full-height registration line hangs at every
// character boundary. `text-box: trim-both cap alphabetic` trims the box to the
// true cap-height and baseline, so the two horizontal lines land exactly on the
// glyph edges. Per-glyph advance widths (per-mille of em) print under each
// column, like the reference. Four corner labels + a boxed superscript tag.

const BRAND_BG = { backgroundColor: "#17593a" } as const;
const LINE = "pointer-events-none absolute bg-[#86efac]/70";
const WORD = "Sentinel";
const FS = 200; // px

const WORD_STYLE = {
  fontFamily: '"Boldonse", sans-serif',
  fontSize: `${FS}px`,
  lineHeight: 1,
  // Trim the block box to cap-height (top) and alphabetic baseline (bottom) so
  // the registration lines sit on the real glyph edges.
  textBox: "trim-both cap alphabetic",
} as CSSProperties;

export function BrandSpecimen() {
  const boxRef = useRef<HTMLDivElement>(null);
  const letterRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const [marks, setMarks] = useState<{ center: number; unit: number }[]>([]);

  useLayoutEffect(() => {
    let cancelled = false;
    const measure = () => {
      const box = boxRef.current;
      if (!box) return;
      const base = box.getBoundingClientRect().left;
      const next: { center: number; unit: number }[] = [];
      letterRefs.current.forEach((el) => {
        if (!el) return;
        const r = el.getBoundingClientRect();
        next.push({
          center: (r.left + r.right) / 2 - base,
          unit: Math.round((r.width / FS) * 1000),
        });
      });
      if (!cancelled && next.length) setMarks(next);
    };
    const ready = document.fonts?.ready ?? Promise.resolve();
    ready.then(() => {
      if (!cancelled) measure();
    });
    window.addEventListener("resize", measure);
    return () => {
      cancelled = true;
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <section className="relative w-full overflow-hidden text-white" style={BRAND_BG}>
      <div className="relative mx-auto flex min-h-[74vh] max-w-6xl items-center justify-center px-6 py-20">
        {/* corner labels */}
        <div className="absolute left-6 top-20 font-sans text-sm leading-tight tracking-wide text-emerald-300">
          Legal-Evidence
          <br />
          Mapper
        </div>
        <div className="absolute right-6 top-20 text-right font-sans text-sm leading-tight tracking-wide text-emerald-300">
          Cross-Border Data
          <br />
          &amp; Cybersecurity
        </div>
        <div className="absolute bottom-20 left-6 font-sans text-sm leading-tight tracking-wide text-emerald-300">
          Team
          <br />
          Sentinel
        </div>
        <div className="absolute bottom-20 right-6 text-right font-sans text-sm leading-tight tracking-wide text-emerald-300">
          RDTII 2.1
          <br />
          Framework
        </div>

        {/* wordmark + registration lines + per-glyph spec numbers */}
        <div className="relative inline-flex flex-col items-stretch">
          <div className="relative" ref={boxRef}>
            <h2 className="whitespace-nowrap tracking-tight" style={WORD_STYLE}>
              {WORD.split("").map((ch, i) => (
                <span
                  key={i}
                  ref={(el) => {
                    letterRefs.current[i] = el;
                  }}
                  className="relative inline-block align-baseline"
                >
                  {ch}
                  {/* left-edge line for this glyph cell, bled full panel height */}
                  <span
                    aria-hidden
                    className={`${LINE} bottom-[-100vh] left-0 top-[-100vh] w-px`}
                  />
                  {/* right-edge line only after the last glyph */}
                  {i === WORD.length - 1 && (
                    <span
                      aria-hidden
                      className={`${LINE} bottom-[-100vh] right-0 top-[-100vh] w-px`}
                    />
                  )}
                </span>
              ))}
            </h2>

            {/* boxed superscript tag at the cap-height line */}
            <span className="absolute left-full top-0 ml-2 shrink-0 border border-white/80 px-2 py-0.5 font-sans text-xs tracking-widest">
              2.1
            </span>

            {/* cap-height + baseline horizontals, bled to panel edges */}
            <span
              aria-hidden
              className={`${LINE} left-[-100vw] right-[-100vw] top-0 h-px`}
            />
            <span
              aria-hidden
              className={`${LINE} left-[-100vw] right-[-100vw] bottom-0 h-px`}
            />
          </div>

          {/* per-glyph advance widths (per-mille of em), centered under columns */}
          <div className="relative mt-6 h-4 font-mono text-xs text-white">
            {marks.map((m, i) => (
              <span
                key={i}
                className="absolute -translate-x-1/2"
                style={{ left: `${m.center}px` }}
              >
                {m.unit}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
