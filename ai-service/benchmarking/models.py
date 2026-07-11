"""Validated contracts for OCR benchmark cases."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OcrNormalization(StrictModel):
    unicode_form: Literal["NFC", "NFKC"] = "NFC"
    normalize_line_endings: bool = True
    collapse_whitespace: bool = True
    join_soft_hyphen_linebreaks: bool = True
    remove_headers_footers: Literal[False] = False
    remove_page_numbers: bool = False


class OcrReview(StrictModel):
    status: Literal["pending", "approved", "rejected"] = "pending"
    reference_origin: Literal[
        "human_corrected",
        "machine_draft",
        "synthetic_test",
    ] = "machine_draft"
    reviewer_role: str = "OCR Benchmark Reviewer"
    reviewed_at: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def require_human_reference_for_approval(self) -> OcrReview:
        if self.status == "approved" and (
            self.reference_origin != "human_corrected" or not self.reviewed_at
        ):
            raise ValueError(
                "approved OCR cases require human_corrected reference text and reviewed_at"
            )
        return self


class OcrBenchmarkCase(StrictModel):
    case_id: str
    document_id: str
    page_number: int = Field(ge=1)
    source_file_path: str
    source_file_sha256: str
    reference_text_path: str
    reference_text_sha256: str
    language: str = Field(min_length=2)
    extraction_path: Literal["pymupdf", "tesseract", "tesseract_vision"]
    normalization: OcrNormalization = Field(default_factory=OcrNormalization)
    review: OcrReview = Field(default_factory=OcrReview)

    @field_validator("case_id", "document_id")
    @classmethod
    def validate_stable_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError("IDs must be lowercase kebab-case")
        return value

    @field_validator("source_file_sha256", "reference_text_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("SHA-256 values must be 64 lowercase hex characters")
        return value


class CerPageResult(StrictModel):
    case_id: str
    document_id: str
    page_number: int
    language: str
    requested_path: str
    actual_path: str
    fallback_used: bool
    fallback_reason: str | None = None
    substitutions: int
    deletions: int
    insertions: int
    edit_distance: int
    reference_characters: int
    candidate_characters: int
    cer: float
    runtime_seconds: float
    confidence: float | None = None
    vision_usage: dict | None = None
