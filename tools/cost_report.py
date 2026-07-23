"""Deployment-cost reporting — parse run cost lines, aggregate the full-submission
cost (the UN-deployment-readiness pitch number; open-weight Ollama = $0 API).

Pure/testable parse + aggregate seams; a thin CLI scans run logs at the bottom.
"""
from __future__ import annotations

import re

_COST_RE = re.compile(
    r"Total measured cost:\s*([\d,]+)\s*LLM calls,\s*([\d,]+)\s*in\s*/\s*([\d,]+)\s*out tokens,"
    r"\s*\$([\d.]+)\s*\(([^)]+)\)"
)


def parse_cost_line(line: str) -> dict | None:
    """Parse one 'Total measured cost:' line into structured numbers, or None."""
    m = _COST_RE.search(line or "")
    if not m:
        return None
    n = lambda s: int(s.replace(",", ""))
    return {
        "economy": m.group(5).strip(),
        "llm_calls": n(m.group(1)),
        "input_tokens": n(m.group(2)),
        "output_tokens": n(m.group(3)),
        "cost_usd": float(m.group(4)),
    }


def aggregate_cost(per_economy: list[dict]) -> dict:
    """Sum per-economy costs into the full-submission deployment cost."""
    return {
        "economies": len(per_economy),
        "total_llm_calls": sum(int(r.get("llm_calls", 0)) for r in per_economy),
        "total_input_tokens": sum(int(r.get("input_tokens", 0)) for r in per_economy),
        "total_output_tokens": sum(int(r.get("output_tokens", 0)) for r in per_economy),
        "total_cost_usd": round(sum(float(r.get("cost_usd", 0.0)) for r in per_economy), 4),
        # A key-free open-weight run (Ollama) has zero API cost — the deployment
        # story: same tool, $0 to run on a laptop with no vendor.
        "open_weight_cost_usd": 0.0,
    }


def main(argv=None):
    import argparse
    import glob
    p = argparse.ArgumentParser(prog="cost_report.py", description=__doc__)
    p.add_argument("logs", nargs="+", help="run log files (or globs) to scan")
    a = p.parse_args(argv)
    per: list[dict] = []
    for pattern in a.logs:
        for path in glob.glob(pattern):
            for line in open(path, encoding="utf-8", errors="ignore"):
                r = parse_cost_line(line)
                if r:
                    per.append(r)
    agg = aggregate_cost(per)
    print(f"Full submission ({agg['economies']} economies): {agg['total_llm_calls']} LLM calls, "
          f"{agg['total_input_tokens']:,} in / {agg['total_output_tokens']:,} out, "
          f"${agg['total_cost_usd']} on deepseek — $0 on open-weight Ollama.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
