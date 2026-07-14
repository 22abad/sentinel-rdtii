"""Regression coverage for final novelty reconciliation in the judges' CLI."""

from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest

import submission
from submission.schema import SubmissionRow


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_main_module():
    spec = importlib.util.spec_from_file_location("sentinel_main", REPO_ROOT / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(law_name: str, *, retrieval_method: str = "official_search") -> SubmissionRow:
    return SubmissionRow(
        economy="Singapore",
        law_name=law_name,
        indicator_id="P6-I1",
        discovery_tag="NEW",
        verbatim_snippet="Exact provision text.",
        retrieval_method=retrieval_method,
    )


@pytest.mark.anyio
async def test_cli_reconciles_inventory_and_fixture_tags_before_writing(monkeypatch, tmp_path):
    main_cli = _load_main_module()
    pipeline_rows = [
        _row("Cybersecurity Act 2018"),  # Present in the ESCAP inventory.
        _row("Configured Fixture Act 2099", retrieval_method="fixture"),
    ]

    async def fake_run_seed_first(*args, **kwargs):
        return pipeline_rows, {
            "provisions_mapped": len(pipeline_rows),
            "documents_processed": 1,
            "warnings": [],
        }

    captured = {}

    def fake_write_outputs(rows, **kwargs):
        captured["rows"] = rows
        return {}

    monkeypatch.setattr("submission.pipeline.run_seed_first", fake_run_seed_first)
    monkeypatch.setattr(submission, "write_outputs", fake_write_outputs)

    args = Namespace(
        economy="Singapore",
        pillar=[6],
        pdf=None,
        offline=False,
        no_seed=False,
        provider=None,
        indicators=None,
        limit=20,
        max_documents=None,
        registry_backend="file",
        output_dir=str(tmp_path),
        format="both",
        strict_live=False,
    )

    assert await main_cli._run(args) == 0
    assert [row.discovery_tag for row in captured["rows"]] == ["KNOWN", "KNOWN"]
