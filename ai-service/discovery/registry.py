"""Config-backed official legal-source registry for Discovery."""

from __future__ import annotations

import logging

import os
import tempfile
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from .schemas import DiscoveryCountryConfig, LegalSourceConfig

DEFAULT_REGISTRY_PATH = Path(__file__).with_name("sources.yaml")
DiscoveryRegistryBackend = Literal["file", "database"]


def _registry_path() -> Path:
    override = os.getenv("DISCOVERY_SOURCES_FILE", "").strip()
    return Path(override) if override else DEFAULT_REGISTRY_PATH


def get_registry_backend() -> DiscoveryRegistryBackend:
    backend = os.getenv("DISCOVERY_REGISTRY_BACKEND", "database").strip().lower()
    if backend in {"file", "database"}:
        return backend
    raise ValueError(f"Unsupported DISCOVERY_REGISTRY_BACKEND: {backend}")


@lru_cache(maxsize=4)
def _load_registry(path: str) -> dict[str, dict[str, Any]]:
    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Discovery registry must be a mapping: {registry_path}")
    return {str(code).strip().upper(): dict(config or {}) for code, config in raw.items()}


def get_registry() -> dict[str, dict[str, Any]]:
    backend = get_registry_backend()
    if backend == "file":
        return deepcopy(_load_registry(str(_registry_path())))

    if backend == "database":
        try:
            from services import discovery_source_persistence

            return discovery_source_persistence.get_registry()
        except Exception:
            if os.getenv("DISCOVERY_ALLOW_YAML_FALLBACK", "").strip().lower() in {"1", "true", "yes"}:
                return deepcopy(_load_registry(str(_registry_path())))
            raise

    raise AssertionError(f"Unhandled DISCOVERY_REGISTRY_BACKEND: {backend}")


def clear_registry_cache() -> None:
    _load_registry.cache_clear()


def save_file_registry(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # Saves are strict: silently dropping a user's invalid source is worse
    # than rejecting the submission.
    normalized = normalize_registry(registry, strict=True)
    registry_path = _registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=registry_path.parent,
        prefix=f".{registry_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        yaml.safe_dump(
            normalized,
            handle,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        temp_path = Path(handle.name)
    os.replace(temp_path, registry_path)
    clear_registry_cache()
    return get_registry()


logger = logging.getLogger(__name__)


def normalize_registry(
    registry: dict[str, Any], *, strict: bool = False
) -> dict[str, dict[str, Any]]:
    """Validate and normalise the registry.

    By default one invalid source is SKIPPED with a logged warning instead of
    blanking the whole registry (the Source Manager went "No countries
    configured" over a single stale row). ``strict=True`` restores
    fail-fast for validation tooling and tests.
    """
    if not isinstance(registry, dict):
        raise ValueError("Discovery registry must be an object keyed by country code.")

    normalized: dict[str, dict[str, Any]] = {}
    for raw_country_code, raw_country_config in registry.items():
        country_code = str(raw_country_code).strip().upper()
        if not country_code:
            raise ValueError("Country code cannot be empty.")
        if len(country_code) > 3:
            raise ValueError(f"Country code must be 3 characters or fewer: {country_code}")
        if not isinstance(raw_country_config, dict):
            raise ValueError(f"{country_code} config must be an object.")

        country_config = dict(raw_country_config)
        raw_sources = country_config.get("sources", [])
        if not isinstance(raw_sources, list):
            raise ValueError(f"{country_code}.sources must be a list.")

        sources: list[dict[str, Any]] = []
        for index, raw_source in enumerate(raw_sources):
            if not isinstance(raw_source, dict):
                raise ValueError(f"{country_code}.sources[{index}] must be an object.")
            source_config = dict(raw_source)
            source_config.setdefault("country_code", country_code)
            try:
                source = LegalSourceConfig(**source_config)
                if not source.domains:
                    raise ValueError(f"{country_code}.sources[{index}].domains cannot be empty.")
            except (ValueError, TypeError) as exc:
                if strict:
                    raise
                logger.warning(
                    "Skipping invalid discovery source %s.sources[%d] (%s): %s",
                    country_code, index, source_config.get("name", "?"), exc,
                )
                continue

            stored_source = source.model_dump()
            stored_source.pop("country_code", None)
            sources.append(_drop_empty_values(stored_source))

        country_config["label"] = str(country_config.get("label") or country_code)
        country_config["languages"] = _normalize_string_list(country_config.get("languages", []))
        country_config["sources"] = sources
        normalized[country_code] = country_config

    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    raw_items = [value] if isinstance(value, str) else list(value or [])
    return [
        str(item).strip().lower()
        for item in raw_items
        if str(item).strip()
    ]


def _drop_empty_values(source: dict[str, Any]) -> dict[str, Any]:
    optional_empty_values = {
        "notes": "",
        "languages": [],
        "pillars": [],
        "indicators": [],
        "search_paths": [],
        "include_patterns": [],
        "exclude_patterns": [],
        "title_overrides": {},
    }
    return {
        key: value
        for key, value in source.items()
        if optional_empty_values.get(key, object()) != value
    }


def get_country_registry(country_code: str) -> dict[str, Any]:
    country_code = country_code.strip().upper()
    registry = get_registry()
    if country_code not in registry:
        raise KeyError(country_code)
    return registry[country_code]


def get_sources(country_code: str) -> list[LegalSourceConfig]:
    normalized = country_code.strip().upper()
    registry = get_country_registry(normalized)
    sources = []
    for source in registry.get("sources", []):
        source_config = dict(source)
        source_config.setdefault("country_code", normalized)
        sources.append(LegalSourceConfig(**source_config))
    return sources


def get_languages(country_code: str) -> list[str]:
    return list(get_country_registry(country_code).get("languages", []))


def list_countries() -> list[DiscoveryCountryConfig]:
    countries: list[DiscoveryCountryConfig] = []
    for country_code, registry in sorted(get_registry().items()):
        sources = [
            LegalSourceConfig(**{**dict(source), "country_code": country_code})
            for source in registry.get("sources", [])
        ]
        supported_pillars = sorted({
            pillar
            for source in sources
            for pillar in source.pillars
        })
        countries.append(
            DiscoveryCountryConfig(
                country_code=country_code,
                label=str(registry.get("label") or country_code),
                languages=list(registry.get("languages", [])),
                source_count=len(sources),
                supported_pillars=supported_pillars,
            )
        )
    return countries
