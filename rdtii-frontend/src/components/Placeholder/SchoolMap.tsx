// De School–style grid section (MVP) — replaces the dotted-map WorldMap on the
// landing page. Swiss/International-Typographic: cream ground + black
// graph-paper grid, bold uppercase headline, monospace listings, underlined
// links, hairline boxes, a stippled block as the only texture (a nod to the
// dotted map it replaces). Static demo data; all links go to /mapsearch.

const COUNTRIES = [
  { code: "SGP", law: "Personal Data Protection Act 2012", pillars: "6 · 7" },
  { code: "MYS", law: "Personal Data Protection Act 2010", pillars: "6 · 7" },
  { code: "AUS", law: "Privacy Act 1988", pillars: "6 · 7" },
  { code: "THA", law: "PDPA B.E. 2562 (2019)", pillars: "6 · 7" },
];

const GRID_BG = {
  backgroundColor: "#ffffff",
  backgroundImage:
    "linear-gradient(#10b98159 1px, transparent 1px)," +
    "linear-gradient(90deg, #10b98159 1px, transparent 1px)",
  backgroundSize: "44px 44px",
} as const;

const STIPPLE = {
  backgroundImage: "radial-gradient(#000 1.2px, transparent 1.2px)",
  backgroundSize: "9px 9px",
} as const;

export function SchoolMap() {
  return (
    <section className="relative w-full border-y border-black text-black" style={GRID_BG}>
      <div className="mx-auto max-w-6xl px-6 py-16">
        {/* top row: boxed wordmark + section tag */}
        <div className="flex items-start justify-between">
          <div className="border border-black leading-none">
            <div className="border-b border-black px-4 py-2 text-xs font-bold tracking-[0.2em]">
              RDTII
            </div>
            <div className="px-4 py-2 text-xs font-bold tracking-[0.2em]">SENTINEL</div>
          </div>
          <a
            href="/mapsearch"
            className="border border-black px-3 py-1 text-xs font-bold uppercase tracking-[0.2em] underline underline-offset-4 hover:bg-black hover:text-white"
          >
            Global Search
          </a>
        </div>

        {/* headline */}
        <h2 className="mt-12 text-5xl font-bold uppercase leading-[0.92] tracking-tight md:text-7xl">
          Search laws
          <br />
          from the map
        </h2>

        <div className="mt-12 grid grid-cols-1 gap-10 md:grid-cols-2">
          {/* left: featured link + stippled block */}
          <div>
            <a
              href="/mapsearch"
              className="block text-2xl font-bold leading-tight underline decoration-1 underline-offset-4 md:text-3xl"
            >
              → Explore the digital-trade map
              <br />
              across Asia-Pacific
            </a>
            <p className="mt-4 max-w-sm font-mono text-xs text-black/60">
              Automated RDTII research focused on Pillars 6 &amp; 7, with an
              extensible path to the full framework.
            </p>
            <div className="mt-8 h-44 w-full border border-black" style={STIPPLE} />
          </div>

          {/* right: monospace listings */}
          <div className="font-mono text-sm">
            {COUNTRIES.map((c) => (
              <a
                key={c.code}
                href="/mapsearch"
                className="block border-t border-black py-3 hover:bg-black/5"
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-bold">{c.code}</span>
                  <span className="underline underline-offset-2">EXPLORE</span>
                </div>
                <div className="text-black/70">{c.law}</div>
                <div className="text-black/50">pillars {c.pillars}</div>
              </a>
            ))}
            <div className="border-t border-black pt-3">
              <a href="/mapsearch" className="font-bold underline underline-offset-4">
                Full map →
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
