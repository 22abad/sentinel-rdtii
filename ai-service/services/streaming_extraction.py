from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncGenerator

from providers.base import ExtractionError
from schemas import RejectedExtraction, RunUsageSummary
from telemetry import UsageCollector

logger = logging.getLogger(__name__)


def _event_name(sse_event: str) -> str:
    first_line = sse_event.split("\n", 1)[0]
    if first_line.startswith("event: "):
        return first_line.removeprefix("event: ").strip()
    return ""


async def stream_extraction(text: str, llm_provider, pdf_metadata: dict | None = None) -> AsyncGenerator[str, None]:
    """Stream extraction events with request-scoped telemetry."""
    collector = UsageCollector(run_id=f"extract-{uuid.uuid4().hex}")
    try:
        if hasattr(llm_provider, "usage_collection"):
            with llm_provider.usage_collection(collector):
                async for event in _stream_extraction_impl(
                    text, llm_provider, pdf_metadata, collector,
                ):
                    yield event
        else:
            async for event in _stream_extraction_impl(
                text, llm_provider, pdf_metadata, collector,
            ):
                yield event
    finally:
        collector.finish()


async def _stream_extraction_impl(
    text: str,
    llm_provider,
    pdf_metadata: dict | None,
    collector: UsageCollector,
) -> AsyncGenerator[str, None]:
    from validation import reset_quote_registry

    import main as main_module
    from chunker import reflow_legal_text, regex_legal_chunker
    from features import get_feature_spec
    from agents.eligibility import EligibilityVerifier

    reset_quote_registry()
    eligibility_verifier = EligibilityVerifier(llm_provider)

    # Mend PDF/OCR line damage before anything reads the text — so source_text,
    # chunk offsets and quote-locating all operate on the same clean text.
    text = reflow_legal_text(text)

    def _sse(event: str, payload: object) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

    def _usage_snapshot() -> dict:
        return RunUsageSummary(
            run_id=collector.run_id,
            **collector.summary(),
        ).model_dump()

    yield _sse("started", {"source_text": text})

    chunks = regex_legal_chunker(text)
    chunk_groups: list[tuple] = []
    for chunk in chunks:
        indicators: list[tuple[str, dict]] = []
        for indicator_id in main_module.classify_indicator(chunk.text):
            spec = get_feature_spec(indicator_id)
            if spec:
                indicators.append((indicator_id, spec))
        if indicators:
            chunk_groups.append((chunk, indicators))

    mapping_count = 0
    rejected_count = 0
    total_groups = len(chunk_groups)
    chunk_timeout = float(os.getenv("RDTII_EXTRACT_CHUNK_TIMEOUT_SECONDS", "90"))

    if not chunk_groups:
        yield _sse("warning", {"message": "No indicator-relevant chunks were found in this text."})

    for index, (chunk, indicators) in enumerate(chunk_groups, start=1):
        yield _sse(
            "progress",
            {
                "current": index,
                "total": total_groups,
                "phase": "extracting",
                "indicators": [indicator_id for indicator_id, _spec in indicators],
            },
        )
        try:
            batch = await asyncio.wait_for(
                asyncio.to_thread(llm_provider.extract_batch, chunk.text, indicators),
                timeout=chunk_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("stream batch timed out after %.1fs", chunk_timeout)
            yield _sse(
                "rejected",
                RejectedExtraction(
                    reason=f"LLM extraction timed out after {chunk_timeout:.0f}s",
                    chunk_preview=chunk.text[:200],
                ).model_dump(),
            )
            rejected_count += 1
            yield _sse("usage", _usage_snapshot())
            continue
        except ExtractionError as exc:
            logger.warning("stream batch failed, per-indicator fallback: %s", exc)
            for ind_id, spec in indicators:
                try:
                    data = await asyncio.wait_for(
                        asyncio.to_thread(llm_provider.extract_features, chunk.text, ind_id, spec),
                        timeout=chunk_timeout,
                    )
                except asyncio.TimeoutError:
                    yield _sse(
                        "rejected",
                        RejectedExtraction(
                            reason=f"LLM extraction timed out after {chunk_timeout:.0f}s",
                            chunk_preview=chunk.text[:200],
                        ).model_dump(),
                    )
                    rejected_count += 1
                    continue
                except ExtractionError:
                    yield _sse(
                        "rejected",
                        RejectedExtraction(
                            reason="LLM extraction failed",
                            chunk_preview=chunk.text[:200],
                        ).model_dump(),
                    )
                    rejected_count += 1
                    continue
                async for event in process_single(chunk, ind_id, spec, data, text, llm_provider, pdf_metadata, eligibility_verifier):
                    if _event_name(event) == "mapping":
                        mapping_count += 1
                    elif _event_name(event) == "rejected":
                        rejected_count += 1
                    yield event
        else:
            for ind_id, spec in indicators:
                data = batch.get(ind_id) if isinstance(batch, dict) else None
                if data is None:
                    yield _sse(
                        "rejected",
                        RejectedExtraction(
                            reason="missing indicator in batch response",
                            chunk_preview=chunk.text[:200],
                        ).model_dump(),
                    )
                    rejected_count += 1
                    continue
                async for event in process_single(chunk, ind_id, spec, data, text, llm_provider, pdf_metadata, eligibility_verifier):
                    if _event_name(event) == "mapping":
                        mapping_count += 1
                    elif _event_name(event) == "rejected":
                        rejected_count += 1
                    yield event

        yield _sse("usage", _usage_snapshot())

    collector.finish()
    usage = RunUsageSummary(run_id=collector.run_id, **collector.summary())
    yield _sse(
        "done",
        {
            "mappings_count": mapping_count,
            "rejected_count": rejected_count,
            "provider": llm_provider.name,
            "usage": usage.model_dump(),
        },
    )


async def process_single(chunk, ind_id, spec, data, full_text, llm_provider, pdf_metadata=None, eligibility_verifier=None):
    from coverage_classifier import classify_coverage
    from extraction_repair import prepare_extraction_with_repair
    from schemas import IndicatorMapping, RejectedExtraction
    from scoring import score_indicator
    from source_validator import grade_source
    from staleness_checker import check_staleness
    from timeframe_extractor import build_timeframe_column, extract_timeframe
    from validation import validate_mapping

    def _sse(event, payload):
        return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

    def _text_field(name: str) -> str:
        return data.get(name) or ""

    prepared = await prepare_extraction_with_repair(
        provider=llm_provider,
        chunk=chunk,
        indicator_id=ind_id,
        feature_spec=spec,
        data=data,
        pdf_metadata=pdf_metadata,
    )
    if prepared["status"] == "skip":
        return
    if prepared["status"] == "reject":
        yield _sse(
            "rejected",
            RejectedExtraction(
                reason=prepared["reason"],
                chunk_preview=chunk.text[:200],
                raw_output=prepared.get("raw_output", data),
            ).model_dump(),
        )
        return

    data = prepared["data"]
    quote = prepared["quote"]
    local_start = prepared["local_start"]
    local_end = prepared["local_end"]
    features = prepared["features"]
    pre_flag_reasons = prepared.get("pre_flag_reasons", [])

    from agents.eligibility import EligibilityVerifier, rejected_from_eligibility

    verifier = eligibility_verifier or EligibilityVerifier(llm_provider)
    eligibility = await verifier.verify(quote, ind_id, features)
    if not eligibility.supported:
        yield _sse(
            "rejected",
            rejected_from_eligibility(
                eligibility, chunk.text[:200], raw_output=data
            ).model_dump(),
        )
        return

    # DISPLAY ONLY: full sentence(s) around the quote, so a reviewer sees a
    # clipped half-sentence in context. Not used for scoring (see chunker note).
    from chunker import sentence_span

    _cs, _ce = sentence_span(chunk.text, local_start, local_end)
    quote_context = chunk.text[_cs:_ce]

    try:
        score, justification = score_indicator(ind_id, features)
        score_not_implemented = False
    except NotImplementedError:
        score, justification = 0.5, "Scoring rules not implemented."
        score_not_implemented = True
        pre_flag_reasons.append(f"Deterministic scoring for indicator {ind_id} is not implemented.")

    raw_scope = (data.get("scope") or "").strip().lower()
    scope_value = raw_scope if raw_scope in {"horizontal", "sectoral"} else "unknown"
    source_legislation_val = _text_field("source_legislation")
    source_url_val = _text_field("source_url")
    last_update_val = _text_field("last_update")

    src_val = grade_source(
        url=source_url_val,
        title=source_legislation_val,
        text_snippet=chunk.text[:300],
    )
    features["_source_grade"] = src_val.get("grade", "unknown")
    features["_source_grade_confidence"] = str(round(src_val.get("confidence", 0.0), 2))

    if scope_value == "unknown":
        cc = classify_coverage(
            provision_text=_text_field("verbatim_quote"),
            source_legislation=source_legislation_val,
            indicator_id=ind_id,
        )
        scope_value = cc["scope"]
        features["_coverage_reasons"] = "; ".join(cc.get("reasons", []))

    timeframe = extract_timeframe(
        text=chunk.text,
        source_legislation=source_legislation_val,
        source_url=source_url_val,
    )
    tf_column = build_timeframe_column(
        status=timeframe["status"],
        in_force_date=timeframe.get("in_force_date") or last_update_val,
        last_amended_date=timeframe.get("last_amended_date"),
        repealed_date=timeframe.get("repealed_date"),
    )
    features["_timeframe_status"] = timeframe["status"]
    features["_timeframe_column"] = tf_column

    ts_verification = {}

    stale = check_staleness(
        last_update=last_update_val,
        timeframe_status=timeframe["status"],
        source_url=source_url_val,
        source_legislation=source_legislation_val,
    )
    features["_staleness_reasons"] = "; ".join(stale["staleness_reasons"])
    features["_staleness_severity"] = stale["stale_severity"]

    mapping = IndicatorMapping(
        pillar=int(ind_id.split(".", 1)[0]),
        indicator=ind_id,
        score=score,
        verbatim_quote=quote,
        quote_start=chunk.start + local_start,
        quote_end=chunk.start + local_end,
        quote_context=quote_context,
        source_legislation=source_legislation_val,
        last_update=ts_verification.get("best_date") or last_update_val,
        source_url=source_url_val,
        scope=scope_value,
        coverage=_text_field("coverage"),
        cov_name="Cross-cutting" if scope_value == "horizontal" else "Sectoral" if scope_value == "sectoral" else "Sectoral",
        cluster=_text_field("cluster"),
        name=_text_field("name"),
        policy_description=_text_field("policy_description"),
        features=features,
        impact=justification,
        requires_human_review=score_not_implemented,
        extraction_provider=llm_provider.name,
        timestamp_verification=ts_verification,
        mapping_decision="supported",
        mapping_confidence=0.8,
        mapping_confidence_type="rule_based_eligibility",
        eligibility_evidence_spans=eligibility.evidence_spans,
        eligibility_verifier_mode=eligibility.verifier_mode,
    )

    import main as main_module

    main_module.format_and_clean_mapping(mapping, data, chunk.text)

    validation = validate_mapping(
        mapping,
        quote=mapping.verbatim_quote,
        chunk_text=chunk.text,
        indicator_id=ind_id,
        features=features,
        include_semantic_check=False,
    )
    if validation.level == "reject":
        yield _sse(
            "rejected",
            RejectedExtraction(
                reason="; ".join(validation.reasons),
                chunk_preview=chunk.text[:200],
            ).model_dump(),
        )
        return
    if validation.level == "flag":
        mapping.requires_human_review = True
        mapping.flag_reasons = list(dict.fromkeys([*pre_flag_reasons, *validation.reasons]))
    elif pre_flag_reasons:
        mapping.requires_human_review = True
        mapping.flag_reasons = pre_flag_reasons

    from agents.analyst import AnalystAgent

    mapping.impact = await AnalystAgent(llm_provider).run(
        chunk_text=chunk.text,
        indicator_id=ind_id,
        extracted_data=data,
        evidence_spans=eligibility.evidence_spans,
    )
    main_module.format_and_clean_mapping(mapping, data, chunk.text)

    yield _sse("mapping", mapping.model_dump())
