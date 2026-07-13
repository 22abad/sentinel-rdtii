"""Regression checks for the documented Round 1 Quick Start contract."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

from submission.schema import CSV_COLUMNS


REPO_ROOT = Path(__file__).resolve().parents[2]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _env_values() -> dict[str, str]:
    values = dotenv_values(REPO_ROOT / ".env.example")
    return {key: value or "" for key, value in values.items()}


def _documented_judge_columns() -> tuple[str, ...]:
    lines = README.splitlines()
    table_header = "| # | Column | Required | Description |"
    header_index = lines.index(table_header)
    columns: list[str] = []

    for line in lines[header_index + 1 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0].isdigit():
            columns.append(cells[1].strip("`"))
    return tuple(columns)


def test_quick_start_defaults_match_readme() -> None:
    env = _env_values()

    # Pin the intended no-key default. The loop below separately checks that
    # README mirrors these values; both files drifting together must still fail.
    assert env["RDTII_LLM_PROVIDER"] == "ollama"
    assert env["RDTII_LLM_FALLBACK_PROVIDER"] == ""
    assert env["OLLAMA_MODEL"] == "qwen2.5:14b"
    assert env["OLLAMA_BASE_URL"] == "http://localhost:11434/v1"

    for key in ("RDTII_LLM_PROVIDER", "OLLAMA_MODEL", "OLLAMA_BASE_URL"):
        assert f"{key}={env[key]}" in README

    assert "playwright install chromium" in README
    assert "--max-documents 1" in README
    assert "PostgreSQL is not required" in README


def test_judge_cli_registry_choice_is_explicit_and_db_free_by_default() -> None:
    probe = """
import json, runpy
ns = runpy.run_path(%r, run_name='sentinel_contract_probe')
parse_args = ns['parse_args']
base = ['--economy', 'Singapore', '--pillar', '6']
print(json.dumps({
    'default': parse_args(base).registry_backend,
    'explicit': parse_args(base + ['--registry-backend', 'database']).registry_backend,
}))
""" % str(REPO_ROOT / "main.py")
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == '{"default": "file", "explicit": "database"}'


def test_readme_preserves_the_judge_csv_contract() -> None:
    assert len(CSV_COLUMNS) == 13
    assert _documented_judge_columns() == CSV_COLUMNS
    assert "does not replace" in README


def test_readme_uses_bounded_reliability_language() -> None:
    assert "To reduce hallucination risk" in README
    assert "To eliminate LLM hallucination" not in README
