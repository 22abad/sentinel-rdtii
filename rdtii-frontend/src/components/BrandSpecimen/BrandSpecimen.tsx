// Standalone brand-logo display — a type-specimen panel (the reference layout).
// No background grid: instead, four registration lines are keyed to the
// wordmark's bounding box — two full-width horizontals at cap-height and
// baseline, two full-height verticals at the left/right glyph edges — bled out
// to the panel edges. Four corner labels, a boxed superscript tag, and a row of
// bare spec numbers under the baseline. Self-contained brand mark.

const BRAND_BG = { backgroundColor: "#17593a" } as const;
const LINE = "pointer-events-none absolute bg-[#86efac]/70";

// Bare spec numbers under the baseline: pillars 6 & 7, 9 indicators,
// 4 economies, 13 output fields.
const SPEC = ["06", "07", "09", "04", "13"];

export function BrandSpecimen() {
  return (
    <section
      className="relative w-full overflow-hidden text-white"
      style={BRAND_BG}
    >
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

        {/* wordmark + registration lines + spec numbers */}
        <div className="relative inline-flex flex-col items-stretch">
          <div className="relative">
            <h2 className="whitespace-nowrap font-serif text-6xl font-bold leading-none tracking-tight sm:text-8xl md:text-[8rem] lg:text-[10rem]">
              Sentinel
            </h2>
            {/* boxed superscript tag at the cap-height line, right of the mark */}
            <span className="absolute left-full top-0 ml-2 shrink-0 border border-white/80 px-2 py-0.5 font-sans text-xs tracking-widest">
              2.1
            </span>
            {/* registration lines keyed to the wordmark box, bled to panel edges */}
            <span className={`${LINE} left-[-100vw] right-[-100vw] top-0 h-px`} aria-hidden />
            <span className={`${LINE} left-[-100vw] right-[-100vw] bottom-0 h-px`} aria-hidden />
            <span className={`${LINE} bottom-[-100vh] left-0 top-[-100vh] w-px`} aria-hidden />
            <span className={`${LINE} bottom-[-100vh] right-0 top-[-100vh] w-px`} aria-hidden />
          </div>
          {/* spec numbers, spread across the wordmark width, below the baseline */}
          <div className="mt-6 flex justify-between font-mono text-sm text-white sm:text-base">
            {SPEC.map((n, i) => (
              <span key={i}>{n}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
