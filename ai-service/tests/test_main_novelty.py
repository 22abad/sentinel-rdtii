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


def _row(law_name: str, *, retrieval_method: str = "official_search",
         source_url: str = "https://example.gov.test/law") -> SubmissionRow:
    return SubmissionRow(
        economy="Singapore",
        law_name=law_name,
        indicator_id="P6-I1",
        article="Section 1",
        discovery_tag="NEW",
        verbatim_snippet="Exact provision text stating a substantive statutory obligation.",
        source_url=source_url,
        retrieval_method=retrieval_method,
    )


@pytest.mark.anyio
async def test_cli_reconciles_provision_and_fixture_tags_before_writing(monkeypatch, tmp_path):
    main_cli = _load_main_module()
    pipeline_rows = [
        # The law is inventoried, but this provision is not in the evidence baseline.
        # Distinct laws sit at distinct URLs (a shared URL would be the one-URL-
        # many-names hallucination that canonicalisation deliberately collapses).
        _row("Cybersecurity Act 2018", source_url="https://example.gov.test/ca2018"),
        _row("Configured Fixture Act 2099", retrieval_method="fixture",
             source_url="https://example.gov.test/fixture"),
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


def test_cli_returns_nonzero_for_empty_results_before_writing(monkeypatch, tmp_path):
    main_cli = _load_main_module()

    async def fake_run_seed_first(*args, **kwargs):
        return [], {
            "provisions_mapped": 0,
            "documents_processed": 0,
            "warnings": [],
        }

    wrote_output = False

    def fake_write_outputs(*args, **kwargs):
        nonlocal wrote_output
        wrote_output = True
        return {}

    monkeypatch.setattr("submission.pipeline.run_seed_first", fake_run_seed_first)
    monkeypatch.setattr(submission, "write_outputs", fake_write_outputs)

    exit_code = main_cli.main(
        [
            "--economy", "Singapore",
            "--pillar", "6",
            "--output-dir", str(tmp_path),
        ]
    )

    assert exit_code == 2
    assert wrote_output is False


@pytest.mark.anyio
async def test_cli_allow_empty_writes_research_output(monkeypatch, tmp_path):
    main_cli = _load_main_module()

    async def fake_run_seed_first(*args, **kwargs):
        return [], {
            "provisions_mapped": 0,
            "documents_processed": 0,
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
        allow_empty=True,
    )

    assert await main_cli._run(args) == 0
    assert captured["rows"] == []


def test_discovery_report_groups_candidates_by_law():
    from submission.novelty import build_discovery_report

    def row(law, ind, quote):
        return SubmissionRow(economy="Malaysia", law_name=law, indicator_id=ind,
                             discovery_tag="NEW", verbatim_snippet=quote,
                             source_url="https://x", article="s.1")
    rows = [
        row("Personal Data Protection Act 2010", "P7-I1", "short"),
        row("PERSONAL DATA PROTECTION ACT 2010", "P7-I3", "a much longer provision text"),
        row("Personal Data Protection Act  2010", "P7-I1", "dup"),
        row("Spam Control Act 2007", "P7-I5", "spam clause"),
    ]
    cands = build_discovery_report("Malaysia", rows)["new_candidates"]
    # The three PDPA variants collapse into one candidate; indicators aggregate.
    assert len(cands) == 2
    pdpa = next(c for c in cands if "Data Protection" in c["law_name"])
    assert sorted(pdpa["indicators"]) == ["P7-I1", "P7-I3"]
    assert pdpa["evidence_rows"] == 3
    assert pdpa["verbatim_snippet"] == "a much longer provision text"  # longest kept
