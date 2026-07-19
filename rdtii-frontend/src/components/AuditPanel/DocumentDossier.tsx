import { useEffect, useState } from "react";
import type { IndicatorMapping } from "../../types";
import {
  verifyReleaseYear,
  verifyTimestamp,
  type ReleaseYear,
  type TimestampVerification,
} from "../../services/verification";

/**
 * Document-level identity, consolidated ONCE across every mapping of a
 * document — source grade, timeframe, staleness, release year, forensic
 * timestamp, OCR quality are properties of the DOCUMENT, not of each
 * mapping. Rendering them per-card let per-chunk LLM noise show a different
 * "legal characterisation" on every row of the same statute; here they are
 * deterministically aggregated (best-confidence grade, modal timeframe,
 * worst staleness, one release-year/timestamp probe per document) and
 * re-derived on every render, so the dossier updates live as mappings
 * stream in. Discovery runs mix several laws in one audit panel, so
 * mappings are grouped per document first.
 */

type FeatureValue = boolean | number | string;

function feat(m: IndicatorMapping, ...keys: string[]): FeatureValue | undefined {
  const features = (m.features ?? {}) as Record<string, FeatureValue>;
  for (const key of keys) {
    if (key in features) return features[key];
  }
  return undefined;
}

function mode(values: string[]): string | null {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  let best: string | null = null;
  let bestCount = 0;
  for (const [value, count] of counts) {
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

const SEVERITY_ORDER = ["none", "low", "medium", "high"];

// Group ONLY by deterministic identity (URL, content hash) — never by
// source_legislation, which is a per-chunk LLM output and would split one
// document into several "documents" (the exact per-card inconsistency this
// dossier exists to kill). Rows with neither (one uploaded file) share a group.
function docKey(m: IndicatorMapping): string {
  return m.source_url || String(feat(m, "source_file_sha256") ?? "") || "uploaded-document";
}

export function DocumentDossier({ mappings }: { mappings: IndicatorMapping[] }) {
  if (!mappings.length) return null;
  const groups = new Map<string, IndicatorMapping[]>();
  for (const m of mappings) {
    const key = docKey(m);
    const group = groups.get(key);
    if (group) group.push(m);
    else groups.set(key, [m]);
  }
  return (
    <>
      {[...groups.entries()].map(([key, group]) => (
        <DossierEntry key={key} mappings={group} showTitle={groups.size > 1} />
      ))}
    </>
  );
}

function DossierEntry({
  mappings,
  showTitle,
}: {
  mappings: IndicatorMapping[];
  showTitle: boolean;
}) {
  const [releaseYear, setReleaseYear] = useState<ReleaseYear | null>(null);
  const [timestamp, setTimestamp] = useState<TimestampVerification | null>(null);

  const anchor = mappings.find((m) => m.source_url) ?? mappings[0];
  const anchorUrl = anchor?.source_url ?? "";

  // One probe per DOCUMENT (keyed by URL), not one per card.
  useEffect(() => {
    let alive = true;
    verifyReleaseYear(anchor)
      .then((r) => alive && setReleaseYear(r))
      .catch(() => {});
    if (anchorUrl) {
      verifyTimestamp(anchorUrl, anchor.last_update ?? "")
        .then((t) => alive && setTimestamp(t))
        .catch(() => {});
    }
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchorUrl]);

  // Source grade: best-confidence row wins (same document → same source).
  let grade: string | null = null;
  let gradeConfidence = -1;
  for (const m of mappings) {
    const raw = feat(m, "_source_grade_confidence");
    const n = typeof raw === "number" ? raw : Number(raw);
    if (Number.isFinite(n) && n > gradeConfidence) {
      gradeConfidence = n;
      grade = String(feat(m, "_source_grade") ?? "");
    }
  }

  // Timeframe: modal value across rows.
  const timeframe = mode(
    mappings
      .map((m) => {
        const column = feat(m, "_timeframe_column");
        const status = feat(m, "_timeframe_status");
        return [column, status && `(${status})`].filter(Boolean).join(" ");
      })
      .filter(Boolean) as string[],
  );

  // Staleness: worst severity, but reasons ONLY from the rows at that
  // severity, with a rows-affected count. A union across all rows once put
  // "repealed" and "draft" on the same in-force Act — one noisy chunk must
  // read as an attributed minority signal, not the document's verdict.
  let severity = "none";
  let sawStaleness = false;
  const perRow: { sv: string; reasons: string[] }[] = [];
  for (const m of mappings) {
    const s = feat(m, "_staleness_severity");
    if (s !== undefined) sawStaleness = true;
    const sv = String(s ?? "none");
    if (SEVERITY_ORDER.indexOf(sv) > SEVERITY_ORDER.indexOf(severity)) severity = sv;
    perRow.push({
      sv,
      reasons: String(feat(m, "_staleness_reasons") ?? "")
        .split(";")
        .map((x) => x.trim())
        .filter(Boolean),
    });
  }
  const worstRows = perRow.filter((r) => r.sv === severity);
  const reasons = new Set<string>(worstRows.flatMap((r) => r.reasons));
  const worstCount = worstRows.length;

  // Document/OCR quality: file-level metadata, identical on every row —
  // take it from the anchor.
  const pdfType = feat(anchor, "_pdf_type", "pdf_type");
  const totalPages = feat(anchor, "total_pages");
  const ocrPages = feat(anchor, "ocr_pages");
  const ocrConfRaw = feat(anchor, "_ocr_mean_confidence", "mean_confidence");
  const ocrConfN = typeof ocrConfRaw === "number" ? ocrConfRaw : Number(ocrConfRaw);
  const sha = feat(anchor, "source_file_sha256");

  const rows: { label: string; value: string }[] = [];
  if (grade && gradeConfidence >= 0) {
    rows.push({ label: "Source grade", value: `${Math.round(gradeConfidence * 100)}% · ${grade}` });
  }
  if (timeframe) rows.push({ label: "Timeframe", value: timeframe });
  if (sawStaleness) {
    rows.push({
      label: "Staleness",
      value:
        severity === "none"
          ? "none — healthy"
          : `${severity} (${worstCount}/${mappings.length} rows)${
              reasons.size ? ` · ${[...reasons].join("; ")}` : ""
            }`,
    });
  }
  if (releaseYear?.year) {
    rows.push({
      label: "Release year",
      value: `${releaseYear.year} · ${Math.round(releaseYear.confidence * 100)}% (${releaseYear.decided_by})`,
    });
  }
  if (timestamp) {
    rows.push({
      label: "Timestamp",
      value: `${timestamp.verified ? "✓ corroborated" : "unconfirmed"}${
        timestamp.best_date ? ` · best date ${timestamp.best_date}` : ""
      }`,
    });
  }
  if (pdfType !== undefined) rows.push({ label: "Type", value: String(pdfType) });
  if (totalPages !== undefined) {
    rows.push({
      label: "OCR",
      value: `${ocrPages !== undefined ? `${ocrPages}/${totalPages} pp` : `${totalPages} pp`}${
        Number.isFinite(ocrConfN) ? ` · ${Math.round(ocrConfN * 100)}% conf` : ""
      }`,
    });
  }
  if (typeof sha === "string" && sha) {
    rows.push({ label: "SHA-256", value: `${sha.slice(0, 10)}…${sha.slice(-6)}` });
  }

  // Majority-vote name across the group's rows — a single chunk's
  // misattribution must not label the whole document.
  const title = showTitle
    ? mode(mappings.map((m) => m.source_legislation).filter(Boolean) as string[]) ||
      anchor.source_url ||
      null
    : null;

  return (
    <div
      className="nodrag border-t-[1.5px] border-[#111827] px-[18px] py-2.5"
      aria-label="Document dossier"
    >
      <div
        style={{
          fontSize: "0.62rem",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "#6b675c",
          marginBottom: 6,
        }}
      >
        Document dossier{title ? ` — ${title}` : ""} · consolidated across{" "}
        {mappings.length} mapping{mappings.length === 1 ? "" : "s"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 18px" }}>
        {rows.map((row) => (
          <div key={row.label} style={{ fontSize: "0.72rem", color: "#1f2933" }}>
            <span style={{ fontWeight: 700 }}>{row.label}:</span>{" "}
            <span style={{ fontFamily: '"SFMono-Regular", Consolas, Menlo, monospace' }}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
