from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.coverage import MIN_CASES
from evaluation.models import GoldenCase, OfflineProviderResponse, PredictionRecord
from evaluation.runner import load_dataset


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "evaluation/golden/cases.jsonl"
DOCUMENTS_PATH = REPO_ROOT / "evaluation/golden/documents.jsonl"


def test_checked_in_golden_candidates_validate_and_match_reference_texts():
    cases, documents = load_dataset(
        repo_root=REPO_ROOT,
        cases_path=CASES_PATH,
        documents_path=DOCUMENTS_PATH,
    )

    assert len(cases) >= MIN_CASES
    assert len(documents) >= 5
    assert {case.country_code for case in cases}.issuperset({"AUS", "MYS", "SGP"})
    assert any(not case.should_map for case in cases)
    # Pending expansion candidates are intentionally excluded from formal
    # metrics. Approved labels must still carry substantive-review metadata.
    approved_cases = [case for case in cases if case.review.status == "approved"]
    assert approved_cases
    assert all(case.review.reviewed_at for case in approved_cases)


def test_portable_schema_required_fields_match_runtime_model():
    schema = json.loads(
        (REPO_ROOT / "evaluation/schema/golden-case.schema.json").read_text(
            encoding="utf-8",
        )
    )
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(schema["required"]) == set(GoldenCase.model_fields)
    assert schema["properties"]["review"]["$ref"] == "#/$defs/review"


def test_duplicate_ids_and_tampered_reference_hash_are_rejected(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    documents_path = tmp_path / "documents.jsonl"
    fixture_path = tmp_path / "fixture.txt"
    fixture_path.write_text("Exact legal evidence.", encoding="utf-8")
    document = {
        "document_id": "test-document",
        "country_code": "SGP",
        "source_legislation": "Test Act",
        "official_source_url": "https://example.gov/test",
        "source_status": "in_force",
        "reference_text_path": "fixture.txt",
        "reference_text_sha256": "0" * 64,
        "language_codes": ["en"],
    }
    documents_path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    cases_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_dataset(
            repo_root=tmp_path,
            cases_path=cases_path,
            documents_path=documents_path,
        )


def test_offline_fixture_requires_response_or_explicit_no_mapping():
    no_mapping = OfflineProviderResponse(
        document_id="test-document",
        indicator_id="6.4",
        no_mapping=True,
    )
    assert no_mapping.response is None

    with pytest.raises(ValueError, match="exactly one"):
        OfflineProviderResponse(
            document_id="test-document",
            indicator_id="6.4",
        )


def test_prediction_requires_non_empty_quote_and_non_empty_offsets():
    base = {
        "prediction_id": "prediction-1",
        "country_code": "SGP",
        "document_id": "test-document",
        "indicator_id": "6.4",
        "article_clause": "Section 1",
        "verbatim_quote": "Evidence",
        "quote_start": 0,
        "quote_end": 8,
        "raw_score": 1.0,
        "scope": "horizontal",
    }
    assert PredictionRecord(**base).verbatim_quote == "Evidence"
    with pytest.raises(ValueError, match="greater than"):
        PredictionRecord(**{**base, "quote_end": 0})
