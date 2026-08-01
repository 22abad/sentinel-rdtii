"""Merge all per-pillar CSVs into one clean official-format Round-2 submission.

Deduplicates by (economy, indicator, law_name, verbatim) keeping the
highest-confidence row, unifies the Indicator ID to the official dotted form
(6.1) and writes per-economy files + a combined file with the EXACT official
13-column header (CSV_HEADERS) judges validate programmatically.

Usage:
    python tools/merge_submission.py [outputs_dir] [out_dir]
"""
from __future__ import annotations

import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))
from submission.schema import CSV_HEADERS  # official header row judges validate

R2_ECO = {"China", "India", "Indonesia", "Lao PDR", "Mongolia", "Russian Federation", "Thailand"}
DEFAULT_OUT = ROOT / "outputs"
DEFAULT_SUBMIT = DEFAULT_OUT / "round2_submission_merged"


def dotted(ind: str) -> str:
    """P6-I1 -> 6.1; keep dotted tails (P12-I4.1 -> 12.4.1)."""
    ind = (ind or "").strip()
    m = re.match(r"P(\d+)-I(.+)", ind)
    return f"{m.group(1)}.{m.group(2)}" if m else ind


def _col(r: dict, *names: str) -> str:
    for n in names:
        v = r.get(n, "").strip()
        if v:
            return v
    return ""


def read_rows(outputs_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(outputs_dir.glob("*.csv")):
        try:
            for r in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8-sig"))):
                if _col(r, "Economy", "economy") in R2_ECO:
                    rows.append(r)
        except Exception:
            continue
    return rows


def dedup(rows: list[dict]) -> list[dict]:
    best: dict = {}
    for r in rows:
        k = (_col(r, "Economy", "economy"),
             dotted(_col(r, "Indicator ID", "indicator_id", "indicator")),
             _col(r, "Law Name", "law_name")[:80],
             _col(r, "Verbatim Snippet", "verbatim_snippet", "verbatim_quote")[:120])
        if k not in best:
            best[k] = r
        else:
            try:
                if float(_col(r, "Confidence", "confidence") or 0) > float(_col(best[k], "Confidence", "confidence") or 0):
                    best[k] = r
            except ValueError:
                pass
    return list(best.values())


def _source_keys(h: str) -> tuple[str, ...]:
    """Official header -> likely source keys, incl. snake_case variants."""
    low = h.lower()
    return (h, low, low.replace(" ", "_").replace("/", "_"), low.replace(" ", "_"))


def out_row(r: dict) -> dict:
    row = {h: _col(r, *_source_keys(h)) for h in CSV_HEADERS}
    row["Indicator ID"] = dotted(row.get("Indicator ID", ""))
    return row


def merge(outputs_dir: Path = DEFAULT_OUT, submit_dir: Path = DEFAULT_SUBMIT) -> dict:
    """Return {economy: [rows]} after writing per-economy + combined files."""
    rows = dedup(read_rows(outputs_dir))
    by_eco: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_eco[_col(r, "Economy", "economy")].append(out_row(r))

    submit_dir.mkdir(parents=True, exist_ok=True)
    for eco in sorted(by_eco.keys()):
        sorted_rows = sorted(by_eco[eco], key=lambda x: (x["Indicator ID"], x["Law Name"]))
        fn = submit_dir / f"{eco.replace(' ', '_')}_merged.csv"
        with open(fn, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
            w.writeheader()
            w.writerows(sorted_rows)

    all_rows = []
    for eco in sorted(by_eco.keys()):
        all_rows.extend(sorted(by_eco[eco], key=lambda x: (x["Economy"], x["Indicator ID"], x["Law Name"])))
    with open(submit_dir / "all_economies_merged.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(all_rows)

    return {eco: len(rs) for eco, rs in by_eco.items()}


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="merge_submission.py", description=__doc__)
    p.add_argument("outputs_dir", nargs="?", default=str(DEFAULT_OUT), help="dir of per-pillar CSVs")
    p.add_argument("out_dir", nargs="?", default=str(DEFAULT_SUBMIT), help="where to write merged files")
    a = p.parse_args(argv)

    counts = merge(Path(a.outputs_dir), Path(a.out_dir))
    total = sum(counts.values())
    print(f"Round-2 merged submission: {total} rows across {len(counts)} economies -> {a.out_dir}")
    for eco, n in sorted(counts.items()):
        print(f"  {eco}: {n}")
    print(f"Header: {list(CSV_HEADERS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
