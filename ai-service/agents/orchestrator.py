"""Orchestrator Agent implementation.

Coordinates the MAS pipeline:
1. Calls ExtractorAgent to extract features and verbatim quote.
2. Uses CriticAgent to verify the quote substring and find absolute offsets.
3. Uses CriticAgent to run deterministic scoring and source auditing.
4. Calls AnalystAgent to draft a multi-paragraph legal impact/comment analysis.
5. Populates the new 10-field RDTII 2.1 schema fields (and their compatibility aliases).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple, List, get_args

from chunker import Chunk
from classifier import classify_indicator
from coverage_classifier import classify_coverage
from features import get_feature_spec
from country_detector import detect_country
from timeframe_extractor import extract_timeframe, build_timeframe_column, format_to_month_year
from staleness_checker import check_staleness
from source_validator import grade_source
from extraction_repair import prepare_extraction_with_repair, repair_max_attempts_from_env
from services.mapping_cleanup import format_and_clean_mapping
from validation import validate_mapping

from schemas import ExtractionResponse, IndicatorId, IndicatorMapping, RejectedExtraction
from providers.base import LLMProvider, ExtractionError

# Indicators the output schema can actually represent. The keyword classifier
# may surface indicators outside this set (e.g. "5.3" from Pillar-5 content);
# those cannot be built into an IndicatorMapping, so they are skipped up front
# rather than crashing the whole document run. MVP scope is Pillars 6 and 7.
SUPPORTED_MAPPING_INDICATORS = frozenset(get_args(IndicatorId))

from agents.extractor import ExtractorAgent
from agents.score_checker import check_generic_score, is_generic_scored
from scoring.scope_overrides import apply_scope_override
from agents.analyst import AnalystAgent, analyst_enabled
from agents.critic import CriticAgent
from agents.eligibility import EligibilityVerifier, rejected_from_eligibility

logger = logging.getLogger(__name__)


#: One id per PROCESS, not per orchestrator. Callers build an orchestrator per
#: document (the golden evaluator and the submission pipeline both do), so an
#: instance-scoped id split a single `python main.py ...` into one "run" per
#: document — which made the run rollup useless for the question it exists to
#: answer, "what did the thing I just ran produce?". A long-lived API server is
#: the trade-off: everything since boot shares an id there, and analysis should
#: group by document_id instead. RDTII_RUN_ID overrides it.
_RUN_ID: str | None = None


def _run_id() -> str:
    global _RUN_ID
    if _RUN_ID is None:
        _RUN_ID = os.getenv("RDTII_RUN_ID", "").strip() or (
            f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        )
    return _RUN_ID


def _make_trajectory_writer(provider: LLMProvider):
    """Build the append-only candidate log, or a disabled stub.

    ON by default. This is the write-only half of the RLVR seam: it records what
    the extractor produced and what the label-free proxy reward thought of it,
    and it changes no output row — so a full submission run can carry it without
    the result differing by a byte. Set ``RDTII_TRAJECTORY_LOG=off`` to disable,
    or to a path to choose the file.

    Nothing reads these records back during a run. They exist so a researcher's
    later approve/reject can be joined to the candidate it judged, via
    (indicator_id, quote_hash) against ``verified_evidence``.

    Any failure here degrades to disabled rather than raising: a logging
    side-channel must never be the reason an extraction fails.
    """
    raw = os.getenv("RDTII_TRAJECTORY_LOG", "").strip()
    if raw.lower() in {"0", "off", "false", "no"}:
        return None
    try:
        from rlvr.trajectory import TrajectoryWriter

        if raw:
            path = Path(raw)
        else:
            root = Path(__file__).resolve().parents[2]
            path = root / "evaluation" / "trajectories" / "trajectory.jsonl"
        run_id = _run_id()
        writer = TrajectoryWriter(
            path=path,
            run_id=run_id,
            provider=getattr(provider, "name", "unknown"),
            model=str(getattr(provider, "model_name", "") or "unknown"),
        )
        logger.info("trajectory logging on: run_id=%s -> %s", run_id, path)
        return writer
    except Exception as exc:  # noqa: BLE001 — never break extraction to log it
        logger.warning("trajectory logging unavailable (%s) — continuing without it", exc)
        return None


def _runtime_hook(name: str, default):
    """Keep legacy API monkeypatch points without importing the web app.

    The extraction pipeline is also used by the lean CLI and offline evaluator.
    Importing ``ai-service/main.py`` there pulls in FastAPI even though neither
    caller serves HTTP. When the web entry point is already loaded, retain its
    patchable compatibility hooks; otherwise use the dependency directly.
    """
    main_module = sys.modules.get("main")
    return getattr(main_module, name, default) if main_module is not None else default


class MASOrchestrator:
    """Orchestrates the Multi-Agent System (MAS) pipeline."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.extractor = ExtractorAgent(provider)
        self.analyst = AnalystAgent(provider)
        self.critic = CriticAgent()
        self.eligibility = EligibilityVerifier(provider)
        self.repair_max_attempts = repair_max_attempts_from_env()
        # Per-run cache for the cross-model generic-score check (keyed by
        # indicator + normalised quote) so a repeated provision costs one call.
        self._score_check_cache: dict = {}
        self._trajectory = _make_trajectory_writer(provider)

    def _log_trajectory(
        self,
        *,
        document_id: str,
        chunk_index: int,
        chunk_text: str,
        indicator_id: str,
        mapping: IndicatorMapping,
        raw_score: float | None,
    ) -> None:
        """Append one candidate + its proxy reward. Never raises.

        The proxy is computed here rather than read from anywhere: it is sync,
        label-free and free of API calls by construction, which is exactly what
        makes it safe to run inline on a real extraction.
        """
        if self._trajectory is None:
            return
        try:
            from rlvr.reward import score_candidate

            candidate = {
                "verbatim_quote": mapping.verbatim_quote,
                "article_clause": mapping.article_clause,
                "source_legislation": mapping.source_legislation,
                "source_url": mapping.source_url,
                "last_update": mapping.last_update,
                "scope": mapping.scope,
            }
            proxy = score_candidate(
                candidate,
                chunk_text=chunk_text,
                indicator_id=indicator_id,
                raw_score=raw_score,
            )
            self._trajectory.log_candidate(
                document_id=document_id,
                chunk_index=chunk_index,
                indicator_id=indicator_id,
                country_code=str((mapping.features or {}).get("_country_code") or ""),
                sampling={"temperature": 0, "sample_index": 0, "k": 1, "greedy": True},
                candidate=candidate,
                proxy=proxy.as_record(),
                selected=True,
                fingerprint="",
            )
        except Exception as exc:  # noqa: BLE001 — logging must never break a run
            logger.warning("trajectory log skipped for %s: %s", indicator_id, exc)

    async def run_pipeline(
        self,
        text: str,
        pdf_metadata: dict | None = None,
        target_indicators: list[str] | None = None,
    ) -> ExtractionResponse:
        """Execute the entire MAS pipeline on the input text.

        ``target_indicators`` bypasses the keyword classifier: every chunk is
        evaluated against exactly those indicators. Use it when the caller
        already knows which indicator a document evidences (e.g. Round 2
        baseline runs, where the official inventory names the indicator per
        law) — classifier recall then stops being a bottleneck for
        non-curated pillars and languages.
        """
        from validation import reset_quote_registry
        reset_quote_registry()

        from submission.pipeline import _document_self_title, _names_disagree

        _doc_self_title = _document_self_title(text)
        # Stable per-document id for the trajectory join key. Content-addressed
        # rather than a counter so the same document re-extracted in a later run
        # lands under the same id, and so it survives a caller that supplies no
        # filename (the CLI path and the offline evaluator both do).
        _document_id = (
            str((pdf_metadata or {}).get("source_sha256") or "")
            or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        )

        t0 = time.time()
        from chunker import regex_legal_chunker
        chunks = regex_legal_chunker(text)

        # The chunk's ordinal is part of the trajectory join key, so it has to
        # survive the filter below — a plain `for chunk in chunks` loses it.
        chunk_groups: list[tuple[int, Chunk, list[tuple[str, dict]]]] = []
        for chunk_index, chunk in enumerate(chunks):
            indicators: list[tuple[str, dict]] = []
            candidate_ids = (
                target_indicators
                if target_indicators is not None
                else _runtime_hook("classify_indicator", classify_indicator)(chunk.text)
            )
            for indicator_id in candidate_ids:
                if indicator_id not in SUPPORTED_MAPPING_INDICATORS:
                    logger.warning(
                        "Skipping unsupported indicator %s (outside RDTII output schema)",
                        indicator_id,
                    )
                    continue
                spec = get_feature_spec(indicator_id)
                if spec:
                    indicators.append((indicator_id, spec))
            if indicators:
                chunk_groups.append((chunk_index, chunk, indicators))

        semaphore = asyncio.Semaphore(int(os.getenv("RDTII_CHUNK_CONCURRENCY", "5")))

        async def _process_chunk_group(
            chunk_index: int,
            chunk: Chunk,
            indicators: list[tuple[str, dict]],
        ) -> list[tuple[IndicatorMapping | None, RejectedExtraction | None]]:
            results_list = []
            async with semaphore:
                # Use extractor agent (batch extraction is preferred)
                try:
                    batch = await self.extractor.run_batch(chunk.text, indicators)
                except Exception as e:
                    logger.warning("Extractor batch failed, falling back to per-indicator: %s", e)
                    batch = {}
                    for ind_id, spec in indicators:
                        try:
                            batch[ind_id] = await self.extractor.run(chunk.text, ind_id, spec)
                        except Exception:
                            batch[ind_id] = None

                for ind_id, spec in indicators:
                    data = batch.get(ind_id) if isinstance(batch, dict) else None
                    if not data:
                        results_list.append((None, RejectedExtraction(
                            reason="missing indicator in batch/fallback response",
                            chunk_preview=chunk.text[:200],
                        )))
                        continue

                    # 1. Repair loop — schema, quote verification, and validation preflight.
                    prepared = await prepare_extraction_with_repair(
                        provider=self.provider,
                        chunk=chunk,
                        indicator_id=ind_id,
                        feature_spec=spec,
                        data=data,
                        pdf_metadata=pdf_metadata,
                        max_attempts=self.repair_max_attempts,
                    )
                    if prepared["status"] == "skip":
                        continue
                    if prepared["status"] == "reject":
                        results_list.append((None, RejectedExtraction(
                            reason=prepared["reason"],
                            chunk_preview=chunk.text[:200],
                            raw_output=prepared.get("raw_output", data),
                        )))
                        continue

                    data = prepared["data"]
                    quote = prepared["quote"]
                    local_start = prepared["local_start"]
                    local_end = prepared["local_end"]
                    features = prepared["features"]
                    pre_flag_reasons = prepared.get("pre_flag_reasons", [])

                    # 2. Independent eligibility gate — before scoring or
                    # rationale generation, and blind to both of them.
                    eligibility = await self.eligibility.verify(quote, ind_id, features)
                    # Default "flag" keeps an ineligible mapping but flags it for
                    # human review instead of dropping it — recall-preserving,
                    # aligned with the official 20% human-validation step and our
                    # other flag-not-drop gates. RDTII_ELIGIBILITY_MODE=reject
                    # opts into the precision-first behaviour (hard-drop any
                    # mapping the eligibility gate does not support).
                    _elig_flag_mode = (
                        os.getenv("RDTII_ELIGIBILITY_MODE", "flag").strip().lower() != "reject"
                    )
                    if not eligibility.supported and not _elig_flag_mode:
                        results_list.append((None, rejected_from_eligibility(
                            eligibility,
                            chunk.text[:200],
                            raw_output=data,
                        )))
                        continue
                    if not eligibility.supported:
                        pre_flag_reasons.append(
                            "Eligibility flag: " + (
                                "; ".join(eligibility.exclusion_reasons)
                                or "candidate indicator not independently supported by the quote"
                            )
                        )
                    _mapping_decision = (
                        "supported" if eligibility.supported else eligibility.decision
                    )

                    # 3. Critic Agent — deterministic scoring
                    raw_score, score_justification = self.critic.evaluate_score(ind_id, features)
                    score_not_implemented = score_justification == "Scoring rules not implemented."
                    if score_not_implemented:
                        pre_flag_reasons.append(
                            f"Deterministic scoring for indicator {ind_id} is not implemented."
                        )

                    # 3a. Deterministic scope guard — methodology-grounded
                    # cross-domain traps (a product-control law keyword-matching a
                    # digital-trade indicator; 9.1's illegal-content exception).
                    # Only ever lowers to 0; runs before the LLM checker so a
                    # scope mismatch costs no extra call.
                    if raw_score and not score_not_implemented:
                        _law_name = (
                            data.get("source_legislation")
                            or (pdf_metadata or {}).get("source_legislation")
                            or ""
                        )
                        scoped, score_justification = apply_scope_override(
                            ind_id, quote, _law_name, float(raw_score), score_justification
                        )
                        if scoped != raw_score:
                            pre_flag_reasons.append(score_justification)
                            raw_score = scoped

                    # 3b. Cross-model check (Maker/Checker) — only for generic-
                    # scored indicators with a still-positive score, the P9-P12
                    # cluster where a single model over-reads principle/relevance
                    # as a measure. Keeps the conservative minimum; never drops a row.
                    if raw_score and not score_not_implemented and is_generic_scored(ind_id):
                        check = await check_generic_score(
                            self.provider, ind_id, quote, float(raw_score),
                            cache=self._score_check_cache,
                        )
                        if not check.agreed:
                            raw_score = check.score
                            score_justification = check.reason
                            pre_flag_reasons.append(check.reason)

                    # Until all validation passes, use the deterministic
                    # justification. The free-form Analyst runs last.
                    impact_comments_val = score_justification

                    # Post-processing / cleaning metadata
                    source_url_val = data.get("source_url", "")
                    source_legislation_val = data.get("source_legislation") or ""
                    # The caller's fetched URL beats an absent LLM echo — the
                    # source-grade audit and staleness checks are URL-driven.
                    source_url_val = (
                        source_url_val or (pdf_metadata or {}).get("source_url", "")
                    )
                    # The document's own opening title beats the model's guess —
                    # the model names the act a provision talks ABOUT (a Cyber
                    # Security Act cross-reference became "Privacy Act 1988").
                    # Same rule build_row applies at the submission boundary;
                    # applied here so the runtime/API and audit views agree.
                    if _doc_self_title and _names_disagree(
                        source_legislation_val, _doc_self_title
                    ):
                        pre_flag_reasons.append(
                            "Law name corrected to the document's own title "
                            f"(model said: {source_legislation_val[:60]})"
                        )
                        source_legislation_val = _doc_self_title
                    last_update_val = data.get("last_update") or ""
                    raw_scope = (data.get("scope") or "").strip().lower()
                    scope_value = raw_scope if raw_scope in {"horizontal", "sectoral"} else "unknown"

                    # Source grade audit
                    src_grade, src_requires_review, src_reasons = self.critic.audit_source(
                        source_url_val, source_legislation_val
                    )
                    features["_source_grade"] = src_grade

                    # Coverage classification override
                    if scope_value == "unknown":
                        cc = _runtime_hook("classify_coverage", classify_coverage)(
                            provision_text=quote,
                            source_legislation=source_legislation_val,
                            indicator_id=ind_id,
                        )
                        scope_value = cc["scope"]
                        features["_coverage_reasons"] = "; ".join(cc.get("reasons", []))

                    # Timeframe extraction
                    tf = _runtime_hook("extract_timeframe", extract_timeframe)(
                        text=chunk.text,
                        source_legislation=source_legislation_val,
                        source_url=source_url_val,
                    )
                    tf_column = _runtime_hook(
                        "build_timeframe_column", build_timeframe_column
                    )(
                        status=tf["status"],
                        in_force_date=tf.get("in_force_date") or last_update_val,
                        last_amended_date=tf.get("last_amended_date"),
                        repealed_date=tf.get("repealed_date"),
                    )
                    features["_timeframe_status"] = tf["status"]
                    features["_timeframe_column"] = tf_column

                    # Triple timestamp verification
                    ts_verification = {}
                    if source_url_val and last_update_val:
                        try:
                            from crawler import verify_law_timeline
                            ts_verification = await verify_law_timeline(
                                source_url_val, last_update_val,
                            )
                        except Exception:
                            pass

                    # Staleness / outdated-law detection
                    stale = _runtime_hook("check_staleness", check_staleness)(
                        last_update=last_update_val,
                        timeframe_status=tf["status"],
                        source_url=source_url_val,
                        source_legislation=source_legislation_val,
                    )
                    features["_staleness_reasons"] = "; ".join(stale["staleness_reasons"])
                    features["_staleness_severity"] = stale["stale_severity"]

                    # Determine pillar
                    pillar_num = int(ind_id.split(".", 1)[0])

                    # Build IndicatorMapping (guarded so a field-validation error
                    # rejects this single mapping instead of crashing the run)
                    try:
                        mapping_obj = IndicatorMapping(
                        pillar=pillar_num,
                        indicator=ind_id,
                        score=raw_score,
                        verbatim_quote=quote,
                        quote_start=chunk.start + local_start,
                        quote_end=chunk.start + local_end,
                        source_legislation=source_legislation_val,
                        document_id=_document_id,
                        chunk_index=chunk_index,
                        last_update=ts_verification.get("best_date") or last_update_val,
                        source_url=source_url_val,
                        scope=scope_value,
                        coverage=data.get("coverage") or "",
                        cov_name="Cross-cutting" if scope_value == "horizontal" else "Sectoral",
                        cluster=data.get("cluster") or "",
                        name=data.get("name") or "",
                        policy_description=data.get("policy_description") or "",
                        features=features,
                        impact=impact_comments_val,
                        requires_human_review=src_requires_review or score_not_implemented,
                        extraction_provider=self.provider.name,
                        timestamp_verification=ts_verification,
                        mapping_decision=_mapping_decision,
                        mapping_confidence=0.8,
                        mapping_confidence_type="rule_based_eligibility",
                        eligibility_evidence_spans=eligibility.evidence_spans,
                        eligibility_verifier_mode=eligibility.verifier_mode,
                        )
                    except Exception as exc:
                        logger.warning("Could not build mapping for %s: %s", ind_id, exc)
                        results_list.append((None, RejectedExtraction(
                            reason=f"invalid mapping for {ind_id}: {exc}",
                            chunk_preview=chunk.text[:200],
                        )))
                        continue

                    # Import format_and_clean_mapping lazily to clean up fields
                    _runtime_hook(
                        "format_and_clean_mapping", format_and_clean_mapping
                    )(mapping_obj, data, chunk.text)

                    # Now explicitly populate the new 10 RDTII 2.1 Fields & compatibility aliases
                    mapping_obj.Pillar_ID = f"{pillar_num}.0"
                    mapping_obj.pillar_id = mapping_obj.Pillar_ID
                    
                    mapping_obj.Indicator_ID = ind_id
                    mapping_obj.indicator_id = ind_id
                    
                    # Category score defaults to the score, capped at 1.0 (subagent/orchestrator handles grouping)
                    mapping_obj.Cat_Score = min(raw_score, 1.0)
                    mapping_obj.cat_score = mapping_obj.Cat_Score
                    
                    mapping_obj.Raw_Score = raw_score
                    mapping_obj.raw_score = raw_score
                    
                    mapping_obj.Act_and_or_practice = mapping_obj.source_legislation
                    mapping_obj.act_and_or_practice = mapping_obj.source_legislation
                    mapping_obj.act_title = mapping_obj.source_legislation
                    
                    # Capitalize Coverage scope value
                    cov_display = scope_value.capitalize() if scope_value != "unknown" else ""
                    mapping_obj.Coverage = cov_display
                    mapping_obj.coverage = cov_display
                    
                    # Ensure impact is fully loaded with generated comments
                    mapping_obj.Impact_or_comments = mapping_obj.impact
                    mapping_obj.impact_or_comments = mapping_obj.impact
                    mapping_obj.impact_comments = mapping_obj.impact
                    
                    # Use timeframe display
                    from excel_exporter import _timeframe_display
                    tf_display = _timeframe_display(mapping_obj)
                    mapping_obj.Timeframe = tf_display
                    mapping_obj.timeframe = tf_display
                    
                    mapping_obj.References = source_url_val
                    mapping_obj.references = source_url_val
                    
                    note_val = data.get("note") or data.get("Note") or ""
                    mapping_obj.Note = note_val
                    mapping_obj.note = note_val

                    # Validate mapping against hallucination filters
                    vr = validate_mapping(
                        mapping_obj,
                        quote=mapping_obj.verbatim_quote,
                        chunk_text=chunk.text,
                        indicator_id=ind_id,
                        features=features,
                        include_semantic_check=False,
                    )
                    if vr.level == "reject":
                        results_list.append((None, RejectedExtraction(
                            reason="; ".join(vr.reasons),
                            chunk_preview=chunk.text[:200],
                        )))
                        continue
                    if vr.level == "flag":
                        mapping_obj.requires_human_review = True
                        mapping_obj.flag_reasons = list(dict.fromkeys([*pre_flag_reasons, *vr.reasons]))
                    elif pre_flag_reasons:
                        mapping_obj.requires_human_review = True
                        mapping_obj.flag_reasons = pre_flag_reasons

                    # 4. Analyst runs only for an accepted mapping and receives
                    # neither the numeric score nor a conclusion to rationalise.
                    # It is one extra LLM call per ACCEPTED mapping and produces
                    # the prose rationale column only — nothing downstream scores
                    # off it. Self-evaluation runs compare deterministic scores,
                    # so they set RDTII_ANALYST=off and skip the call; the
                    # submission pipeline must leave it on (the rationale is a
                    # submitted column).
                    # Reassigning impact_comments_val (not just mapping_obj.impact)
                    # is load-bearing: the three legacy alias fields written below
                    # read this variable, so writing only .impact would leave the
                    # aliases carrying the deterministic justification while the
                    # main field carries the Analyst's — one response contradicting
                    # itself.
                    if analyst_enabled():
                        impact_comments_val = await self.analyst.run(
                            chunk_text=chunk.text,
                            indicator_id=ind_id,
                            extracted_data=data,
                            evidence_spans=eligibility.evidence_spans,
                        )
                        mapping_obj.impact = impact_comments_val
                    _runtime_hook(
                        "format_and_clean_mapping", format_and_clean_mapping
                    )(mapping_obj, data, chunk.text)
                    mapping_obj.Impact_or_comments = impact_comments_val
                    mapping_obj.impact_or_comments = impact_comments_val
                    mapping_obj.impact_comments = impact_comments_val

                    # Write-only: record the candidate the researcher is about
                    # to see, with the label-free proxy's read of it. Logged
                    # AFTER the mapping is final so the record matches what was
                    # actually returned, not an intermediate. `selected=True`
                    # for every row today — best-of-N is not wired, so this is
                    # the single greedy draw and there is nothing it beat.
                    self._log_trajectory(
                        document_id=_document_id,
                        chunk_index=chunk_index,
                        chunk_text=chunk.text,
                        indicator_id=ind_id,
                        mapping=mapping_obj,
                        raw_score=raw_score,
                    )

                    results_list.append((mapping_obj, None))

            return results_list

        # Execute parallel processing of chunk groups
        all_results = await asyncio.gather(
            *[_process_chunk_group(i, c, inds) for i, c, inds in chunk_groups]
        )

        logger.debug("[MAS TIMING] total=%.1fs", time.time() - t0)

        mappings: list[IndicatorMapping] = []
        rejected: list[RejectedExtraction] = []
        for chunk_results in all_results:
            for mapping, rej in chunk_results:
                if mapping:
                    mappings.append(mapping)
                elif rej:
                    rejected.append(rej)

        # Post-process: Aggregate Cat_Score per Pillar / Category
        # RDTII 2.1: Cat_Score is the sum of raw scores under the same pillar, capped at 1.0.
        pillar_scores: dict[int, float] = {}
        for m in mappings:
            pillar_scores[m.pillar] = pillar_scores.get(m.pillar, 0.0) + m.Raw_Score

        for m in mappings:
            capped_score = min(pillar_scores[m.pillar], 1.0)
            m.Cat_Score = capped_score
            m.cat_score = capped_score

        return ExtractionResponse(
            mappings=mappings,
            rejected=rejected,
            provider=self.provider.name,
            source_text=text,
        )
