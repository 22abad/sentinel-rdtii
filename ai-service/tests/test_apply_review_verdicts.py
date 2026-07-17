"""Tests for the legal-review verdict ingestion tool (dry-run, real manifest)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "apply_review_verdicts.py"


def _run(files):
    return subprocess.run([sys.executable, str(TOOL), *files],
                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


def test_banked_review_hint_update_plan(tmp_path):
    """A confirmed card with a different indicator set plans a HINTS update
    against the real manifest entry (dry-run: nothing written)."""
    export = {
        "reviewer": "Reviewer",
        "decisions": [{
            "economy": "MYS",
            "law_name": "Personal Data Protection (Amendment) Act 2024 (Act A1727) — s.12A",
            "url": "https://www.pdp.gov.my/x", "our_hint": ["7.1"],
            "engine_tagged": [], "katie_indicators": ["P7-I4"],
            "verdict": "ok", "note": "DPO duty maps to 7.4, not 7.1",
        }],
    }
    f = tmp_path / "banked.json"
    f.write_text(json.dumps(export))
    before = (REPO_ROOT / "data/law_library/manifest.jsonl").read_text()
    proc = _run([str(f)])
    assert proc.returncode == 0, proc.stderr
    assert "HINTS" in proc.stdout and "7.4" in proc.stdout
    assert "dry-run" in proc.stdout
    # dry-run must not touch the manifest
    assert (REPO_ROOT / "data/law_library/manifest.jsonl").read_text() == before


def test_adjudication_prints_promote_commands(tmp_path):
    export = {
        "reviewer": "Reviewer", "batch": "live-discovery-adjudication",
        "decisions": [
            {"law_name": "Singapore Computer Misuse and Cybersecurity Act",
             "indicator": "P7-I2", "article": "Section 15A",
             "url": "https://sso.agc.gov.sg/Act/CMA1993", "tag": "NEW",
             "verdict": "valid", "correct_indicators": [], "note": ""},
            {"law_name": "Singapore Gas Act, 2001", "indicator": "P6-I4",
             "article": "Section 43(5)", "url": "https://sso.agc.gov.sg/Act/GA2001",
             "tag": "NEW", "verdict": "reject", "correct_indicators": [],
             "note": "licence transfer, not data"},
        ],
    }
    f = tmp_path / "adj.json"
    f.write_text(json.dumps(export))
    proc = _run([str(f)])
    assert proc.returncode == 0, proc.stderr
    assert "ACCEPTED" in proc.stdout and "promote_new_law.py" in proc.stdout
    assert "--indicators 7.2" in proc.stdout
    assert "REJECTED: Singapore Gas Act" in proc.stdout
