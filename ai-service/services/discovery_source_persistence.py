from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from typing import Any

from auth import _db_connect
from discovery.registry import normalize_registry


class DiscoverySourcePersistenceError(RuntimeError):
    pass


def get_registry() -> dict[str, dict[str, Any]]:
    return deepcopy(_get_registry_cached())


def clear_registry_cache() -> None:
    _get_registry_cached.cache_clear()


@lru_cache(maxsize=1)
def _get_registry_cached() -> dict[str, dict[str, Any]]:
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT country_code, label, languages "
                    "FROM discovery_countries "
                    "ORDER BY country_code"
                )
                country_rows = cur.fetchall()
                if not country_rows:
                    return {}
                cur.execute(
                    "SELECT country_code, name, base_url, domains, source_grade, adapter, "
                    "source_type, languages, pillars, indicators, search_paths, include_patterns, "
                    "exclude_patterns, priority, notes "
                    "FROM discovery_sources "
                    "ORDER BY country_code, position, name"
                )
                source_rows = cur.fetchall()

        registry: dict[str, dict[str, Any]] = {}
        for country_code, label, languages in country_rows:
            registry[str(country_code).upper()] = {
                "label": label,
                "languages": _json_list(languages),
                "sources": [],
            }

        for row in source_rows:
            (
                country_code,
                name,
                base_url,
                domains,
                source_grade,
                adapter,
                source_type,
                languages,
                pillars,
                indicators,
                search_paths,
                include_patterns,
                exclude_patterns,
                priority,
                notes,
            ) = row
            country = registry.get(str(country_code).upper())
            if country is None:
                continue
            country["sources"].append({
                "name": name,
                "base_url": base_url,
                "domains": _json_list(domains),
                "source_grade": source_grade,
                "adapter": adapter,
                "source_type": source_type,
                "languages": _json_list(languages),
                "pillars": _json_list(pillars),
                "indicators": _json_list(indicators),
                "search_paths": _json_list(search_paths),
                "include_patterns": _json_list(include_patterns),
                "exclude_patterns": _json_list(exclude_patterns),
                "priority": priority,
                "notes": notes,
            })
        return normalize_registry(registry)
    except Exception as exc:
        raise DiscoverySourcePersistenceError(str(exc)) from exc


def save_registry(
    registry: dict[str, Any],
    *,
    changed_by: str | None = None,
    change_note: str = "",
) -> dict[str, dict[str, Any]]:
    normalized = normalize_registry(registry)
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM discovery_sources")
                cur.execute("DELETE FROM discovery_countries")
                for country_code, country in normalized.items():
                    cur.execute(
                        "INSERT INTO discovery_countries (country_code, label, languages) "
                        "VALUES (%s, %s, %s::jsonb)",
                        (
                            country_code,
                            country.get("label") or country_code,
                            json.dumps(country.get("languages", [])),
                        ),
                    )
                    for position, source in enumerate(country.get("sources", [])):
                        cur.execute(
                            "INSERT INTO discovery_sources ("
                            "country_code, name, base_url, domains, source_grade, adapter, "
                            "source_type, languages, pillars, indicators, search_paths, "
                            "include_patterns, exclude_patterns, priority, notes, position"
                            ") VALUES ("
                            "%s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, "
                            "%s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s"
                            ")",
                            (
                                country_code,
                                source["name"],
                                source["base_url"],
                                json.dumps(source.get("domains", [])),
                                source.get("source_grade", "primary"),
                                source.get("adapter", "search_engine"),
                                source.get("source_type", "official_website"),
                                json.dumps(source.get("languages", [])),
                                json.dumps(source.get("pillars", [])),
                                json.dumps(source.get("indicators", [])),
                                json.dumps(source.get("search_paths", [])),
                                json.dumps(source.get("include_patterns", [])),
                                json.dumps(source.get("exclude_patterns", [])),
                                source.get("priority", 50),
                                source.get("notes", ""),
                                position,
                            ),
                        )
                cur.execute(
                    "INSERT INTO discovery_source_versions (registry, changed_by, change_note) "
                    "VALUES (%s::jsonb, %s, %s)",
                    (json.dumps(normalized), changed_by, change_note),
                )
                cur.execute(
                    "INSERT INTO discovery_source_audit_events (actor_id, action, details) "
                    "VALUES (%s, %s, %s::jsonb)",
                    (
                        changed_by,
                        "discovery_config_saved",
                        json.dumps({
                            "country_count": len(normalized),
                            "source_count": sum(len(country.get("sources", [])) for country in normalized.values()),
                        }),
                    ),
                )
                conn.commit()
    except Exception as exc:
        raise DiscoverySourcePersistenceError(str(exc)) from exc
    clear_registry_cache()
    return normalized


def _json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)
