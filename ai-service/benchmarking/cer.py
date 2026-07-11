"""Character Error Rate calculation with an explicit normalization policy."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable

from rapidfuzz.distance import Levenshtein

from .models import CerPageResult, OcrNormalization


def normalize_ocr_text(value: str, policy: OcrNormalization) -> str:
    text = unicodedata.normalize(policy.unicode_form, value)
    if policy.normalize_line_endings:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    if policy.join_soft_hyphen_linebreaks:
        text = re.sub(r"\u00ad\s*\n\s*", "", text)
        text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    if policy.remove_page_numbers:
        text = re.sub(
            r"(?m)^\s*(?:page\s+)?\d+\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
    if policy.collapse_whitespace:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def calculate_cer(
    reference: str,
    candidate: str,
    policy: OcrNormalization | None = None,
) -> dict:
    policy = policy or OcrNormalization()
    normalized_reference = normalize_ocr_text(reference, policy)
    normalized_candidate = normalize_ocr_text(candidate, policy)
    if not normalized_reference:
        raise ValueError("CER reference text is empty after normalization")

    operations = Levenshtein.editops(normalized_reference, normalized_candidate)
    counts = Counter(operation.tag for operation in operations)
    substitutions = counts["replace"]
    deletions = counts["delete"]
    insertions = counts["insert"]
    distance = substitutions + deletions + insertions
    return {
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "edit_distance": distance,
        "reference_characters": len(normalized_reference),
        "candidate_characters": len(normalized_candidate),
        "cer": distance / len(normalized_reference),
    }


def summarize_cer(results: Iterable[CerPageResult], *, target: float = 0.05) -> dict:
    pages = list(results)
    total_reference = sum(page.reference_characters for page in pages)
    total_distance = sum(page.edit_distance for page in pages)
    return {
        "page_count": len(pages),
        "macro_cer": (
            sum(page.cer for page in pages) / len(pages) if pages else None
        ),
        "micro_cer": total_distance / total_reference if total_reference else None,
        "total_edit_distance": total_distance,
        "total_reference_characters": total_reference,
        "target_cer": target,
        "pages_above_target": sum(page.cer > target for page in pages),
    }
