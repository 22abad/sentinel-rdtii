"""Shared extraction normalization and repair preflight.

This module sits at the LLM/provider boundary. Both the batch endpoint and the
streaming endpoint use it so feature coercion, quote validation, and bounded
repair behavior cannot diverge between runtime paths.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from chunker import Chunk
from validation import validate_mapping
from verification import find_quote_offsets, verify_quote

logger = logging.getLogger(__name__)

NO_MATCH_QUOTES = {"", "n/a", "none", "null", "not found"}


def repair_max_attempts_from_env() -> int:
    raw = os.getenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    try:
        return max(0, min(2, int(raw)))
    except ValueError:
        return 1


def _default_for_type(type_hint: str) -> Any:
    if type_hint == "bool":
        return False
    if type_hint == "int":
        return 0
    if type_hint == "float":
        return 0.0
    return ""


def coerce_feature_value(
    name: str,
    value: Any,
    type_hint: str,
) -> tuple[Any, str | None]:
    """Coerce LLM JSON feature values into scorer-safe Python types."""
    if value is None:
        return _default_for_type(type_hint), None

    if type_hint == "bool":
        if isinstance(value, bool):
            return value, None
        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value), None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "y", "1"}:
                return True, None
            if lowered in {"false", "no", "n", "0", ""}:
                return False, None
        return False, f'Feature "{name}" must be boolean, got {value!r}'

    if type_hint == "int":
        if isinstance(value, bool):
            return 0, f'Feature "{name}" must be integer, got boolean {value!r}'
        if isinstance(value, int):
            return value, None
        if isinstance(value, float) and value.is_integer():
            return int(value), None
        if isinstance(value, str):
            stripped = value.strip()
            try:
                return int(stripped), None
            except ValueError:
                try:
                    as_float = float(stripped)
                except ValueError:
                    pass
                else:
                    if as_float.is_integer():
                        return int(as_float), None
        return 0, f'Feature "{name}" must be integer, got {value!r}'

    if type_hint == "float":
        if isinstance(value, bool):
            return 0.0, f'Feature "{name}" must be float, got boolean {value!r}'
        if isinstance(value, (int, float)):
            return float(value), None
        if isinstance(value, str):
            try:
                return float(value.strip()), None
            except ValueError:
                pass
        return 0.0, f'Feature "{name}" must be float, got {value!r}'

    if type_hint == "str":
        if isinstance(value, str):
            return value, None
        return str(value), None

    return value, None


def normalize_extraction_data(
    data: dict[str, Any],
    feature_spec: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], list[str]]:
    """Return scorer-safe extraction data plus repair-worthy schema errors."""
    normalized = dict(data)
    errors: list[str] = []

    for name, meta in feature_spec.items():
        type_hint = (meta.get("type") or "bool").strip().lower()
        if name not in normalized:
            normalized[name] = _default_for_type(type_hint)
            continue
        coerced, err = coerce_feature_value(name, normalized[name], type_hint)
        normalized[name] = coerced
        if err:
            errors.append(err)

    return normalized, errors


def _quote_from_data(data: dict[str, Any]) -> tuple[str, list[str]]:
    raw = data.get("verbatim_quote")
    if raw is None:
        return "", []
    if not isinstance(raw, str):
        return "", [f"verbatim_quote must be a string, got {type(raw).__name__}"]
    return raw.strip(), []


def _features_for_scoring(
    data: dict[str, Any],
    feature_spec: dict[str, dict[str, str]],
    pdf_metadata: dict | None,
) -> dict[str, Any]:
    features = {k: data[k] for k in feature_spec.keys() if k in data}
    if pdf_metadata:
        # pdf_metadata now carries per-page provenance lists (page_sources,
        # page_char_spans, vision_usage, ...) alongside the scalar OCR hints.
        # Only scalars are valid IndicatorMapping.features values — merging
        # the lists fails schema validation for every mapping.
        features.update({
            k: v for k, v in pdf_metadata.items()
            if isinstance(v, (bool, int, float, str))
        })
    return features


async def _repair_once(
    *,
    provider,
    chunk_text: str,
    indicator_id: str,
    feature_spec: dict[str, dict[str, str]],
    previous_output: dict[str, Any],
    validation_errors: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        repaired = await asyncio.to_thread(
            provider.repair_extraction,
            chunk_text,
            indicator_id,
            feature_spec,
            previous_output,
            validation_errors,
        )
    except Exception as exc:
        return None, f"repair_extraction failed: {exc}"
    if not isinstance(repaired, dict):
        return None, "repair_extraction returned non-object JSON"
    return repaired, None


async def prepare_extraction_with_repair(
    *,
    provider,
    chunk: Chunk,
    indicator_id: str,
    feature_spec: dict[str, dict[str, str]],
    data: dict[str, Any],
    pdf_metadata: dict | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    """Validate and, when needed, repair one raw extraction before scoring."""
    attempts = repair_max_attempts_from_env() if max_attempts is None else max(0, min(2, max_attempts))
    current = dict(data) if isinstance(data, dict) else {}
    last_errors: list[str] = []
    last_repair_error = ""

    for attempt in range(attempts + 1):
        current, schema_errors = normalize_extraction_data(current, feature_spec)
        quote, quote_errors = _quote_from_data(current)

        if not quote_errors and quote.lower() in NO_MATCH_QUOTES:
            return {"status": "skip"}

        errors = [*schema_errors, *quote_errors]
        is_valid = False
        local_start = -1
        local_end = -1

        if quote:
            is_valid = verify_quote(quote, chunk.text)
            if is_valid:
                local_start, local_end = find_quote_offsets(quote, chunk.text)
                if local_start < 0 or local_end <= local_start:
                    errors.append("verbatim_quote matched fuzzily but exact offsets unrecoverable")
                    is_valid = False
            else:
                errors.append("verbatim_quote not found in chunk shown to LLM")
        elif not quote_errors:
            errors.append("verbatim_quote is empty")

        features = _features_for_scoring(current, feature_spec, pdf_metadata)
        # Deterministic guard: a 7.5 "government access" feature must not fire on
        # a consent-gated disclosure (a safeguard, not unfettered access).
        from scoring.pillar_7 import veto_consent_gated_government_access

        veto_reasons = veto_consent_gated_government_access(indicator_id, quote, features)
        validation_reasons: list[str] = list(veto_reasons)
        if not errors and is_valid:
            vr = validate_mapping(
                {},
                quote=quote,
                chunk_text=chunk.text,
                indicator_id=indicator_id,
                features=features,
                include_semantic_check=False,
                track_cross_reference=False,
            )
            if vr.level == "reject":
                errors.extend(f"Validation reject: {reason}" for reason in vr.reasons)
            elif vr.level == "flag":
                validation_reasons = [*validation_reasons, *vr.reasons]

        if not errors:
            return {
                "status": "ready",
                "data": current,
                "quote": quote,
                "local_start": local_start,
                "local_end": local_end,
                "features": features,
                "pre_flag_reasons": validation_reasons,
            }

        last_errors = errors
        if attempt >= attempts:
            reason = "; ".join(errors)
            if last_repair_error:
                reason = f"{reason}; {last_repair_error}"
            return {
                "status": "reject",
                "reason": reason,
                "raw_output": current,
            }

        repaired, repair_error = await _repair_once(
            provider=provider,
            chunk_text=chunk.text,
            indicator_id=indicator_id,
            feature_spec=feature_spec,
            previous_output=current,
            validation_errors=errors,
        )
        if repair_error:
            last_repair_error = repair_error
            return {
                "status": "reject",
                "reason": f"{'; '.join(last_errors)}; {repair_error}",
                "raw_output": current,
            }

        logger.info(
            "Repaired extraction for indicator %s after attempt %s: %s",
            indicator_id,
            attempt + 1,
            "; ".join(errors),
        )
        current = {**current, **repaired}

    return {
        "status": "reject",
        "reason": "; ".join(last_errors) or "extraction repair failed",
        "raw_output": current,
    }
