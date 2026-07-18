// Type-specimen–style brand section (De School lineage), sibling to SchoolMap.
// Color-inverse of the map panel — deep-green ground + light-green measurement
// grid + a huge white wordmark — so the landing page alternates white → green.
// Specimen scaffolding: four corner labels, a boxed superscript tag, and a row
// of metric numbers. All figures are real SENTINEL / Round-1 facts, not filler.

const BRAND_GRID = {
  backgroundColor: "#17593a",
  backgroundImage:
    "linear-gradient(#4ade8040 1px, transparent 1px)," +
    "linear-gradient(90deg, #4ade8040 1px, transparent 1px)",
  backgroundSize: "44px 44px",
} as const;

// Round-1 scope, all defensible: P6+P7, indicators 6.1–6.4 & 7.1–7.5,
// four economies (SGP MYS AUS THA), the official 13-column output, RDTII 2.1.
const METRICS = [
  { n: "02", label: "Pillars" },
  { n: "09", label: "Indicators" },
  { n: "04", label: "Economies" },
  { n: "13", label: "Data fields" },
  { n: "2.1", label: "Framework" },
];

export function BrandSpecimen() {
  return (
    <section
      className="relative w-full border-y border-[#10B981]/40 text-white"
      style={BRAND_GRID}
    >
      <div className="mx-auto max-w-6xl px-6 py-16">
        {/* top corner labels */}
        <div className="flex items-start justify-between font-mono text-[11px] uppercase leading-tight tracking-[0.2em] text-emerald-300">
          <div>
            Regulatory
            <br />
            Intelligence
          </div>
          <div className="text-right">
            Cross-Border Data
            <br />
            &amp; Cybersecurity
          </div>
        </div>

        {/* wordmark + boxed superscript tag */}
        <div className="mt-10 flex items-start justify-center">
          <h2 className="text-center text-6xl font-bold uppercase leading-[0.85] tracking-tight sm:text-8xl md:text-[9rem] lg:text-[11rem]">
            Sentinel
          </h2>
          <span className="ml-2 mt-2 shrink-0 border border-emerald-300/70 px-2 py-0.5 font-mono text-[11px] tracking-[0.15em] text-emerald-200">
            RDTII
          </span>
        </div>

        {/* metric row (real Round-1 figures) */}
        <div className="mt-10 grid grid-cols-2 gap-x-6 gap-y-6 border-t border-emerald-300/30 pt-5 font-mono sm:grid-cols-5">
          {METRICS.map((m) => (
            <div key={m.label}>
              <div className="text-3xl font-bold leading-none md:text-4xl">
                {m.n}
              </div>
              <div className="mt-2 text-[11px] uppercase tracking-[0.2em] text-emerald-300">
                {m.label}
              </div>
            </div>
          ))}
        </div>

        {/* brand statement */}
        <p className="mt-10 max-w-xl font-mono text-xs leading-relaxed text-white/70">
          SENTINEL is an automated legal-evidence mapper for the UN ESCAP
          Regulatory Digital Trade Integration Index — reading enacted law and
          returning verbatim, sourced evidence rows against the RDTII 2.1
          framework.
        </p>

        {/* bottom corner labels + about link */}
        <div className="mt-12 flex items-end justify-between font-mono text-[11px] uppercase tracking-[0.2em] text-emerald-300">
          <div className="leading-tight">
            Team Sentinel
            <br />
            UN ESCAP · RDTII 2.1
          </div>
          <a
            href="/about"
            className="border border-emerald-300/70 px-3 py-1 text-white underline decoration-1 underline-offset-4 hover:bg-white hover:text-[#17593a]"
          >
            About the project →
          </a>
        </div>
      </div>
    </section>
  );
}
