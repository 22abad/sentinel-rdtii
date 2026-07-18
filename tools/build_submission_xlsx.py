#!/usr/bin/env python3
"""Assemble the official Round-1 submission workbook from per-economy tool output.

Fills the official OUTPUT_TEMPLATE_31MAY.xlsx "Output Data" sheet with the rows
the tool produced (one CSV per economy), deletes the illustrative example rows,
and preserves the template's Instructions + Indicator Reference sheets and the
header/description rows exactly. Also emits a single consolidated CSV.

Usage:
  python tools/build_submission_xlsx.py --in outputs/final_live_20260718_run2 \
      --out outputs/SUBMISSION_Round1_SENTINEL.xlsx
"""
import argparse, csv, glob, os, sys
import openpyxl

TEMPLATE = ("requirements/Hackthon Knowledge Products/Round 1 Submission Templates/"
            "OUTPUT_TEMPLATE_31MAY.xlsx")
HEADER_ROW = 4          # 'Economy | Law Name | ...' lives on row 4
FIRST_DATA_ROW = 6      # rows 1-5 are title/markers/header/description; 6+ were examples

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--template", default=TEMPLATE)
    a = ap.parse_args()

    wb = openpyxl.load_workbook(a.template)
    ws = wb["Output Data"]
    headers = [ws.cell(row=HEADER_ROW, column=j).value for j in range(1, 14)]
    # sanity: header row must be the 13 official columns
    assert headers[0] == "Economy" and headers[8] == "Verbatim Snippet", headers

    # Unmerge any merged ranges in/below the example region (e.g. the "EXAMPLE
    # ROWS" banner spans all columns). Writing into a merged range only fills the
    # anchor cell, leaving every data row blank past its first column.
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= FIRST_DATA_ROW:
            ws.unmerge_cells(str(rng))

    # Clear every row from FIRST_DATA_ROW down (example + blank template rows).
    if ws.max_row >= FIRST_DATA_ROW:
        ws.delete_rows(FIRST_DATA_ROW, ws.max_row - FIRST_DATA_ROW + 1)

    # Load the tool's per-economy CSVs, in a stable economy order.
    order = {"Singapore": 0, "Malaysia": 1, "Australia": 2}
    files = sorted(glob.glob(os.path.join(a.indir, "*.csv")),
                   key=lambda f: order.get(os.path.basename(f).split("_")[0], 9))
    rows = []
    for f in files:
        with open(f, encoding="utf-8-sig") as fh:
            for d in csv.DictReader(fh):
                rows.append([d.get(h, "") for h in headers])

    r = FIRST_DATA_ROW
    for row in rows:
        for j, val in enumerate(row, start=1):
            ws.cell(row=r, column=j, value=val)
        r += 1
    wb.save(a.out)

    # Consolidated CSV alongside.
    csv_out = os.path.splitext(a.out)[0] + ".csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(headers)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {a.out} and {csv_out}")

if __name__ == "__main__":
    main()
