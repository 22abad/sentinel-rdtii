from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "discovery_coverage.py"
SPEC = importlib.util.spec_from_file_location("discovery_coverage", SCRIPT_PATH)
assert SPEC and SPEC.loader
coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage
SPEC.loader.exec_module(coverage)


def test_required_country_coverage_contract_is_complete_and_valid():
    payload = coverage.load_contract()

    coverage.validate_contract(payload)

    assert payload["scope"]["countries"] == ["AUS", "MYS", "SGP"]
    assert payload["scope"]["indicators"] == [
        "6.1", "6.2", "6.3", "6.4", "6.5",
        "7.1", "7.2", "7.3", "7.4", "7.5",
    ]
    assert sum(len(cells) for cells in payload["countries"].values()) == 30


def test_smoke_verified_cells_name_passing_discovery_and_fetch_checks():
    payload = coverage.load_contract()

    verified = [
        cell
        for cells in payload["countries"].values()
        for cell in cells.values()
        if cell["status"] == "smoke_verified"
    ]

    assert len(verified) == 20
    for cell in verified:
        assert cell["instruments"]
        assert all(instrument["live_discovery"] == "passed" for instrument in cell["instruments"])
        assert all(instrument["text_fetch"] == "passed" for instrument in cell["instruments"])
        assert all(instrument["smoke_case"] for instrument in cell["instruments"])


def test_rendered_coverage_report_is_current():
    payload = coverage.load_contract()
    rendered = coverage.render_markdown(payload)

    assert coverage.DEFAULT_OUTPUT.read_text(encoding="utf-8") == rendered
