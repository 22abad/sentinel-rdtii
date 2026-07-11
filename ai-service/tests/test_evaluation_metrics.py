from __future__ import annotations

from evaluation.metrics import evaluate_predictions, evidence_similarity
from evaluation.models import GoldenCase, GoldenDocument, PredictionRecord


def _case(case_id: str, *, should_map: bool = True) -> GoldenCase:
    return GoldenCase(
        case_id=case_id,
        country_code="SGP",
        document_id="test-act",
        source_legislation="Test Act",
        official_source_url="https://example.gov/test",
        source_status="in_force",
        indicator_id="6.4",
        should_map=should_map,
        article_clause="Section 1",
        verbatim_quote="Personal data may be transferred with comparable protection.",
        expected_scope="horizontal",
        coverage_detail="Personal data",
        expected_raw_score=1.0 if should_map else 0.0,
        expected_cat_score=1.0 if should_map else 0.0,
        legal_rationale="A sufficiently detailed legal rationale.",
        review={
            "status": "approved",
            "reviewer_role": "Substantive Lead",
            "reviewed_at": "2026-07-11",
            "framework_version": "RDTII 2.1",
        },
    )


def _prediction(prediction_id: str, quote: str) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=prediction_id,
        country_code="SGP",
        document_id="test-act",
        indicator_id="6.4",
        article_clause="Section 1",
        verbatim_quote=quote,
        quote_start=11,
        quote_end=11 + len(quote),
        raw_score=1.0,
        scope="horizontal",
    )


def _documents(text: str):
    document = GoldenDocument(
        document_id="test-act",
        country_code="SGP",
        source_legislation="Test Act",
        official_source_url="https://example.gov/test",
        source_status="in_force",
        reference_text_path="fixture.txt",
        reference_text_sha256="0" * 64,
        language_codes=["en"],
    )
    return {"test-act": (document, text)}


def test_metrics_match_evidence_one_to_one_and_verify_offsets():
    quote = "Personal data may be transferred with comparable protection."
    text = f"Section 1. {quote}"
    report = evaluate_predictions(
        [_case("positive-case")],
        [_prediction("prediction-1", quote)],
        _documents(text),
    )

    aggregate = report["aggregate"]
    assert aggregate["mapping_precision"] == 1.0
    assert aggregate["mapping_recall"] == 1.0
    assert aggregate["mapping_f1"] == 1.0
    assert aggregate["citation_exact_match_rate"] == 1.0
    assert aggregate["raw_score_accuracy"] == 1.0
    assert aggregate["scope_accuracy"] == 1.0


def test_unmatched_prediction_is_false_positive_and_hits_negative_case():
    quote = "Personal data may be transferred with comparable protection."
    text = f"Section 1. {quote}"
    prediction = _prediction("prediction-1", quote)
    report = evaluate_predictions(
        [_case("negative-case", should_map=False)],
        [prediction],
        _documents(text),
    )

    aggregate = report["aggregate"]
    assert aggregate["true_positives"] == 0
    assert aggregate["false_positives"] == 1
    assert aggregate["mapping_precision"] == 0.0
    assert report["negative_case_hits"] == [{
        "case_id": "negative-case",
        "prediction_id": "prediction-1",
    }]


def test_no_predictions_with_expected_mapping_has_zero_precision_and_recall():
    report = evaluate_predictions(
        [_case("missed-case")],
        [],
        _documents("Personal data may be transferred with comparable protection."),
    )
    assert report["aggregate"]["mapping_precision"] == 0.0
    assert report["aggregate"]["mapping_recall"] == 0.0
    assert report["aggregate"]["mapping_f1"] == 0.0


def test_single_country_and_indicator_groups_contain_complete_metrics():
    report = evaluate_predictions(
        [_case("single-group-case")],
        [],
        _documents("Personal data may be transferred with comparable protection."),
    )

    assert report["per_country"]["SGP"]["mapping_precision"] == 0.0
    assert report["per_indicator"]["6.4"]["mapping_recall"] == 0.0


def test_evidence_similarity_normalizes_unicode_composition():
    assert evidence_similarity("Caf\u00e9 transfer", "Cafe\u0301 transfer") == 1.0


def test_citation_offset_failure_has_case_level_reason():
    quote = "Personal data may be transferred with comparable protection."
    prediction = _prediction("bad-offset", quote)
    prediction = prediction.model_copy(update={"quote_start": 1, "quote_end": 1 + len(quote)})
    report = evaluate_predictions(
        [_case("citation-case")],
        [prediction],
        _documents(f"Section 1. {quote}"),
    )

    assert report["aggregate"]["citation_exact_match_rate"] == 0.0
    assert report["citation_failures"] == [{
        "case_id": "citation-case",
        "prediction_id": "bad-offset",
        "reason": "quote offsets do not recover the submitted verbatim quote",
    }]
