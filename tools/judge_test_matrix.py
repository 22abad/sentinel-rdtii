#!/usr/bin/env python3
"""Judge-simulation graded test matrix for the Round 1 CLI.

Judges probe a tool from easy to hard. This harness runs representative
`main.py` invocations in tiers of increasing difficulty, and for each grades
the OUTPUT the way a judge would: did it run, did it write files, and are the
rows judge-usable (verbatim quote present, official URL, article-level cite,
no obviously hallucinated law name, honest emptiness).

    python tools/judge_test_matrix.py                 # tiers 1-3 (offline+robustness)
    python tools/judge_test_matrix.py --live          # also tier 4 (network)

Writes docs/judge-test-report.md and prints a pass/fail summary. Exit code is
non-zero if any non-live tier case fails, so it doubles as a pre-submission gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "outputs" / "judge_matrix"
FIXTURES = OUT_DIR / "_fixtures"
REPORT = REPO_ROOT / "docs" / "judge-test-report.md"
PYTHON = sys.executable
SCANNED_PDF = (
    REPO_ROOT / "requirements" / "Hackthon Knowledge Products" / "Database"
    / "Sample legislations" / "PDF of scanned documents"
    / "India-Public_Procurement_order_2017.pdf"
)

# A law name that is probably hallucinated: mixes unrelated jurisdictions, or
# says "Unknown". Cheap heuristic, only used as a warning signal.
_SUSPECT_NAME = re.compile(
    r"unknown country|south korea queensland|new zealand .*singapore",
    re.IGNORECASE,
)


@dataclass
class Case:
    tier: int
    name: str
    args: list[str]
    expect: str  # "output" | "clean_error" | "empty_ok"
    network: bool = False
    is_pdf: bool = False  # provenance is a file path, not an http URL


@dataclass
class Result:
    case: Case
    exit_code: int
    wrote_files: bool
    rows: int
    quality: dict = field(default_factory=dict)
    note: str = ""
    passed: bool = False
    seconds: float = 0.0


CASES = [
    # Tier 1 — the trivial documented command, mandatory scope, deterministic.
    Case(1, "SGP P6 offline (the headline command)", ["--economy", "Singapore", "--pillar", "6", "--offline"], "output"),
    Case(1, "SGP P7 offline", ["--economy", "Singapore", "--pillar", "7", "--offline"], "output"),
    # Tier 2 — full mandatory scope + the required OCR path.
    Case(2, "MYS P6+7 offline", ["--economy", "Malaysia", "--pillar", "6,7", "--offline"], "output"),
    Case(2, "AUS P6+7 offline", ["--economy", "Australia", "--pillar", "6,7", "--offline"], "output"),
    Case(2, "Scanned PDF -> citations (OCR)", ["--economy", "India", "--pillar", "2", "--pdf", str(SCANNED_PDF)], "output", is_pdf=True),
    # Tier 3 — robustness / adversarial inputs a judge will try.
    Case(3, "Misspelled economy -> clean error", ["--economy", "Singapoore", "--pillar", "6", "--offline"], "clean_error"),
    Case(3, "Invalid pillar -> clean error", ["--economy", "Singapore", "--pillar", "13", "--offline"], "clean_error"),
    Case(3, "Missing PDF path -> clean error", ["--economy", "India", "--pillar", "2", "--pdf", "/no/such.pdf"], "clean_error"),
    Case(3, "Mixed-case economy tolerated", ["--economy", "sInGaPoRe", "--pillar", "6", "--offline"], "output"),
    Case(3, "Uncovered economy offline -> empty, honest", ["--economy", "Mongolia", "--pillar", "6", "--offline", "--allow-empty"], "empty_ok"),
    # Tier 4 — network / live (opt-in; flaky by nature).
    Case(4, "SGP P6 seed-first (default, network)", ["--economy", "Singapore", "--pillar", "6", "--max-documents", "1"], "output", network=True),
    Case(4, "SGP P6 strict-live (auditable crawl)", ["--economy", "Singapore", "--pillar", "6", "--strict-live", "--max-documents", "1"], "output", network=True),
    # Tier 5 — hard / honesty stress (offline, deterministic, no network).
    Case(5, "Indicator filter (--indicators 6.1)", ["--economy", "Singapore", "--pillar", "6", "--indicators", "6.1", "--offline", "--allow-empty"], "empty_ok"),
    Case(5, "All 12 pillars on a mandatory economy", ["--economy", "Singapore", "--pillar", "all", "--offline"], "output"),
    Case(5, "Mismatched-pillar PDF -> honest, no hallucination", ["--economy", "India", "--pillar", "7", "--pdf", str(SCANNED_PDF), "--allow-empty"], "empty_ok", is_pdf=True),
    Case(5, "Malformed PDF -> clean error", ["--economy", "India", "--pillar", "6", "--pdf", str(FIXTURES / "malformed.pdf")], "clean_error"),
    Case(5, "Blank PDF -> empty, honest", ["--economy", "India", "--pillar", "6", "--pdf", str(FIXTURES / "blank.pdf"), "--allow-empty"], "empty_ok", is_pdf=True),
    Case(5, "Huge --limit does not crash", ["--economy", "Singapore", "--pillar", "6", "--offline", "--limit", "500"], "output"),
    # Tier 6 — malformed-arg edge cases (deterministic, offline).
    Case(6, "Duplicate pillars 6,6,7 -> deduped", ["--economy", "Singapore", "--pillar", "6,6,7", "--offline"], "output"),
    Case(6, "Text file renamed .pdf -> clean error", ["--economy", "India", "--pillar", "6", "--pdf", str(FIXTURES / "fake.pdf")], "clean_error"),
    Case(6, "Zero pillar -> clean error", ["--economy", "Singapore", "--pillar", "0", "--offline"], "clean_error"),
]


def _grade_output(out_dir: Path) -> tuple[int, dict]:
    csvs = sorted(out_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not csvs:
        return 0, {}
    rows = list(csv.DictReader(csvs[-1].open(encoding="utf-8-sig")))
    if not rows:
        return 0, {}
    n = len(rows)
    q = {
        "verbatim_pct": round(100 * sum(1 for r in rows if len(r.get("verbatim_snippet", "")) > 20) / n),
        "url_pct": round(100 * sum(1 for r in rows if r.get("source_url", "").startswith("http")) / n),
        "source_present_pct": round(100 * sum(1 for r in rows if r.get("source_url", "").strip()) / n),
        "article_pct": round(100 * sum(1 for r in rows if r.get("article", "").strip()) / n),
        "suspect_names": sum(1 for r in rows if _SUSPECT_NAME.search(r.get("law_name", ""))),
        "duplicate_rows": n - len({(r["indicator_id"], r["law_name"], " ".join(r["verbatim_snippet"].split()).casefold()) for r in rows}),
    }
    return n, q


def run_case(case: Case, offline_env: dict) -> Result:
    case_dir = OUT_DIR / f"t{case.tier}_{re.sub(r'[^a-z0-9]+', '-', case.name.lower())[:40]}"
    case_dir.mkdir(parents=True, exist_ok=True)
    for f in case_dir.glob("*"):
        f.unlink()
    cmd = [PYTHON, str(REPO_ROOT / "main.py"), *case.args, "--output-dir", str(case_dir), "--format", "both"]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=offline_env, timeout=900)
    secs = time.time() - t0
    rows, quality = _grade_output(case_dir)
    wrote = rows > 0
    res = Result(case=case, exit_code=proc.returncode, wrote_files=wrote, rows=rows,
                 quality=quality, seconds=round(secs, 1))

    if case.expect == "output":
        # A provided PDF has no official http URL; its provenance is the file
        # path (source_present_pct), so grade that instead of url_pct.
        prov_pct = quality.get("source_present_pct", 0) if case.is_pdf else quality.get("url_pct", 0)
        prov_label = "source" if case.is_pdf else "url"
        res.passed = proc.returncode == 0 and wrote and quality.get("verbatim_pct", 0) >= 80 \
            and prov_pct >= 80 and quality.get("suspect_names", 1) == 0 \
            and quality.get("duplicate_rows", 1) == 0
        if not res.passed:
            bad = []
            if proc.returncode != 0: bad.append(f"exit={proc.returncode}")
            if not wrote: bad.append("no output files")
            if quality.get("verbatim_pct", 0) < 80: bad.append(f"verbatim {quality.get('verbatim_pct')}%")
            if prov_pct < 80: bad.append(f"{prov_label} {prov_pct}%")
            if quality.get("suspect_names"): bad.append(f"{quality['suspect_names']} suspect names")
            if quality.get("duplicate_rows"): bad.append(f"{quality['duplicate_rows']} dup rows")
            res.note = "; ".join(bad)
    elif case.expect == "clean_error":
        # Fail-fast with a non-zero code and NO traceback in stderr.
        traceback = "Traceback (most recent call last)" in proc.stderr
        res.passed = proc.returncode != 0 and not traceback and not wrote
        res.note = "traceback leaked" if traceback else ("wrote files on error" if wrote else "")
    elif case.expect == "empty_ok":
        res.passed = proc.returncode == 0
        res.note = "" if res.passed else f"exit={proc.returncode}"
    return res


def render(results: list[Result]) -> str:
    lines = ["# Judge-simulation test matrix", "",
             "_Graded `main.py` runs from easy to hard, scored the way a judge grades "
             "output. Regenerate with `python tools/judge_test_matrix.py`._", ""]
    for tier in sorted({r.case.tier for r in results}):
        trs = [r for r in results if r.case.tier == tier]
        label = {1: "Trivial (headline command)", 2: "Mandatory scope + OCR",
                 3: "Robustness / adversarial", 4: "Live / network", 5: "Hard / honesty stress", 6: "Malformed-argument edge cases"}.get(tier, str(tier))
        passed = sum(1 for r in trs if r.passed)
        lines += [f"## Tier {tier} — {label}  ({passed}/{len(trs)} pass)", "",
                  "| Case | Result | Rows | Quality | Notes |", "|---|---|---|---|---|"]
        for r in trs:
            mark = "✅" if r.passed else "❌"
            q = r.quality
            qstr = (f"verbatim {q.get('verbatim_pct','-')}% · url {q.get('url_pct','-')}% · "
                    f"art {q.get('article_pct','-')}%" if q else "—")
            lines.append(f"| {r.case.name} | {mark} ({r.seconds}s) | {r.rows} | {qstr} | {r.note} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import os

    p = argparse.ArgumentParser(prog="judge_test_matrix.py", description=__doc__)
    p.add_argument("--live", action="store_true", help="also run tier 4 (network)")
    p.add_argument("--tier", type=int, default=None, help="run only this tier")
    args = p.parse_args(argv)

    env = dict(os.environ)
    env.setdefault("RDTII_LLM_PROVIDER", "deepseek")

    # Self-contained adversarial fixtures (no binaries in the repo).
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "malformed.pdf").write_bytes(b"%PDF-1.4\n garbage not a real pdf body\n")
    (FIXTURES / "fake.pdf").write_bytes(b"This is plain text, not a PDF. Section 1. Data must stay local.\n")
    try:
        import fitz  # pymupdf
        doc = fitz.open(); doc.new_page(); doc.save(str(FIXTURES / "blank.pdf")); doc.close()
    except Exception:
        (FIXTURES / "blank.pdf").write_bytes(b"%PDF-1.4\n")

    cases = [c for c in CASES if (args.live or not c.network)]
    if args.tier:
        cases = [c for c in cases if c.tier == args.tier]

    results: list[Result] = []
    for c in cases:
        print(f"[tier {c.tier}] {c.name} ...", flush=True)
        try:
            r = run_case(c, env)
        except subprocess.TimeoutExpired:
            r = Result(case=c, exit_code=-1, wrote_files=False, rows=0, note="TIMEOUT", passed=False)
        results.append(r)
        print(f"    {'PASS' if r.passed else 'FAIL'} rows={r.rows} {r.note}", flush=True)

    REPORT.write_text(render(results), encoding="utf-8")
    non_live_fail = [r for r in results if not r.passed and not r.case.network]
    print(f"\n{sum(1 for r in results if r.passed)}/{len(results)} pass. Report: {REPORT.relative_to(REPO_ROOT)}")
    return 1 if non_live_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
