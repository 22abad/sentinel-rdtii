"""Test the promote-new-law tool builds a correct NEW library entry (dry-run)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "promote_new_law.py"


def test_dry_run_builds_discovered_new_manifest_row(tmp_path):
    text = tmp_path / "provision.txt"
    text.write_text(
        "Section 10. A participation agreement must provide for each party not to "
        "disclose identification information except as required or permitted by law.",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable, str(TOOL),
            "--economy", "Australia",
            "--law-name", "Identity Verification Services Act 2023",
            "--url", "https://www.legislation.gov.au/C2023A00115/latest/text",
            "--pillars", "7", "--indicators", "7.5",
            "--text-file", str(text),
            "--dry-run",
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    # The dry-run prints the manifest row it would append; parse and check it.
    row_line = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")][0]
    row = json.loads(row_line)
    assert row["economy"] == "AUS"
    assert row["discovery_tag"] == "NEW"      # a formal run tags it NEW
    assert row["origin"] == "discovered"      # ...because it's an independent find
    assert row["pillars"] == [7]
    assert row["indicator_hints"] == ["7.5"]
    assert row["law_id"] == "aus-identity-verification-services-act-2023"
    assert len(row["sha256"]) == 64


def test_rejects_too_short_provision(tmp_path):
    text = tmp_path / "tiny.txt"
    text.write_text("too short", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable, str(TOOL), "--economy", "SGP", "--law-name", "X Act",
            "--url", "https://x", "--pillars", "6", "--indicators", "6.4",
            "--text-file", str(text), "--dry-run",
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 2
    assert "too short" in proc.stderr.lower()
