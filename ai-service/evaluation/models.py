"""Validated contracts for golden cases, documents, and predictions."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas import IndicatorId, ScopeKind, Score


_STABLE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewRecord(StrictModel):
    status: Literal["pending", "approved", "rejected"] = "pending"
    reviewer_role: str = "Substantive Lead"
    reviewed_at: str | None = None
    framework_version: Literal["RDTII 2.1"] = "RDTII 2.1"
    notes: str = ""

    @model_validator(mode="after")
    def require_approval_metadata(self) -> ReviewRecord:
        if self.status == "approved" and not self.reviewed_at:
            raise ValueError("approved labels require reviewed_at")
        return self


class GoldenDocument(StrictModel):
    document_id: str
    country_code: str
    source_legislation: str
    official_source_url: str
    source_status: Literal["in_force", "repealed", "superseded", "draft", "unknown"]
    reference_text_path: str
    reference_text_sha256: str
    source_file_sha256: str | None = None
    language_codes: list[str] = Field(min_length=1)
    retrieval_instructions: str = ""
    review: ReviewRecord = Field(default_factory=ReviewRecord)

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("document_id must be a stable lowercase kebab-case id")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("country_code must be ISO 3166-1 alpha-3")
        return normalized

    @field_validator("official_source_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("official_source_url must be HTTP(S)")
        return value

    @field_validator("reference_text_sha256", "source_file_sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("SHA-256 values must be 64 lowercase hex characters")
        return value


class GoldenCase(StrictModel):
    case_id: str
    country_code: str
    document_id: str
    source_legislation: str
    official_source_url: str
    source_status: Literal["in_force", "repealed", "superseded", "draft", "unknown"]
    indicator_id: IndicatorId
    should_map: bool
    article_clause: str
    verbatim_quote: str = Field(min_length=1)
    expected_scope: ScopeKind
    coverage_detail: str
    expected_raw_score: Score
    expected_cat_score: Score
    legal_rationale: str = Field(min_length=10)
    review: ReviewRecord = Field(default_factory=ReviewRecord)

    @field_validator("case_id", "document_id")
    @classmethod
    def validate_stable_id(cls, value: str) -> str:
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("case and document ids must be lowercase kebab-case")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("country_code must be ISO 3166-1 alpha-3")
        return normalized

    @field_validator("official_source_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("official_source_url must be HTTP(S)")
        return value

    @model_validator(mode="after")
    def validate_negative_score(self) -> GoldenCase:
        if not self.should_map and (
            self.expected_raw_score != 0.0 or self.expected_cat_score != 0.0
        ):
            raise ValueError("negative cases must have zero expected scores")
        return self


class OfflineProviderResponse(StrictModel):
    document_id: str
    # The production classifier can still emit legacy IDs outside the current
    # GoldenCase enum. Fixtures must describe those outputs explicitly so they
    # are not silently dropped by offline evaluation.
    indicator_id: str
    response: dict[str, Any] | None = None
    no_mapping: bool = False

    @field_validator("indicator_id")
    @classmethod
    def validate_classifier_indicator(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"\d+\.\d+", normalized):
            raise ValueError("offline indicator_id must use numeric dotted form")
        return normalized

    @model_validator(mode="after")
    def require_one_fixture_outcome(self) -> OfflineProviderResponse:
        if self.no_mapping == (self.response is not None):
            raise ValueError("set exactly one of response or no_mapping=true")
        return self


class PredictionRecord(StrictModel):
    prediction_id: str
    country_code: str
    document_id: str
    indicator_id: IndicatorId
    article_clause: str = ""
    verbatim_quote: str = Field(min_length=1)
    quote_start: int = Field(ge=0)
    quote_end: int = Field(ge=0)
    raw_score: Score
    scope: ScopeKind
    requires_human_review: bool = False
    source_legislation: str = ""
    source_url: str = ""
    extraction_provider: str = "unknown"

    @model_validator(mode="after")
    def validate_offsets(self) -> PredictionRecord:
        if self.quote_end <= self.quote_start:
            raise ValueError("quote_end must be greater than quote_start")
        return self
