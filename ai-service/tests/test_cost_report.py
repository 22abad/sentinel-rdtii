"""TDD (red-first) for the deployment-cost reporting seam.

Seam: parse the run's 'Total measured cost:' line into structured numbers, and
aggregate across economies into a full-submission cost — the deployment-cost
pitch number (UN-readiness is a scored dimension; open-weight Ollama = $0 API).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "tools"))


def test_parse_cost_line():
    from cost_report import parse_cost_line

    line = "Total measured cost: 57 LLM calls, 58,651 in / 8,656 out tokens, $0.0254 (India)"
    r = parse_cost_line(line)
    assert r == {"economy": "India", "llm_calls": 57,
                 "input_tokens": 58651, "output_tokens": 8656, "cost_usd": 0.0254}


def test_parse_cost_line_ignores_non_cost_lines():
    from cost_report import parse_cost_line

    assert parse_cost_line("Seed evidence: 0") is None


def test_aggregate_submission_cost():
    from cost_report import aggregate_cost

    per = [
        {"economy": "India", "llm_calls": 57, "input_tokens": 58651, "output_tokens": 8656, "cost_usd": 0.0254},
        {"economy": "China", "llm_calls": 100, "input_tokens": 100000, "output_tokens": 20000, "cost_usd": 0.05},
    ]
    a = aggregate_cost(per)
    assert a["economies"] == 2
    assert a["total_cost_usd"] == round(0.0254 + 0.05, 4)
    assert a["total_llm_calls"] == 157
    assert a["open_weight_cost_usd"] == 0.0   # Ollama/open-weight = $0 API
