#!/usr/bin/env python3
"""Compare a run's output against the official RDTII Round-1 answer key.

The official database (requirements/.../ESCAP-RDTII-2.1_ Round 1 Database.xlsx)
holds ONE raw score (0 / 0.5 / 1) per indicator per economy, with the law it is
based on. This tool folds any run's per-provision output into per-indicator
coverage and lines it up against that answer key, so a reviewer can see at a
glance whether a run is right — and, crucially, flags the cases the framework
rewards-or-punishes:

  • NEW-EVIDENCE DIVERGENCE — an indicator whose evidence rests on a NEW law we
    discovered (not the law the official key cites). If real, this can legitimately
    change the score (Discovery of New Evidence, Stage-2 bonus); if hallucinated,
    it is an over-claim. Either way it MUST be verified and surfaced — so it is
    printed loudly and written into the report.
  • HALLUCINATION — many different law names sharing one source URL (the tell-tale
    of a fabricated discovery).
  • GAP — the official key has a score but our run found no evidence.

    python tools/score_vs_official.py outputs/Singapore_P6-7_*.json
    python tools/score_vs_official.py --economy Singapore        # newest in outputs/
    python tools/score_vs_official.py <run.csv> --md report.md   # also write markdown
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OFFICIAL_XLSX = (
    REPO / "requirements" / "Hackthon Knowledge Products" / "Database"
    / "ESCAP-RDTII-2.1_ Round 1 Database.xlsx"
)
ECON_SHEET = {"singapore": "Singapore", "sgp": "Singapore", "malaysia": "Malaysia",
              "mys": "Malaysia", "australia": "Australia", "aus": "Australia"}


def load_official(economy: str) -> dict[str, list[tuple]]:
    """{indicator: [(raw_score, law_name), ...]} for the economy's P6/P7 rows."""
    import openpyxl

    sheet = ECON_SHEET.get(economy.strip().lower())
    if not sheet:
        raise SystemExit(f"Unknown economy '{economy}' (use Singapore/Malaysia/Australia).")
    if not OFFICIAL_XLSX.exists():
        raise SystemExit(
            f"Official answer key not found at:\n  {OFFICIAL_XLSX}\n"
            "It ships in the hackathon Resource Library (gitignored — not in the repo). "
            "Download 'ESCAP-RDTII-2.1_ Round 1 Database.xlsx' into that folder to score against it."
        )
    wb = openpyxl.load_workbook(OFFICIAL_XLSX, read_only=True, data_only=True)
    rows = list(wb[sheet].iter_rows(values_only=True))
    # columns: 0 Pillar_ID, 1 Indicator_ID, 2 Raw Score, 3 Act and/or practice
    out: dict[str, list[tuple]] = defaultdict(list)
    for r in rows[1:]:
        ind = str(r[1] or "").strip()
        if ind.startswith(("6.", "7.")):
            out[ind].append((r[2], str(r[3] or "").replace("\n", " ").strip()))
    return out


def _dotted(code: str) -> str:
    code = (code or "").strip().upper()
    if code.startswith("P") and "-I" in code:
        p, i = code[1:].split("-I", 1)
        return f"{p}.{i}"
    return code


def load_run(path: Path) -> list[dict]:
    if path.suffix == ".json":
        doc = json.loads(path.read_text())
        return doc.get("provisions") or doc.get("rows") or (doc if isinstance(doc, list) else [])
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _get(row: dict, *names: str) -> str:
    for n in names:
        for k in row:
            if n.lower() == k.lower():
                return str(row.get(k) or "")
    for n in names:
        for k in row:
            if n.lower() in k.lower():
                return str(row.get(k) or "")
    return ""


def analyze(run: list[dict], official: dict) -> dict:
    # group run rows by indicator; detect hallucination by URL reuse. The tell is
    # DISTINCT LAW NAMES per URL (one law legitimately maps to several indicators
    # = several rows on one URL — that is NOT hallucination), matching the
    # validator gate. 3+ distinct names on one URL = a fabricated name.
    by_ind: dict[str, list[dict]] = defaultdict(list)
    names_per_url: dict[str, set] = defaultdict(set)
    for r in run:
        u = _get(r, "source_url", "final_url")
        # Count by BASE act name (drop a "— s.12A" section suffix): several
        # provisions of the same act on one URL are legitimate, not a hallucination.
        base = re.split(r"[—–]", _get(r, "law_name"))[0]
        n = _norm(base)
        if u and n:
            names_per_url[u].add(n)
    url_counts = {u: len(names) for u, names in names_per_url.items()}
    for r in run:
        ind = _dotted(_get(r, "indicator_id", "indicator"))
        if ind.startswith(("6.", "7.")):
            by_ind[ind].append(r)

    # P6 has 4 indicators (6.1–6.4); P7 has 5 (7.1–7.5).
    indicators = ["6.1", "6.2", "6.3", "6.4", "7.1", "7.2", "7.3", "7.4", "7.5"]
    report = []
    for ind in indicators:
        off = official.get(ind, [])
        off_score = off[0][0] if off else None
        off_law = off[0][1] if off else ""
        rows = by_ind.get(ind, [])
        my_laws = []
        halluc = 0
        has_new = False
        for r in rows:
            law = _get(r, "law_name")
            tag = _get(r, "discovery_tag").upper()
            url = _get(r, "source_url", "final_url")
            is_new = "NEW" in tag
            has_new = has_new or is_new
            if url_counts.get(url, 0) > 2:
                halluc += 1
            my_laws.append({"law": law, "new": is_new, "url": url})
        # divergence: I rely on a NEW law whose name doesn't match the official basis
        divergence = has_new and off is not None and not any(
            _norm(l["law"]) and _norm(l["law"]) in _norm(off_law) or _norm(off_law) in _norm(l["law"])
            for l in my_laws if not l["new"]
        )
        flag = ""
        if off_score is not None and not rows:
            flag = "GAP" if str(off_score) not in ("0", "0.0") else "OK-EMPTY"
        elif halluc:
            flag = "HALLUCINATION"
        elif divergence:
            flag = "NEW-EVIDENCE-DIVERGENCE"
        else:
            flag = "COVERED"
        report.append({
            "indicator": ind, "official_score": off_score, "official_law": off_law,
            "my_rows": len(rows), "my_new": has_new, "halluc_rows": halluc,
            "my_laws": my_laws, "flag": flag,
        })
    return {"report": report, "total_rows": len(run),
            "halluc_total": sum(1 for r in run if url_counts.get(_get(r, "source_url", "final_url"), 0) > 2)}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def render(economy: str, res: dict) -> str:
    L = []
    L.append(f"# Run vs official RDTII answer key — {economy} (Pillars 6/7)\n")
    L.append(f"Run rows: {res['total_rows']}  ·  likely-hallucinated rows "
             f"(≥3 laws share one URL): **{res['halluc_total']}**\n")
    L.append("| Indicator | Official score | Official basis | My rows | NEW? | Flag |")
    L.append("|---|---|---|---|---|---|")
    diverge, gaps, halluc = [], [], []
    for r in res["report"]:
        L.append(f"| {r['indicator']} | {r['official_score']} | {r['official_law'][:40]} | "
                 f"{r['my_rows']} | {'🆕' if r['my_new'] else '-'} | {_badge(r['flag'])} |")
        if r["flag"] == "NEW-EVIDENCE-DIVERGENCE":
            diverge.append(r)
        elif r["flag"] == "GAP":
            gaps.append(r)
        elif r["flag"] == "HALLUCINATION":
            halluc.append(r)
    if diverge:
        L.append("\n## ⚠️ NEW-evidence divergences — VERIFY, then decide")
        L.append("_These indicators rest on a NEW law we discovered, not the law the official key "
                 "cites. If the NEW law is REAL, the score may legitimately differ (Stage-2 discovery "
                 "bonus) — **document it in the submission**. If it is hallucinated, drop it._")
        for r in diverge:
            newlaws = ", ".join(sorted({l["law"][:50] for l in r["my_laws"] if l["new"]}))
            L.append(f"- **{r['indicator']}** — official score {r['official_score']} "
                     f"(basis: {r['official_law'][:40]}); our NEW evidence: {newlaws}")
    if gaps:
        L.append("\n## ❌ Coverage gaps (official has a non-zero score, we found nothing)")
        for r in gaps:
            L.append(f"- **{r['indicator']}** — official {r['official_score']} "
                     f"(basis: {r['official_law'][:45]}) — we produced no evidence.")
    if halluc:
        L.append("\n## 💀 Hallucination-flagged indicators (many law names share one URL)")
        for r in halluc:
            L.append(f"- **{r['indicator']}** — {r['halluc_rows']} suspect rows; verify each URL.")
    return "\n".join(L)


def _badge(flag: str) -> str:
    return {"COVERED": "✅ covered", "OK-EMPTY": "✅ (official 0, none expected)",
            "GAP": "❌ GAP", "HALLUCINATION": "💀 HALLUCINATION",
            "NEW-EVIDENCE-DIVERGENCE": "⚠️ NEW-EVIDENCE"}.get(flag, flag)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", help="run CSV or JSON (default: newest in outputs/ for --economy)")
    ap.add_argument("--economy", help="Singapore/Malaysia/Australia (infers the official sheet + finds newest run)")
    ap.add_argument("--md", help="also write the report to this markdown file")
    args = ap.parse_args(argv)

    if args.run:
        run_path = Path(args.run)
        economy = args.economy
        if not economy:
            m = re.match(r"([A-Za-z]+)", run_path.stem)
            economy = m.group(1) if m else ""
    else:
        if not args.economy:
            ap.error("give a run file or --economy")
        economy = args.economy
        hits = sorted(glob.glob(str(REPO / "outputs" / f"{economy}*_P6-7_*.json")), reverse=True)
        if not hits:
            ap.error(f"no run found in outputs/ for {economy}")
        run_path = Path(hits[0])

    official = load_official(economy)
    run = load_run(run_path)
    res = analyze(run, official)
    report = render(economy, res)
    print(report)
    print(f"\n(source: {run_path})")
    if args.md:
        Path(args.md).write_text(report + f"\n\n_source: {run_path.name}_\n", encoding="utf-8")
        print(f"\nwrote {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
