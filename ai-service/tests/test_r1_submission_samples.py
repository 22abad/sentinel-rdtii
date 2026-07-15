"""Contract checks for the committed Round 1 review artifacts."""

from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "docs" / "r1-submission-sample"


def test_committed_samples_have_complete_citation_metadata():
    for path in sorted(SAMPLE_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows, path.name
        for row in rows:
            assert row["article"].strip(), (path.name, row["law_name"])
            assert row["last_amended"].strip(), (path.name, row["law_name"])
            assert row["location_reference"].strip(), (path.name, row["law_name"])


def test_queensland_baseline_is_not_claimed_as_new():
    path = SAMPLE_DIR / "Australia_P6-7.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        qld_rows = [
            row for row in csv.DictReader(handle)
            if "Information Privacy Act 2009 (QLD)" in row["law_name"]
        ]
    assert qld_rows
    assert {row["discovery_tag"] for row in qld_rows} == {"KNOWN"}
