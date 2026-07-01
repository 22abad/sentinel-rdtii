"""Schemas for the RDTII Discovery Agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceMode = Literal["official_first", "official_only", "broad_web"]
SourceGrade = Literal["primary", "secondary", "unknown"]
SUPPORTED_PILLARS = {6, 7}
SUPPORTED_INDICATORS = {"6.1", "6.2", "6.3", "6.4", "6.5", "7.1", "7.2", "7.3", "7.4", "7.5"}


class DiscoverySearchRequest(BaseModel):
    country_code: str
    pillars: list[int] = Field(default_factory=lambda: [6, 7])
    indicators: list[str] = Field(default_factory=list)
    keywords: str = ""
    limit: int = Field(default=20, ge=1, le=50)
    source_mode: SourceMode = "official_first"
    languages: list[str] = Field(default_factory=list)
    include_secondary_leads: bool = True
    browser_mode: str = "auto"

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("country_code is required")
        return value

    @field_validator("pillars")
    @classmethod
    def validate_pillars(cls, value: list[int]) -> list[int]:
        if not value:
            return [6, 7]
        invalid = [pillar for pillar in value if pillar not in SUPPORTED_PILLARS]
        if invalid:
            raise ValueError(f"unsupported pillar id(s): {invalid}")
        return value

    @field_validator("indicators")
    @classmethod
    def normalize_indicators(cls, value: list[str]) -> list[str]:
        indicators = [indicator.strip() for indicator in value if indicator.strip()]
        invalid = [indicator for indicator in indicators if indicator not in SUPPORTED_INDICATORS]
        if invalid:
            raise ValueError(f"unsupported indicator id(s): {invalid}")
        return indicators

    @field_validator("languages")
    @classmethod
    def normalize_languages(cls, value: list[str]) -> list[str]:
        return [language.strip().lower() for language in value if language.strip()]


class LegalSourceConfig(BaseModel):
    name: str
    base_url: str
    domains: list[str]
    source_grade: SourceGrade = "primary"
    adapter: str = "search_engine"
    country_code: str = ""
    source_type: str = "official_website"
    languages: list[str] = Field(default_factory=list)
    pillars: list[int] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    search_paths: list[str] = Field(default_factory=list)
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    priority: int = 50
    notes: str = ""

    @field_validator("domains")
    @classmethod
    def normalize_domains(cls, value: list[str]) -> list[str]:
        domains = [domain.strip().lower() for domain in value if domain.strip()]
        if not domains:
            raise ValueError("source domains cannot be empty")
        return domains

    @field_validator("pillars")
    @classmethod
    def validate_source_pillars(cls, value: list[int]) -> list[int]:
        invalid = [pillar for pillar in value if pillar not in SUPPORTED_PILLARS]
        if invalid:
            raise ValueError(f"unsupported source pillar id(s): {invalid}")
        return value

    @field_validator("indicators")
    @classmethod
    def normalize_source_indicators(cls, value: list[str]) -> list[str]:
        indicators = [indicator.strip() for indicator in value if indicator.strip()]
        invalid = [indicator for indicator in indicators if indicator not in SUPPORTED_INDICATORS]
        if invalid:
            raise ValueError(f"unsupported source indicator id(s): {invalid}")
        return indicators

    @field_validator("languages")
    @classmethod
    def normalize_source_languages(cls, value: list[str]) -> list[str]:
        return [language.strip().lower() for language in value if language.strip()]


class DiscoveryCountryConfig(BaseModel):
    country_code: str
    label: str
    languages: list[str] = Field(default_factory=list)
    source_count: int = 0
    supported_pillars: list[int] = Field(default_factory=list)


class RawSearchHit(BaseModel):
    title: str = ""
    url: str
    snippet: str = ""
    source_adapter: str = ""
    source_name: str = ""
    query: str = ""
    position: int = 0
    external_id: str = ""
    raw: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class LegalCandidate(BaseModel):
    id: str
    country_code: str
    title: str
    url: str
    source_domain: str = ""
    source_name: str = ""
    source_grade: SourceGrade = "unknown"
    document_type: str = "unknown"
    language: str = ""
    last_update: str = ""
    matched_pillars: list[int] = Field(default_factory=list)
    matched_indicators: list[str] = Field(default_factory=list)
    snippet: str = ""
    confidence: float = 0.0
    rank_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    external_id: str = ""
    source_adapter: str = ""
    query: str = ""


class DiscoverySearchResponse(BaseModel):
    country_code: str
    queries: list[str]
    candidates: list[LegalCandidate]
    diagnostics: dict = Field(default_factory=dict)
