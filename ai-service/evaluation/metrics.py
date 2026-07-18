"""Deterministic matching and substantive evaluation metrics."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Iterable

from rapidfuzz import fuzz

from .models import GoldenCase, GoldenDocument, PredictionRecord


def normalize_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def evidence_similarity(expected: str, predicted: str) -> float:
    left = normalize_evidence(expected)
    right = normalize_evidence(predicted)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return min(len(left), len(right)) / max(len(left), len(right))
    return fuzz.ratio(left, right) / 100.0


def clauses_compatible(expected: str, predicted: str) -> bool:
    left = normalize_evidence(expected)
    right = normalize_evidence(predicted)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def evaluate_predictions(
    cases: Iterable[GoldenCase],
    predictions: Iterable[PredictionRecord],
    documents: dict[str, tuple[GoldenDocument, str]],
    *,
    evidence_threshold: float = 0.8,
) -> dict:
    case_list = list(cases)
    prediction_list = list(predictions)
    result = _evaluate_core(
        case_list,
        prediction_list,
        documents,
        evidence_threshold=evidence_threshold,
    )
    result["per_country"] = _group_metrics(
        case_list,
        prediction_list,
        documents,
        "country",
        evidence_threshold=evidence_threshold,
    )
    result["per_indicator"] = _group_metrics(
        case_list,
        prediction_list,
        documents,
        "indicator",
        evidence_threshold=evidence_threshold,
    )
    return result


def prediction_matches_case(
    case: GoldenCase,
    prediction: PredictionRecord,
    *,
    evidence_threshold: float = 0.8,
) -> bool:
    return (
        case.country_code == prediction.country_code
        and case.document_id == prediction.document_id
        and case.indicator_id == prediction.indicator_id
        and evidence_similarity(case.verbatim_quote, prediction.verbatim_quote)
        >= evidence_threshold
    )


def _evaluate_core(
    case_list: list[GoldenCase],
    prediction_list: list[PredictionRecord],
    documents: dict[str, tuple[GoldenDocument, str]],
    *,
    evidence_threshold: float,
) -> dict:
    positives = [case for case in case_list if case.should_map]
    negatives = [case for case in case_list if not case.should_map]

    candidates: list[tuple[float, int, int]] = []
    for case_index, case in enumerate(positives):
        for prediction_index, prediction in enumerate(prediction_list):
            if not prediction_matches_case(
                case,
                prediction,
                evidence_threshold=evidence_threshold,
            ):
                continue
            similarity = evidence_similarity(case.verbatim_quote, prediction.verbatim_quote)
            candidates.append((similarity, case_index, prediction_index))

    matched_cases: set[int] = set()
    matched_predictions: set[int] = set()
    matches: list[tuple[GoldenCase, PredictionRecord, float]] = []
    for similarity, case_index, prediction_index in sorted(candidates, reverse=True):
        if case_index in matched_cases or prediction_index in matched_predictions:
            continue
        matched_cases.add(case_index)
        matched_predictions.add(prediction_index)
        matches.append(
            (positives[case_index], prediction_list[prediction_index], similarity)
        )

    false_negatives = [
        case for index, case in enumerate(positives) if index not in matched_cases
    ]
    false_positives = [
        prediction
        for index, prediction in enumerate(prediction_list)
        if index not in matched_predictions
    ]

    tp = len(matches)
    fp = len(false_positives)
    fn = len(false_negatives)
    precision = _safe_precision(tp, fp, len(positives))
    recall = _safe_recall(tp, fn)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    citation_failures = [
        _citation_failure(case, prediction, documents)
        for case, prediction, _similarity in matches
        if not _citation_is_exact(prediction, documents)
    ]
    exact_citations = tp - len(citation_failures)
    article_correct = sum(
        clauses_compatible(case.article_clause, prediction.article_clause)
        for case, prediction, _similarity in matches
    )
    score_correct = sum(
        case.expected_raw_score == prediction.raw_score
        for case, prediction, _similarity in matches
    )
    scope_correct = sum(
        case.expected_scope == prediction.scope
        for case, prediction, _similarity in matches
    )

    category_expected = _expected_category_scores(positives)
    category_predicted = _predicted_category_scores(prediction_list)
    category_correct = sum(
        category_predicted.get(key, 0.0) == score
        for key, score in category_expected.items()
    )

    negative_hits = []
    for case in negatives:
        for prediction in prediction_list:
            if prediction_matches_case(
                case,
                prediction,
                evidence_threshold=evidence_threshold,
            ):
                negative_hits.append({
                    "case_id": case.case_id,
                    "prediction_id": prediction.prediction_id,
                })

    aggregate = {
        "expected_positive_mappings": len(positives),
        "explicit_negative_cases": len(negatives),
        "predicted_mappings": len(prediction_list),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "mapping_precision": precision,
        "accepted_precision": precision,
        "mapping_recall": recall,
        "mapping_f1": f1,
        "false_positive_rate": fp / len(prediction_list) if prediction_list else 0.0,
        "abstention_rate": fn / len(positives) if positives else 0.0,
        "acceptance_rate": (
            len(prediction_list) / (len(prediction_list) + fn)
            if prediction_list or fn else 1.0
        ),
        "citation_exact_match_rate": _rate(exact_citations, tp),
        "article_citation_accuracy": _rate(article_correct, tp),
        "raw_score_accuracy": _rate(score_correct, tp),
        "category_score_accuracy": _rate(category_correct, len(category_expected)),
        "scope_accuracy": _rate(scope_correct, tp),
        "human_review_rate": _rate(
            sum(prediction.requires_human_review for prediction in prediction_list),
            len(prediction_list),
        ),
        "approval_rate": None,
        "correction_rate": None,
    }

    return {
        "aggregate": aggregate,
        "matches": [
            {
                "case_id": case.case_id,
                "prediction_id": prediction.prediction_id,
                "evidence_similarity": round(similarity, 6),
            }
            for case, prediction, similarity in matches
        ],
        "false_positives": [prediction.model_dump() for prediction in false_positives],
        "false_negatives": [case.model_dump() for case in false_negatives],
        "negative_case_hits": negative_hits,
        "citation_failures": citation_failures,
        "confusion_matrix": _indicator_confusion_matrix(
            positives, false_positives, evidence_threshold=evidence_threshold
        ),
    }


def _indicator_confusion_matrix(
    positive_cases: list[GoldenCase],
    false_positives: list[PredictionRecord],
    *,
    evidence_threshold: float,
) -> dict[str, dict[str, int]]:
    """Count wrong-indicator predictions on otherwise matching evidence."""
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for prediction in false_positives:
        candidates = [
            case for case in positive_cases
            if case.country_code == prediction.country_code
            and case.document_id == prediction.document_id
            and evidence_similarity(case.verbatim_quote, prediction.verbatim_quote)
            >= evidence_threshold
            and case.indicator_id != prediction.indicator_id
        ]
        if not candidates:
            continue
        expected = max(
            candidates,
            key=lambda case: evidence_similarity(case.verbatim_quote, prediction.verbatim_quote),
        ).indicator_id
        matrix[expected][prediction.indicator_id] += 1
    return {
        expected: dict(sorted(predicted.items()))
        for expected, predicted in sorted(matrix.items())
    }


def _group_metrics(
    cases: list[GoldenCase],
    predictions: list[PredictionRecord],
    documents: dict[str, tuple[GoldenDocument, str]],
    dimension: str,
    *,
    evidence_threshold: float,
) -> dict[str, dict]:
    values = sorted({
        case.country_code if dimension == "country" else case.indicator_id
        for case in cases
    })
    grouped: dict[str, dict] = {}
    for value in values:
        subset_cases = [
            case for case in cases
            if (case.country_code if dimension == "country" else case.indicator_id) == value
        ]
        subset_predictions = [
            prediction for prediction in predictions
            if (
                prediction.country_code
                if dimension == "country"
                else prediction.indicator_id
            ) == value
        ]
        grouped[value] = _evaluate_core(
            subset_cases,
            subset_predictions,
            documents,
            evidence_threshold=evidence_threshold,
        )["aggregate"]
    return grouped


def _citation_is_exact(
    prediction: PredictionRecord,
    documents: dict[str, tuple[GoldenDocument, str]],
) -> bool:
    document_entry = documents.get(prediction.document_id)
    if document_entry is None:
        return False
    text = document_entry[1]
    return (
        prediction.quote_end > prediction.quote_start
        and text[prediction.quote_start:prediction.quote_end] == prediction.verbatim_quote
    )


def _citation_failure(
    case: GoldenCase,
    prediction: PredictionRecord,
    documents: dict[str, tuple[GoldenDocument, str]],
) -> dict[str, str]:
    document_entry = documents.get(prediction.document_id)
    if document_entry is None:
        reason = "document is absent from the evaluated dataset"
    elif prediction.quote_end <= prediction.quote_start:
        reason = "quote offsets are empty or reversed"
    else:
        recovered = document_entry[1][prediction.quote_start:prediction.quote_end]
        reason = "quote offsets do not recover the submitted verbatim quote"
        if not recovered:
            reason = "quote offsets are outside the available document text"
    return {
        "case_id": case.case_id,
        "prediction_id": prediction.prediction_id,
        "reason": reason,
    }


def _expected_category_scores(cases: list[GoldenCase]) -> dict[tuple[str, str], float]:
    grouped: dict[tuple[str, str], set[float]] = defaultdict(set)
    for case in cases:
        grouped[(case.country_code, case.indicator_id)].add(case.expected_cat_score)
    inconsistent = {key: values for key, values in grouped.items() if len(values) > 1}
    if inconsistent:
        raise ValueError(f"inconsistent expected category scores: {inconsistent}")
    return {key: next(iter(values)) for key, values in grouped.items()}


def _predicted_category_scores(
    predictions: list[PredictionRecord],
) -> dict[tuple[str, str], float]:
    grouped: dict[tuple[str, str], float] = defaultdict(float)
    for prediction in predictions:
        key = (prediction.country_code, prediction.indicator_id)
        grouped[key] = min(1.0, grouped[key] + prediction.raw_score)
    return dict(grouped)


def _safe_precision(tp: int, fp: int, expected_positives: int) -> float:
    if tp + fp:
        return tp / (tp + fp)
    return 0.0 if expected_positives else 1.0


def _safe_recall(tp: int, fn: int) -> float:
    return tp / (tp + fn) if tp + fn else 1.0


def _rate(correct: int, total: int) -> float | None:
    return correct / total if total else None
