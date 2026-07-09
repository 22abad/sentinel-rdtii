"""Schemas for the RDTII Discovery Agent."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

SourceMode = Literal["official_first", "official_only", "broad_web"]
SourceGrade = Literal["primary", "secondary", "unknown"]
RetrievalMode = Literal["live", "fixture", "fallback"]
ValidationStatus = Literal["unverified", "verified", "weak", "failed"]
SUPPORTED_PILLARS = {6, 7}
SUPPORTED_INDICATORS = {"6.1", "6.2", "6.3", "6.4", "6.5", "7.1", "7.2", "7.3", "7.4", "7.5"}


def normalize_hostname(value: str) -> str:
    hostname = value.strip().rstrip(".")
    if not hostname or hostname.startswith("."):
        raise ValueError(f"invalid hostname: {value}")
    try:
        return hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ValueError(f"invalid hostname: {value}") from exc


def indicators_outside_pillars(
    indicators: list[str],
    pillars: list[int],
) -> list[str]:
    allowed_pillars = set(pillars)
    return [
        indicator
        for indicator in indicators
        if int(indicator.split(".", 1)[0]) not in allowed_pillars
    ]


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

    @model_validator(mode="after")
    def validate_indicator_pillars(self) -> DiscoverySearchRequest:
        mismatched = indicators_outside_pillars(self.indicators, self.pillars)
        if mismatched:
            required_pillars = sorted({
                int(indicator.split(".", 1)[0])
                for indicator in mismatched
            })
            raise ValueError(
                f"indicator(s) {mismatched} require requested pillar(s) {required_pillars}"
            )
        return self


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
        domains: list[str] = []
        for raw_domain in value:
            domain = raw_domain.strip().rstrip(".")
            if not domain:
                continue
            if "://" in domain or any(char in domain for char in "/@?#"):
                raise ValueError(f"source domain must be a hostname: {raw_domain}")
            try:
                domain = normalize_hostname(domain)
            except ValueError as exc:
                raise ValueError(f"invalid source domain: {raw_domain}") from exc
            domains.append(domain)
        if not domains:
            raise ValueError("source domains cannot be empty")
        return list(dict.fromkeys(domains))

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip()
        try:
            parsed = urlsplit(value)
            scheme = parsed.scheme.casefold()
            hostname = parsed.hostname
            username = parsed.username
            password = parsed.password
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("source base_url is invalid") from exc
        if scheme not in {"http", "https"} or not hostname:
            raise ValueError("source base_url must be an HTTP(S) URL")
        if username is not None or password is not None:
            raise ValueError("source base_url cannot include credentials")
        return value

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

    @model_validator(mode="after")
    def validate_source_indicator_pillars(self) -> LegalSourceConfig:
        try:
            base_hostname = normalize_hostname(urlsplit(self.base_url).hostname or "")
        except ValueError as exc:
            raise ValueError("source base_url hostname is invalid") from exc
        if base_hostname not in self.domains:
            raise ValueError(
                f"source base_url hostname {base_hostname!r} must be listed in domains"
            )
        if not self.pillars:
            return self
        mismatched = indicators_outside_pillars(self.indicators, self.pillars)
        if mismatched:
            raise ValueError(
                f"source indicator(s) {mismatched} fall outside configured pillars {self.pillars}"
            )
        return self


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
    retrieval_mode: RetrievalMode = "live"


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
    retrieval_mode: RetrievalMode = "live"
    validation_status: ValidationStatus = "unverified"
    validation_metadata: dict = Field(default_factory=dict)


class DiscoverySearchResponse(BaseModel):
    country_code: str
    queries: list[str]
    candidates: list[LegalCandidate]
    diagnostics: dict = Field(default_factory=dict)
