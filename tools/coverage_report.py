"""Official scorable-cell coverage for a Round-2 submission (pure, testable).

A cell = (economy, indicator). It is OFFICIAL NON-ZERO when the RDTII database
gives it a score > 0. The submission COVERS a cell when it has >=1 evidence row
for that (economy, indicator). This module computes coverage with no files/no
network so it is unit-testable; a thin CLI at the bottom points it at real dirs.
"""
from __future__ import annotations

import re

# Submission CSVs use display names; the inventory uses ISO-3 codes.
_ECON_CODE = {
    "china": "CHN", "india": "IND", "indonesia": "IDN", "lao pdr": "LAO",
    "lao_pdr": "LAO", "mongolia": "MNG", "russian federation": "RUS",
    "russian_federation": "RUS", "thailand": "THA",
}


def _code(economy: str) -> str:
    e = (economy or "").strip()
    return _ECON_CODE.get(e.lower(), e.upper())


def _dotted(indicator_id: str) -> str | None:
    """'P6-I1' -> '6.1'; a bare '6.1' passes through."""
    m = re.match(r"P(\d+)-I(.+)", indicator_id or "")
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return indicator_id or None


def official_cell_coverage(submission_rows: list[dict], inventory_rows: list[dict]) -> dict:
    nonzero: set[tuple[str, str]] = set()
    for d in inventory_rows:
        try:
            score = float(d.get("official_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score > 0:
            nonzero.add((_code(d.get("economy", "")), str(d.get("indicator_id", ""))))

    covered_by_econ: dict[str, set[str]] = {}
    for r in submission_rows:
        ind = _dotted(r.get("Indicator ID", ""))
        if not ind:
            continue
        covered_by_econ.setdefault(_code(r.get("Economy", "")), set()).add(ind)

    by_economy: dict[str, dict] = {}
    by_pillar: dict[str, dict] = {}
    uncovered: list[tuple[str, str]] = []
    covered = 0
    for econ, ind in sorted(nonzero):
        pillar = ind.split(".")[0]
        be = by_economy.setdefault(econ, {"covered": 0, "total": 0})
        bp = by_pillar.setdefault(pillar, {"covered": 0, "total": 0})
        be["total"] += 1
        bp["total"] += 1
        if ind in covered_by_econ.get(econ, set()):
            be["covered"] += 1
            bp["covered"] += 1
            covered += 1
        else:
            uncovered.append((econ, ind))

    total = len(nonzero)
    return {
        "total_nonzero_cells": total,
        "covered_cells": covered,
        "coverage_rate": round(covered / total, 3) if total else 0.0,
        "by_economy": by_economy,
        "by_pillar": by_pillar,
        "uncovered_cells": uncovered,
    }


def classify_gap(*, has_local_text: bool, is_statute: bool) -> str:
    """Root cause of an uncovered cell — decides WHERE the fix goes.

    FETCH_GAP     : no local text at all → get the document.
    CORPUS_QUALITY: text present but only a summary/stub → re-fetch the statute.
    EXTRACTION    : a real statute is present but no provision was surfaced →
                    extraction/classification recall.
    """
    if not has_local_text:
        return "FETCH_GAP"
    return "EXTRACTION" if is_statute else "CORPUS_QUALITY"


def submission_stats(rows: list[dict]) -> dict:
    """Shape of a submission for the meeting report / pitch: total rows, distinct
    laws & indicators, NEW/KNOWN split, per-pillar row counts."""
    laws: set = set()
    indicators: set = set()
    by_tag: dict[str, int] = {}
    by_pillar: dict[str, int] = {}
    for r in rows:
        laws.add((_code(r.get("Economy", "")), r.get("Law Name", "")))
        ind = r.get("Indicator ID", "")
        indicators.add((_code(r.get("Economy", "")), ind))
        tag = r.get("Discovery Tag", "") or "?"
        by_tag[tag] = by_tag.get(tag, 0) + 1
        dotted = _dotted(ind)
        if dotted:
            pillar = dotted.split(".")[0]
            by_pillar[pillar] = by_pillar.get(pillar, 0) + 1
    return {
        "total_rows": len(rows),
        "distinct_laws": len(laws),
        "distinct_indicators": len(indicators),
        "by_tag": by_tag,
        "by_pillar": by_pillar,
    }


def aggregate_cell_status(kinds_by_cell: dict[tuple, list[str]]) -> dict[tuple, tuple[bool, bool]]:
    """Per (economy, indicator) cell: (has_text, is_statute), aggregated over ALL
    manifest entries for the cell — not just the one whose law_name matches the
    inventory string exactly. A cell that holds both a summary and a real statute
    (e.g. THA 12.7) is a statute-bearing cell; the old law_name-exact join would
    tag it from the summary alone and misclassify it as CORPUS_QUALITY."""
    return {
        cell: (bool(kinds), "STATUTE" in kinds)
        for cell, kinds in kinds_by_cell.items()
    }


_CAUSE_ORDER = {"FETCH_GAP": 0, "CORPUS_QUALITY": 1, "EXTRACTION": 2}


def gap_worklist(cells: list[dict]) -> list[dict]:
    """One actionable row per uncovered cell — {economy, indicator, cause} —
    ordered so the tractable fixes (fetch a doc, re-fetch a statute) lead and the
    hard extraction-recall cells trail."""
    out = [
        {"economy": c.get("economy", ""), "indicator": c.get("indicator", ""),
         "cause": classify_gap(has_local_text=c.get("has_text", False),
                               is_statute=c.get("is_statute", False))}
        for c in cells
    ]
    out.sort(key=lambda r: (_CAUSE_ORDER.get(r["cause"], 9), r["economy"], r["indicator"]))
    return out


def summarize_gaps(cells: list[dict]) -> dict:
    """Aggregate uncovered cells (each tagged has_text/is_statute) into the
    reproducible 3-way split — EXTRACTION / CORPUS_QUALITY / FETCH_GAP — overall
    and per pillar, so effort routes to the right lever."""
    by_cause: dict[str, int] = {}
    by_pillar: dict[str, dict] = {}
    for c in cells:
        cause = classify_gap(has_local_text=c.get("has_text", False),
                             is_statute=c.get("is_statute", False))
        by_cause[cause] = by_cause.get(cause, 0) + 1
        pillar = str(c.get("indicator", "")).split(".")[0]
        bp = by_pillar.setdefault(pillar, {})
        bp[cause] = bp.get(cause, 0) + 1
    return {"by_cause": by_cause, "by_pillar": by_pillar}


def coverage_delta(old: dict, new: dict) -> dict:
    """Change between two coverage reports (e.g. before/after a corpus re-fetch):
    total covered delta, before/after rates, and per-pillar gains (only pillars
    whose covered count moved)."""
    def _rate(r):
        t = r.get("total_nonzero_cells", 0)
        return round(r.get("covered_cells", 0) / t, 3) if t else 0.0

    gains: dict[str, int] = {}
    op, np_ = old.get("by_pillar", {}), new.get("by_pillar", {})
    for pillar in set(op) | set(np_):
        g = np_.get(pillar, {}).get("covered", 0) - op.get(pillar, {}).get("covered", 0)
        if g:
            gains[pillar] = g
    return {
        "covered_delta": new.get("covered_cells", 0) - old.get("covered_cells", 0),
        "rate_before": _rate(old),
        "rate_after": _rate(new),
        "pillar_gains": gains,
    }


# ── thin CLI adapter (file IO; the tested seam is official_cell_coverage) ─────
def _load_inventory(path):
    import json
    from pathlib import Path
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load_submission(directory):
    import csv
    import glob
    rows = []
    for f in glob.glob(str(directory) + "/*.csv"):
        with open(f, newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def _gap_cell_status(uncovered, inventory, repo):
    """Tag each uncovered (economy, dotted-indicator) cell with has_text /
    is_statute from the corpus manifest — the input to summarize_gaps.

    Aggregates manifest entries per (economy, indicator), NOT per exact
    law_name: the inventory law_name is often a ';\\n\\n'-joined bundle or
    worded differently from the manifest record, so a law_name-exact join
    misses statutes that ARE present (e.g. THA 12.7's Telecommunications
    Business Act) and mislabels the cell as CORPUS_QUALITY."""
    import sys as _sys
    _sys.path.insert(0, str(repo / "tools"))
    from restore_corpus import _load_manifest, _is_corrupt, classify_text_quality
    from pathlib import Path

    # (economy, indicator) -> classify_text_quality kinds of every readable entry
    kinds_by_cell: dict[tuple, list[str]] = {}
    for m in _load_manifest():
        if m.get("status") not in ("ok", "cached") or _is_corrupt(m)[0]:
            continue
        pth = repo / m.get("text_path", "")
        if not pth.exists():
            continue
        key = (m.get("economy", ""), str(m.get("indicator_id", "")))
        kinds_by_cell.setdefault(key, []).append(
            classify_text_quality(pth.read_text(encoding="utf-8", errors="ignore"))[0])

    status = aggregate_cell_status(kinds_by_cell)
    out = []
    for econ, ind in uncovered:
        has_text, is_stat = status.get((econ, ind), (False, False))
        out.append({"economy": econ, "indicator": ind, "has_text": has_text, "is_statute": is_stat})
    return out


def main(argv=None):
    import argparse
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(prog="coverage_report.py", description=__doc__)
    p.add_argument("submission_dir", help="dir of per-economy submission CSVs")
    p.add_argument("--inventory", default=str(repo / "data" / "round2_inventory.jsonl"))
    p.add_argument("--gaps", action="store_true",
                   help="also break uncovered cells into fetch/corpus/extraction causes")
    p.add_argument("--worklist", metavar="CSV",
                   help="write the actionable uncovered-cell worklist to this CSV")
    a = p.parse_args(argv)
    inventory = _load_inventory(a.inventory)
    r = official_cell_coverage(_load_submission(a.submission_dir), inventory)
    print(f"Official scorable-cell coverage: {r['covered_cells']}/{r['total_nonzero_cells']} "
          f"({r['coverage_rate']:.1%})")
    print("  by economy:", {e: f"{v['covered']}/{v['total']}" for e, v in sorted(r["by_economy"].items())})
    print("  by pillar:", {k: f"{v['covered']}/{v['total']}"
                           for k, v in sorted(r["by_pillar"].items(), key=lambda x: int(x[0]))})
    if a.gaps or a.worklist:
        status = _gap_cell_status(r["uncovered_cells"], inventory, repo)
        print("  gap root cause:", summarize_gaps(status)["by_cause"])
        if a.worklist:
            import csv as _csv
            wl = gap_worklist(status)
            with open(a.worklist, "w", newline="", encoding="utf-8") as fh:
                w = _csv.DictWriter(fh, fieldnames=["cause", "economy", "indicator"])
                w.writeheader()
                for row in wl:
                    w.writerow({"cause": row["cause"], "economy": row["economy"],
                                "indicator": row["indicator"]})
            print(f"  worklist ({len(wl)} cells) -> {a.worklist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
