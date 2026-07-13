"""Regression checks for the documented Round 1 Quick Start contract."""

from __future__ import annotations

from pathlib import Path

from submission.schema import CSV_COLUMNS


REPO_ROOT = Path(__file__).resolve().parents[2]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_quick_start_defaults_match_readme() -> None:
    env = _env_values()

    assert env["RDTII_LLM_PROVIDER"] == "ollama"
    assert env["OLLAMA_MODEL"] == "qwen2.5:14b"
    assert env["OLLAMA_BASE_URL"] == "http://localhost:11434/v1"

    for key in ("RDTII_LLM_PROVIDER", "OLLAMA_MODEL", "OLLAMA_BASE_URL"):
        assert f"{key}={env[key]}" in README

    assert "playwright install chromium" in README
    assert "--max-documents 1" in README


def test_readme_preserves_the_judge_csv_contract() -> None:
    assert len(CSV_COLUMNS) == 13
    judge_section = README.split(
        "### Round 1 prototype output — 13 fields", 1
    )[1].split("### Frontend RDTII data-table export — 10 fields", 1)[0]

    positions = [judge_section.index(f"`{column}`") for column in CSV_COLUMNS]
    assert positions == sorted(positions)
    assert "does not replace" in README


def test_readme_uses_bounded_reliability_language() -> None:
    assert "To reduce hallucination risk" in README
    assert "To eliminate LLM hallucination" not in README
