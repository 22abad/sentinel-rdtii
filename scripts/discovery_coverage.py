#!/usr/bin/env python3
"""Validate and render the required-country Discovery coverage contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE_ROOT = REPO_ROOT / "ai-service"
sys.path.insert(0, str(AI_SERVICE_ROOT))

from discovery.evidence_markers import known_evidence_markers  # noqa: E402
from discovery.smoke_cases import SMOKE_CASES  # noqa: E402


DEFAULT_INPUT = REPO_ROOT / "ai-service" / "discovery" / "required_country_coverage.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "discovery-required-country-coverage.md"
VALID_STATUSES = {
    "unresearched",
    "source_identified",
    "live_discovered",
    "text_fetched",
    "smoke_verified",
    "manual_review_required",
}
VALID_EVIDENCE_TYPES = {"positive", "positive_or_negative", "negative_requires_review"}
VALID_CHECK_STATES = {"untested", "passed", "failed", "not_applicable"}


def load_contract(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("coverage contract must be a mapping")
    return payload


def validate_contract(payload: dict[str, Any]) -> None:
    scope = payload.get("scope") or {}
    expected_countries = [str(value) for value in scope.get("countries") or []]
    expected_indicators = [str(value) for value in scope.get("indicators") or []]
    countries = payload.get("countries") or {}
    errors: list[str] = []
    smoke_references: list[tuple[str, str, str]] = []

    if set(countries) != set(expected_countries):
        errors.append("country keys must exactly match scope.countries")

    for country in expected_countries:
        cells = countries.get(country) or {}
        if set(cells) != set(expected_indicators):
            errors.append(f"{country} indicator keys must exactly match scope.indicators")
            continue
        for indicator in expected_indicators:
            cell = cells[indicator]
            label = f"{country} {indicator}"
            if cell.get("status") not in VALID_STATUSES:
                errors.append(f"{label} has invalid status")
            if cell.get("evidence_type") not in VALID_EVIDENCE_TYPES:
                errors.append(f"{label} has invalid evidence_type")
            instruments = cell.get("instruments")
            if not isinstance(instruments, list):
                errors.append(f"{label} instruments must be a list")
                continue
            if cell.get("status") in {"source_identified", "live_discovered", "text_fetched", "smoke_verified"} and not instruments:
                errors.append(f"{label} status requires at least one instrument")
            for index, instrument in enumerate(instruments):
                instrument_label = f"{label} instrument {index + 1}"
                for field in ("title", "official_source", "url", "role"):
                    if not str(instrument.get(field) or "").strip():
                        errors.append(f"{instrument_label} is missing {field}")
                for field in ("live_discovery", "text_fetch"):
                    if instrument.get(field) not in VALID_CHECK_STATES:
                        errors.append(f"{instrument_label} has invalid {field}")
                if cell.get("status") == "smoke_verified" and not instrument.get("smoke_case"):
                    errors.append(f"{instrument_label} must name its smoke_case")
                smoke_case = str(instrument.get("smoke_case") or "").strip()
                if smoke_case:
                    smoke_references.append((smoke_case, country, indicator))
                    if cell.get("status") != "smoke_verified":
                        errors.append(
                            f"{instrument_label} names smoke_case {smoke_case} "
                            "but is not smoke_verified"
                        )

    smoke_cases_by_id = {case.case_id: case for case in SMOKE_CASES}
    known_markers = known_evidence_markers()
    smoke_reference_ids = [case_id for case_id, _country, _indicator in smoke_references]
    if len(smoke_cases_by_id) != len(SMOKE_CASES):
        errors.append("SMOKE_CASES contains duplicate case ids")
    for case in SMOKE_CASES:
        unknown_markers = sorted(set(case.required_evidence_markers) - known_markers)
        if unknown_markers:
            errors.append(
                f"smoke_case {case.case_id} has unknown evidence marker(s): "
                + ", ".join(unknown_markers)
            )
        if len(case.required_evidence_markers) != len(set(case.required_evidence_markers)):
            errors.append(f"smoke_case {case.case_id} has duplicate evidence markers")
    if len(smoke_reference_ids) != len(set(smoke_reference_ids)):
        errors.append("coverage contract references a smoke_case more than once")

    for case_id, country, indicator in smoke_references:
        smoke_case = smoke_cases_by_id.get(case_id)
        if smoke_case is None:
            errors.append(f"{country} {indicator} references unknown smoke_case {case_id}")
            continue
        if smoke_case.country != country or smoke_case.indicator != indicator:
            errors.append(
                f"{country} {indicator} smoke_case {case_id} maps to "
                f"{smoke_case.country} {smoke_case.indicator}"
            )

    missing_smoke_cases = sorted(set(smoke_cases_by_id) - set(smoke_reference_ids))
    if missing_smoke_cases:
        errors.append(
            "coverage contract does not reference smoke case(s): "
            + ", ".join(missing_smoke_cases)
        )

    if errors:
        raise ValueError("invalid coverage contract:\n- " + "\n- ".join(errors))


def render_markdown(payload: dict[str, Any]) -> str:
    statuses = {
        "unresearched": "待调查",
        "source_identified": "已定位来源",
        "live_discovered": "可实时发现",
        "text_fetched": "已抓正文",
        "smoke_verified": "Smoke 已验证",
        "manual_review_required": "需人工判断",
    }
    indicators = [str(value) for value in payload["scope"]["indicators"]]
    lines = [
        "# Required-country Discovery coverage",
        "",
        "> Generated from `ai-service/discovery/required_country_coverage.yaml`; do not edit by hand.",
        "",
        f"Guide: **{payload['guide_version']}**",
        "",
        "| Country | " + " | ".join(indicators) + " |",
        "| --- | " + " | ".join("---" for _ in indicators) + " |",
    ]
    for country in payload["scope"]["countries"]:
        cells = payload["countries"][country]
        lines.append(
            f"| {country} | "
            + " | ".join(statuses[cells[indicator]["status"]] for indicator in indicators)
            + " |"
        )

    lines.extend([
        "",
        "## Evidence inventory",
        "",
        "`需人工判断` means that Discovery may collect leads, but an empty result set cannot prove the legal measure or framework is absent.",
        "",
    ])
    for country in payload["scope"]["countries"]:
        lines.extend([f"### {country}", ""])
        for indicator in indicators:
            cell = payload["countries"][country][indicator]
            lines.append(f"- **{indicator} — {statuses[cell['status']]}**: {cell['notes']}")
            for instrument in cell["instruments"]:
                smoke = f"; smoke `{instrument['smoke_case']}`" if instrument.get("smoke_case") else ""
                lines.append(
                    f"  - [{instrument['title']}]({instrument['url']}) — {instrument['official_source']}; "
                    f"live discovery `{instrument['live_discovery']}`; text fetch `{instrument['text_fetch']}`{smoke}."
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_contract(args.input)
    validate_contract(payload)
    rendered = render_markdown(payload)
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"coverage report is stale; run: {Path(__file__).name} --write")
    if not args.write and not args.check:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
