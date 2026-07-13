#!/usr/bin/env python3
"""Extract the Round 2 baseline from the official ESCAP RDTII 2.1 database.

Round 2 (final submission) spans ALL 12 pillars across 7 new economies
(China, India, Indonesia, Lao PDR, Mongolia, Russian Federation, Thailand).
The official Round 2 database workbook already contains, per economy:
the act/practice name, official reference URLs and the official raw score
for every filled indicator. That makes it three things at once:

  1. the KNOWN baseline + seed-URL source for the seed-first retrieval path,
  2. the indicator methodology (scoring criteria) for the deterministic scorer,
  3. free ground truth to self-evaluate our tool's output against.

Usage:
    python tools/build_round2_baseline.py           # write both outputs
    python tools/build_round2_baseline.py --check   # verify freshness (CI)

Outputs (checked in — they are derived from judge-provided material):
  data/rdtii21_methodology.json   61 indicators: pillar, category, criteria, scores
  data/round2_inventory.jsonl     one row per (economy, indicator, act):
                                  law name, official URLs, official raw score
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

WORKBOOK = (
    REPO_ROOT / "requirements" / "Hackthon Knowledge Products" / "Database"
    / "ESCAP-RDTII-2.1_ Round 2 Database.xlsx"
)
METHODOLOGY_OUT = REPO_ROOT / "data" / "rdtii21_methodology.json"
INVENTORY_OUT = REPO_ROOT / "data" / "round2_inventory.jsonl"

METHODOLOGY_SHEET = "RDTII 2.1 Methodology"
ECONOMY_SHEETS = {
    "China": "CHN",
    "India": "IND",
    "Indonesia": "IDN",
    "Lao PDR": "LAO",
    "Mongolia": "MNG",
    "Russian Federation": "RUS",
    "Thailand": "THA",
}

_URL_RE = re.compile(r"https?://[^\s,;\)\]。]+")


def _cell(value) -> str:
    """Normalise a cell to a clean string ('' for None)."""
    if value is None:
        return ""
    return str(value).strip()


def _is_indicator_id(token: str) -> bool:
    """Indicator ids look like 1.4, 12.2 or 12.4.1 (pillar-prefixed, dotted)."""
    return bool(re.fullmatch(r"\d{1,2}(\.\d{1,2}){1,2}", token))


def _pillar_of(indicator_id: str) -> int:
    return int(indicator_id.split(".")[0])


def _normalize_ids(raw_ids: list[str]) -> dict[str, str]:
    """Undo Excel float formatting in indicator ids.

    The workbook stores some ids as numbers, so 4.10 arrives as "4.1" and the
    real 4.1 was typed as text "4.01" to survive. Data-driven rule per pillar:
    "N.01" is the true "N.1", and a bare "N.1" that coexists with an "N.01"
    is the true "N.10" (verified against the category names: 4.01 = patents
    = RDTII 4.1; 4.1 = trade secrets = RDTII 4.10; 12.01 = equity limits
    = RDTII 12.1).
    """
    mapping: dict[str, str] = {}
    by_pillar: dict[int, set[str]] = {}
    for rid in raw_ids:
        by_pillar.setdefault(_pillar_of(rid), set()).add(rid)
    for pillar, ids in by_pillar.items():
        zero_one = f"{pillar}.01"
        bare_one = f"{pillar}.1"
        for rid in ids:
            if rid == zero_one:
                mapping[rid] = bare_one
            elif rid == bare_one and zero_one in ids:
                mapping[rid] = f"{pillar}.10"
            else:
                mapping[rid] = rid
    return mapping


def build_methodology(wb) -> list[dict]:
    """Parse the methodology sheet into one record per indicator."""
    ws = wb[METHODOLOGY_SHEET]
    rows = list(ws.iter_rows(values_only=True))

    out: list[dict] = []
    pillar_names: dict[int, str] = {}
    current_pillar = 0
    for row in rows[1:]:
        pid, iid, category = _cell(row[0]), _cell(row[1]), _cell(row[2])
        if pid.isdigit():
            current_pillar = int(pid)
            # Pillar header rows carry the pillar name in the indicator column.
            pillar_names[current_pillar] = iid or category
            continue
        if not _is_indicator_id(iid):
            continue
        out.append({
            "indicator_id": iid,
            "pillar": _pillar_of(iid) or current_pillar,
            "pillar_name": pillar_names.get(_pillar_of(iid), ""),
            "category": category,
            "criteria": _cell(row[3]),
            "possible_scores": _cell(row[4]),
        })
    return out


def build_inventory(wb) -> list[dict]:
    """Parse every economy sheet into (economy, indicator, act) rows."""
    out: list[dict] = []
    for sheet, code in ECONOMY_SHEETS.items():
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        header, body = rows[0], rows[1:]
        for row in body:
            iid = _cell(row[1])
            if not _is_indicator_id(iid):
                continue  # pillar header / blank rows
            act = _cell(row[3])
            urls: list[str] = []
            for cell in row[6:]:  # Timeframe onward — References span several columns
                urls.extend(_URL_RE.findall(_cell(cell)))
            # Preserve order, drop duplicates.
            seen: set[str] = set()
            urls = [u for u in urls if not (u in seen or seen.add(u))]
            raw = _cell(row[2])
            try:
                official_score = float(raw)
            except ValueError:
                official_score = None
            out.append({
                "economy": code,
                "pillar": _pillar_of(iid),
                "indicator_id": iid,
                "official_score": official_score,
                "law_name": act,
                "coverage": _cell(row[4])[:300],
                "timeframe": _cell(row[6])[:200],
                "urls": urls,
            })
    return out


def render(methodology: list[dict], inventory: list[dict]) -> tuple[str, str]:
    meth = json.dumps(methodology, ensure_ascii=False, indent=1) + "\n"
    inv = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in inventory)
    return meth, inv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_round2_baseline.py", description=__doc__)
    p.add_argument("--check", action="store_true", help="fail if outputs are stale")
    args = p.parse_args(argv)

    import openpyxl

    wb = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    methodology = build_methodology(wb)
    inventory = build_inventory(wb)

    # Normalise Excel-mangled ids once, consistently across both outputs.
    id_map = _normalize_ids([m["indicator_id"] for m in methodology])
    for record in [*methodology, *inventory]:
        raw = record["indicator_id"]
        record["source_id"] = raw
        record["indicator_id"] = id_map.get(raw, raw)

    meth_text, inv_text = render(methodology, inventory)

    if args.check:
        cur_m = METHODOLOGY_OUT.read_text(encoding="utf-8") if METHODOLOGY_OUT.exists() else ""
        cur_i = INVENTORY_OUT.read_text(encoding="utf-8") if INVENTORY_OUT.exists() else ""
        if cur_m != meth_text or cur_i != inv_text:
            print("round2 baseline is stale — run: python tools/build_round2_baseline.py",
                  file=sys.stderr)
            return 1
        print(f"round2 baseline up to date ({len(methodology)} indicators, "
              f"{len(inventory)} inventory rows).")
        return 0

    METHODOLOGY_OUT.write_text(meth_text, encoding="utf-8")
    INVENTORY_OUT.write_text(inv_text, encoding="utf-8")

    by_econ: dict[str, int] = {}
    url_total = 0
    for r in inventory:
        by_econ[r["economy"]] = by_econ.get(r["economy"], 0) + 1
        url_total += len(r["urls"])
    print(f"Wrote {len(methodology)} indicators -> {METHODOLOGY_OUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {len(inventory)} inventory rows ({url_total} official URLs) "
          f"-> {INVENTORY_OUT.relative_to(REPO_ROOT)}")
    for econ, n in sorted(by_econ.items()):
        print(f"  {econ}: {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
