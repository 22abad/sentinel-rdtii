// Standalone brand-logo display — a type-specimen panel (the reference layout).
// Self-contained: deep-green ground, light-green measurement grid, one huge
// white wordmark with a boxed superscript tag, four corner labels, and a row of
// bare spec numbers. Not linked to or styled as a continuation of any other
// section — it stands on its own as the brand mark.

const BRAND_GRID = {
  backgroundColor: "#17593a",
  backgroundImage:
    "linear-gradient(#4ade8040 1px, transparent 1px)," +
    "linear-gradient(90deg, #4ade8040 1px, transparent 1px)",
  backgroundSize: "44px 44px",
} as const;

// Bare spec numbers (the specimen's number row): pillars 6 & 7, 9 indicators,
// 4 economies, 13 output fields.
const SPEC = ["06", "07", "09", "04", "13"];

export function BrandSpecimen() {
  return (
    <section className="relative w-full text-white" style={BRAND_GRID}>
      <div className="mx-auto flex min-h-[72vh] max-w-6xl flex-col justify-between px-6 py-16">
        {/* top corner labels */}
        <div className="flex items-start justify-between font-sans text-sm leading-tight tracking-wide text-emerald-300">
          <div>
            Legal-Evidence
            <br />
            Mapper
          </div>
          <div className="text-right">
            Cross-Border Data
            <br />
            &amp; Cybersecurity
          </div>
        </div>

        {/* wordmark + boxed superscript tag + spec number row */}
        <div className="py-10">
          <div className="flex items-start justify-center">
            <h2 className="font-serif text-6xl font-bold leading-none tracking-tight sm:text-8xl md:text-[8rem] lg:text-[10rem]">
              Sentinel
            </h2>
            <span className="ml-2 mt-3 shrink-0 border border-white/80 px-2 py-0.5 font-sans text-xs tracking-widest">
              2.1
            </span>
          </div>
          <div className="mt-8 flex justify-between font-mono text-sm text-white sm:text-base">
            {SPEC.map((n, i) => (
              <span key={i}>{n}</span>
            ))}
          </div>
        </div>

        {/* bottom corner labels */}
        <div className="flex items-end justify-between font-sans text-sm leading-tight tracking-wide text-emerald-300">
          <div>
            Team
            <br />
            Sentinel
          </div>
          <div className="text-right">
            RDTII 2.1
            <br />
            Framework
          </div>
        </div>
      </div>
    </section>
  );
}
