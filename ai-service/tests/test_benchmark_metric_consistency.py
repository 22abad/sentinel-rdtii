"""Prevent audience-facing benchmark claims from drifting between artifacts."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "docs" / "round2-meeting-report.md"
AUDIENCE_ARTIFACTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "pitch-deck-outline.md",
    REPO_ROOT / "docs" / "pitch-deck-script.md",
    REPO_ROOT / "docs" / "video-script.md",
    REPO_ROOT / "docs" / "mentor-review-brief.md",
)


def _report_totals() -> tuple[int, int, int]:
    row_pattern = re.compile(
        r"^\| (?:CHN|IND|IDN|LAO|MNG|RUS|THA) \| \d+ \| "
        r"(\d+) \| (\d+) \| (\d+) \(\d+%\) \|",
        re.MULTILINE,
    )
    rows = row_pattern.findall(REPORT.read_text(encoding="utf-8"))
    assert len(rows) == 7, "expected one benchmark row for each evaluated economy"
    return tuple(sum(int(row[index]) for row in rows) for index in range(3))


def test_round2_report_has_canonical_headline() -> None:
    evaluated, evidence, exact = _report_totals()

    assert (evaluated, evidence, exact) == (500, 351, 251)
    report = REPORT.read_text(encoding="utf-8")
    assert "351 evidence-backed (70.2%)" in report
    assert "251 exact score matches (50.2%)" in report


def test_audience_artifacts_use_the_canonical_benchmark() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in AUDIENCE_ARTIFACTS)

    for stale_claim in (
        "464 rows",
        "464 official baseline rows",
        "464 行",
        "78% evidence yield",
        "46% exact",
        "41–57%",
        "482-test",
        "482 tests",
        "~530",
    ):
        assert stale_claim not in combined, f"stale benchmark claim remains: {stale_claim}"

    for artifact in AUDIENCE_ARTIFACTS:
        text = artifact.read_text(encoding="utf-8")
        assert "500" in text, f"{artifact.name} is missing the evaluated-row count"
        assert "70.2%" in text, f"{artifact.name} is missing the evidence rate"
        assert "50.2%" in text, f"{artifact.name} is missing the exact-match rate"

