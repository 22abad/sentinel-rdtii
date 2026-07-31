"""Measure whether the proxy reward can actually pick the right candidate.

This is step 1 of the RLVR plan and the gate on everything after it: if the
label-free proxy reward cannot rank a real extraction above manufactured bad
ones, best-of-N is 4x extractor spend for noise and should not be wired in.

Runs against the reviewed golden set. The DEFAULT mode is fully offline — no
API calls, no network, no database — and emits:

    rlvr-measurement.json   machine-readable, one object per run
    rlvr-measurement.md     the human view
    rlvr-measurement-history.jsonl   append-only, one summary line per run

``--with-llm`` swaps the deterministic eligibility arm for the real verifier.
That mode DOES make billed API calls, one per distinct (indicator, quote), and
writes to the parallel ``rlvr-measurement-llm.*`` stem so the two never
overwrite each other. Read them as two different measurements of two different
systems: the offline number reflects a stub, the --with-llm number reflects
what production would actually do, and only the latter gates wiring best-of-N.

Usage:
    python3 scripts/rlvr_measure.py
    python3 scripts/rlvr_measure.py --with-llm deepseek     # costs money
    python3 scripts/rlvr_measure.py --out-dir /tmp/report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))

# Load provider credentials the same way the app does. Only --with-llm needs
# them; the default offline run works with none of this set.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001 — offline runs must not depend on dotenv
    pass

from chunker import regex_legal_chunker  # noqa: E402
from evaluation.metrics import normalize_evidence  # noqa: E402
from evaluation.models import GoldenCase, OfflineProviderResponse  # noqa: E402
from evaluation.runner import load_dataset  # noqa: E402
from rlvr.distractors import (  # noqa: E402
    HYGIENE_KINDS,
    SEMANTIC_KINDS,
    build_candidate_set,
)
from rlvr import oracle as oracle_mod  # noqa: E402
from rlvr import reward as reward_mod  # noqa: E402
from rlvr.oracle import score_against_case  # noqa: E402
from rlvr.reward import score_candidate  # noqa: E402


def reward_config() -> dict:
    """Every constant that produced the numbers in this report.

    Emitted with the results so a report is self-describing: reading a top-1
    rate without knowing the weights and thresholds behind it tells you a
    score changed but not why, and these constants are exactly what gets
    tuned between runs.
    """
    return {
        "proxy": {
            "component_weights": dict(reward_mod.WEIGHTS),
            "gates": [
                "quote_present",
                "quote_grounded",
                "offsets_recover_quote",
                "score_in_allowed_tiers",
                "not_a_section_header",
                "quote_not_a_page_dump",
            ],
            "quote_dump_gate_chars": reward_mod.QUOTE_DUMP_GATE_CHARS,
            "chunk_coverage_soft_limit": reward_mod.CHUNK_COVERAGE_SOFT_LIMIT,
            "chunk_coverage_floor_value": reward_mod.CHUNK_COVERAGE_FLOOR_VALUE,
            "chunker": "regex_legal_chunker (deterministic regex + UAX#29)",
            "existence_indicators": sorted(reward_mod.EXISTENCE_INDICATORS),
            "existence_exempt_components": [
                "single_provision",
                "eligibility_supported (only when an external verdict is supplied — "
                "the deterministic branches are safe for a bare title, the LLM arm "
                "is not)",
            ],
            "eligibility_abstain_policy": (
                "a verifier that raises yields no verdict; the term is dropped "
                "from the objective rather than scored 0.0"
            ),
        },
        "oracle": {
            "evidence_threshold": oracle_mod.EVIDENCE_THRESHOLD,
            "w_matched": oracle_mod.W_MATCHED,
            "w_citation_exact": oracle_mod.W_CITATION_EXACT,
            "w_score_correct": oracle_mod.W_SCORE_CORRECT,
            "w_article_correct": oracle_mod.W_ARTICLE_CORRECT,
            "w_scope_correct": oracle_mod.W_SCOPE_CORRECT,
            "r_negative_case_hit": oracle_mod.R_NEGATIVE_CASE_HIT,
            "r_missed_positive": oracle_mod.R_MISSED_POSITIVE,
            "r_avoided_negative": oracle_mod.R_AVOIDED_NEGATIVE,
            "score_term_active": False,
            "score_term_note": (
                "raw_score is not supplied in this study — it measures EVIDENCE "
                "selection, which is what best-of-N chooses between. Max "
                "achievable oracle total is therefore 0.85, not 1.0."
            ),
        },
    }


def component_analysis(results: list[dict]) -> dict:
    """Per-component discrimination: which reward terms actually do work.

    For each component, the mean value on the real extraction versus the mean
    on each distractor kind. A component whose reference mean equals its
    distractor mean is carrying weight in the objective while contributing
    nothing to the decision — that is what this table exists to expose.
    """
    buckets: dict[str, dict[str, list[float]]] = {}
    weights: dict[str, float] = {}

    for case in results:
        for candidate in case["candidates"]:
            bucket_key = "reference" if candidate["is_reference"] else candidate["kind"]
            for name, comp in candidate["proxy"].get("components", {}).items():
                entry = buckets.setdefault(name, {})
                entry.setdefault(bucket_key, []).append(comp["value"])
                weights[name] = comp["weight"]

    analysis: dict[str, dict] = {}
    for name, by_kind in sorted(buckets.items()):
        reference_values = by_kind.get("reference", [])
        reference_mean = (
            statistics.fmean(reference_values) if reference_values else None
        )
        distractor_values = [
            value
            for kind, values in by_kind.items()
            if kind != "reference"
            for value in values
        ]
        distractor_mean = (
            statistics.fmean(distractor_values) if distractor_values else None
        )
        analysis[name] = {
            "weight": weights[name],
            "weight_share": weights[name] / sum(weights.values()),
            "reference_mean": reference_mean,
            "distractor_mean": distractor_mean,
            "discrimination": (
                reference_mean - distractor_mean
                if reference_mean is not None and distractor_mean is not None
                else None
            ),
            "scored_on_candidates": sum(len(v) for v in by_kind.values()),
            "by_kind_mean": {
                kind: statistics.fmean(values)
                for kind, values in sorted(by_kind.items())
            },
        }
    return analysis

CASES_PATH = ROOT / "evaluation" / "golden" / "cases.jsonl"
DOCUMENTS_PATH = ROOT / "evaluation" / "golden" / "documents.jsonl"
FIXTURES_PATH = ROOT / "evaluation" / "fixtures" / "offline-provider-responses.jsonl"
DEFAULT_OUT_DIR = ROOT / "evaluation" / "reports"


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _load_fixtures() -> dict[tuple[str, str], dict]:
    fixtures: dict[tuple[str, str], dict] = {}
    for line in FIXTURES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = OfflineProviderResponse.model_validate_json(line)
        if record.response is not None:
            fixtures[(record.document_id, record.indicator_id)] = record.response
    return fixtures


def _llm_eligibility_map(
    provider_name: str, work: list[tuple[str, str, dict]]
) -> dict[tuple[str, str], tuple[float | None, str]]:
    """Run EligibilityVerifier's FULL cascade (deterministic + blind LLM).

    Answers one question the free study structurally cannot: six of the ten
    P6/P7 indicators (6.1, 6.2, 6.4, 6.5, 7.1, 7.2) have only feature-driven
    branches in ``deterministic_eligibility``, so with distractors inheriting
    the reference's features that term returns 1.0 for every candidate. The
    criteria those six encode — a *ban* versus a *condition* on transfer, or
    "a framework exists" — are semantic judgements over shared vocabulary,
    which is exactly what the LLM arm exists for.

    Costs real API calls, so it is opt-in via --with-llm and never part of the
    default reproducible run. Failures are reported loudly, never silently
    downgraded to the deterministic answer.
    """
    import asyncio

    from agents.eligibility import EligibilityVerifier
    from providers import get_provider

    provider = get_provider(provider_name)
    verifier = EligibilityVerifier(provider)

    # De-duplicate first: reference and metadata_stripped share a quote, and
    # the verifier caches per quote anyway.
    unique: dict[tuple[str, str], tuple[str, str, dict]] = {}
    for quote, indicator_id, features in work:
        unique.setdefault((indicator_id, " ".join(quote.split())),
                          (quote, indicator_id, features))

    async def _run() -> dict[tuple[str, str], tuple[float | None, str]]:
        semaphore = asyncio.Semaphore(8)
        failures: list[str] = []

        async def _one(key, payload):
            quote, indicator_id, features = payload
            async with semaphore:
                try:
                    result = await verifier.verify(quote, indicator_id, features)
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{indicator_id}: {type(exc).__name__}: {exc}")
                    # None, not 0.0 — an error is not a verdict of "ineligible".
                    return key, (None, f"VERIFIER ERROR: {type(exc).__name__}: {exc}")
            detail = (
                f"[{result.verifier_mode}] "
                + ("eligible for this indicator" if result.supported
                   else "; ".join(result.exclusion_reasons) or "not supported")
            )
            if result.verifier_failed:
                # EligibilityVerifier swallows its own LLM/parse errors and
                # abstains (correct for the pipeline, which must stay
                # precision-first). That made these invisible here: the loud
                # report below counted zero failures while a broken call was
                # being scored as a real "ineligible" verdict against whichever
                # candidate hit it.
                failures.append(f"{indicator_id}: abstained — {'; '.join(result.exclusion_reasons)}")
                return key, (None, detail[:200])
            return key, (1.0 if result.supported else 0.0, detail[:200])

        pairs = await asyncio.gather(*(_one(k, v) for k, v in unique.items()))
        if failures:
            # Loud, never silently downgraded to the deterministic answer.
            print(f"!! {len(failures)} of {len(unique)} verifier calls FAILED:", flush=True)
            for line in failures[:5]:
                print(f"     {line}", flush=True)
        return dict(pairs)

    return asyncio.run(_run())


def _host_chunk(document_text: str, gold_quote: str) -> tuple[str, int] | None:
    """The chunk the reference quote actually lives in.

    The pipeline scores a candidate against its chunk, never against the whole
    document, so the study has to do the same or it is measuring a decision
    the selector never makes.
    """
    normalized_gold = normalize_evidence(gold_quote)
    for index, chunk in enumerate(regex_legal_chunker(document_text)):
        if normalized_gold and normalized_gold in normalize_evidence(chunk.text):
            return chunk.text, index
    return None


def _evaluate_case(
    case: GoldenCase,
    reference: dict,
    document_text: str,
    llm_elig: dict[tuple[str, str], tuple[float | None, str]] | None = None,
) -> dict | None:
    """Score one synthetic best-of-N set. Returns None when unbuildable."""
    host = _host_chunk(document_text, reference.get("verbatim_quote") or "")
    if host is None:
        return None
    chunk_text, chunk_index = host

    candidates = build_candidate_set(reference, chunk_text=chunk_text)
    if len(candidates) < 2:
        return None

    scored = []
    for candidate in candidates:
        override = None
        if llm_elig is not None:
            key = (case.indicator_id,
                   " ".join((candidate.data.get("verbatim_quote") or "").split()))
            override = llm_elig.get(key)
        proxy = score_candidate(
            candidate.data,
            chunk_text=chunk_text,
            indicator_id=case.indicator_id,
            eligibility_override=override,
        )
        # raw_score is deliberately None: this study measures EVIDENCE
        # selection, which is what best-of-N chooses between. The score is
        # computed downstream, deterministically, from the winner's features.
        oracle = score_against_case(
            candidate.data, case, document_text=document_text, raw_score=None,
        )
        scored.append(
            {
                "kind": candidate.kind,
                "is_reference": candidate.is_reference,
                "quote_chars": len(candidate.data.get("verbatim_quote", "")),
                "quote_preview": candidate.data.get("verbatim_quote", "")[:160],
                # Flat totals for convenience...
                "proxy_total": proxy.total,
                "proxy_gates_passed": proxy.passed_gates,
                "proxy_failed_gates": list(proxy.failed_gates),
                "oracle_total": oracle.total,
                "oracle_matched": oracle.matched,
                "evidence_similarity": oracle.evidence_similarity,
                # ...and the full breakdown. A reward you cannot decompose
                # after the fact is a reward you cannot debug: every component
                # keeps its value, its weight and the detail string that
                # explains the value.
                "proxy": proxy.as_record(),
                "oracle": oracle.as_record(),
            }
        )

    reference_row = next(row for row in scored if row["is_reference"])
    ref_proxy = reference_row["proxy_total"]

    pairs = []
    for row in scored:
        if row["is_reference"]:
            continue
        pairs.append(
            {
                "kind": row["kind"],
                "reference_proxy": ref_proxy,
                "distractor_proxy": row["proxy_total"],
                # Mirrors best_of_n.select_best, which only replaces the
                # incumbent on a STRICT improvement. A tie therefore keeps the
                # greedy candidate — scoring a tie as a loss here would report
                # failures the selector does not actually make.
                "reference_wins": ref_proxy >= row["proxy_total"],
                "delta": ref_proxy - row["proxy_total"],
            }
        )

    hygiene_top1 = not any(
        row["proxy_total"] > ref_proxy
        for row in scored
        if row["kind"] in HYGIENE_KINDS
    )
    full_top1 = not any(
        row["proxy_total"] > ref_proxy for row in scored if not row["is_reference"]
    )

    return {
        "case_id": case.case_id,
        "country_code": case.country_code,
        "indicator_id": case.indicator_id,
        "document_id": case.document_id,
        "chunk_index": chunk_index,
        "chunk_chars": len(chunk_text),
        "candidates": scored,
        "pairs": pairs,
        "hygiene_top1": hygiene_top1,
        "full_top1": full_top1,
        "reference_proxy": ref_proxy,
        "reference_oracle": reference_row["oracle_total"],
    }


def measure(llm_provider: str | None = None) -> dict:
    cases, documents = load_dataset(
        repo_root=ROOT, cases_path=CASES_PATH, documents_path=DOCUMENTS_PATH
    )
    fixtures = _load_fixtures()

    # Pre-compute the live verdicts in one pass so the verifier's per-quote
    # cache is shared across every case.
    llm_elig = None
    if llm_provider:
        work: list[tuple[str, str, dict]] = []
        for case in cases:
            if not case.should_map:
                continue
            reference = fixtures.get((case.document_id, case.indicator_id))
            if reference is None:
                continue
            host = _host_chunk(documents[case.document_id][1],
                               reference.get("verbatim_quote") or "")
            if host is None:
                continue
            for cand in build_candidate_set(reference, chunk_text=host[0]):
                quote = (cand.data.get("verbatim_quote") or "").strip()
                if quote:
                    work.append((quote, case.indicator_id, cand.data))
        print(f"Running EligibilityVerifier LLM arm over {len(work)} candidates "
              f"via '{llm_provider}' ...", flush=True)
        llm_elig = _llm_eligibility_map(llm_provider, work)
        print(f"  -> {len(llm_elig)} distinct (indicator, quote) verdicts", flush=True)

    results = []
    skipped = []
    for case in cases:
        if not case.should_map:
            # Negative cases have no correct extraction to rank against; they
            # are graded by the harness's negative_case_hits, not here.
            continue
        reference = fixtures.get((case.document_id, case.indicator_id))
        if reference is None:
            skipped.append({"case_id": case.case_id, "reason": "no offline fixture"})
            continue
        text = documents[case.document_id][1]
        evaluated = _evaluate_case(case, reference, text, llm_elig)
        if evaluated is None:
            skipped.append({"case_id": case.case_id, "reason": "too few candidates"})
            continue
        results.append(evaluated)

    all_pairs = [pair for row in results for pair in row["pairs"]]
    by_kind: dict[str, dict] = {}
    for pair in all_pairs:
        entry = by_kind.setdefault(
            pair["kind"], {"total": 0, "wins": 0, "deltas": []}
        )
        entry["total"] += 1
        entry["wins"] += int(pair["reference_wins"])
        entry["deltas"].append(pair["delta"])

    kind_summary = {
        kind: {
            "pairs": entry["total"],
            "reference_wins": entry["wins"],
            "win_rate": entry["wins"] / entry["total"] if entry["total"] else None,
            "mean_delta": statistics.fmean(entry["deltas"]) if entry["deltas"] else 0.0,
            "class": "hygiene" if kind in HYGIENE_KINDS else "semantic",
        }
        for kind, entry in sorted(by_kind.items())
    }

    hygiene_pairs = [p for p in all_pairs if p["kind"] in HYGIENE_KINDS]
    semantic_pairs = [p for p in all_pairs if p["kind"] in SEMANTIC_KINDS]

    def _rate(rows: list[dict]) -> float | None:
        return (
            sum(r["reference_wins"] for r in rows) / len(rows) if rows else None
        )

    case_text = CASES_PATH.read_bytes()
    summary = {
        "cases_measured": len(results),
        "cases_skipped": len(skipped),
        "candidate_sets": len(results),
        "total_pairs": len(all_pairs),
        "hygiene_top1_rate": (
            sum(r["hygiene_top1"] for r in results) / len(results) if results else None
        ),
        "full_top1_rate": (
            sum(r["full_top1"] for r in results) / len(results) if results else None
        ),
        "hygiene_pairwise_win_rate": _rate(hygiene_pairs),
        "semantic_pairwise_win_rate": _rate(semantic_pairs),
        "mean_reference_proxy": (
            statistics.fmean([r["reference_proxy"] for r in results]) if results else 0.0
        ),
        "mean_reference_oracle": (
            statistics.fmean([r["reference_oracle"] for r in results]) if results else 0.0
        ),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "case_set_sha256": hashlib.sha256(case_text).hexdigest(),
        "mode": ("synthetic-distractors+llm-eligibility" if llm_provider
                 else "offline-synthetic-distractors"),
        "llm_provider": llm_provider,
        "reward_config": reward_config(),
        "summary": summary,
        "by_kind": kind_summary,
        "component_analysis": component_analysis(results),
        "cases": results,
        "skipped": skipped,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def render_markdown(report: dict) -> str:
    s = report["summary"]
    # The provenance line must describe the run that actually happened. This
    # string used to be hardcoded to "(no API calls, no network)" regardless of
    # mode, so every --with-llm report asserted it had stayed offline while it
    # was billing one eligibility call per candidate. A report that misstates
    # whether it touched the network cannot be used to justify spending on the
    # next one.
    provider = report.get("llm_provider")
    provenance = (
        f"live LLM eligibility via `{provider}` — REAL API calls, billed"
        if provider
        else "no API calls, no network"
    )
    lines = [
        "# RLVR proxy-reward measurement",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Commit: `{report['commit']}`",
        f"- Mode: `{report['mode']}` ({provenance})",
        f"- Case-set SHA-256: `{report['case_set_sha256']}`",
        f"- Candidate sets: {s['candidate_sets']} "
        f"(skipped {s['cases_skipped']}), pairs compared: {s['total_pairs']}",
        "",
        "## Headline",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Hygiene top-1 (proxy picks the real extraction) | {_pct(s['hygiene_top1_rate'])} |",
        f"| Hygiene pairwise win rate | {_pct(s['hygiene_pairwise_win_rate'])} |",
        f"| Full top-1 (incl. wrong-provision control) | {_pct(s['full_top1_rate'])} |",
        f"| Semantic pairwise win rate (control) | {_pct(s['semantic_pairwise_win_rate'])} |",
        f"| Mean proxy reward of the real extraction | {s['mean_reference_proxy']:.4f} |",
        f"| Mean oracle reward of the real extraction | {s['mean_reference_oracle']:.4f} |",
        "",
        "The semantic row is a CONTROL, not a target. `neighbour_span` is a real,",
        "correctly quoted provision from the same document that is simply the wrong",
        "one. No label-free reward can rule it out; the number is reported so the",
        "proxy's ceiling is visible rather than averaged away.",
        "",
        "## Per distractor type",
        "",
        "| Distractor | Class | Pairs | Reference wins | Win rate | Mean margin |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for kind, entry in report["by_kind"].items():
        lines.append(
            f"| `{kind}` | {entry['class']} | {entry['pairs']} | "
            f"{entry['reference_wins']} | {_pct(entry['win_rate'])} | "
            f"{entry['mean_delta']:+.4f} |"
        )

    config = report["reward_config"]
    proxy_config = config["proxy"]
    lines += [
        "",
        "## Reward configuration that produced these numbers",
        "",
        "### Proxy component weights",
        "",
        "| Component | Weight | Share of objective |",
        "| --- | ---: | ---: |",
    ]
    total_weight = sum(proxy_config["component_weights"].values())
    for name, weight in sorted(
        proxy_config["component_weights"].items(), key=lambda kv: -kv[1]
    ):
        lines.append(f"| `{name}` | {weight:.1f} | {weight / total_weight * 100:.1f}% |")

    lines += [
        "",
        "### Hard gates (any failure collapses the total to 0)",
        "",
        "".join(f"`{g}` " for g in proxy_config["gates"]).strip(),
        "",
        "### Thresholds",
        "",
        "| Constant | Value |",
        "| --- | ---: |",
        f"| `quote_dump_gate_chars` | {proxy_config['quote_dump_gate_chars']} |",
        f"| `chunk_coverage_soft_limit` | {proxy_config['chunk_coverage_soft_limit']} |",
        f"| `chunk_coverage_floor_value` | {proxy_config['chunk_coverage_floor_value']} |",
        f"| `chunker` | {proxy_config['chunker']} |",
        f"| `existence_indicators` | {', '.join(proxy_config['existence_indicators'])} |",
        f"| `existence_exempt_components` | "
        f"{', '.join(proxy_config['existence_exempt_components'])} |",
        "",
        "### Oracle weights (labelled reward — never seen by the selector)",
        "",
        "| Term | Value |",
        "| --- | ---: |",
    ]
    for key, value in config["oracle"].items():
        if isinstance(value, (int, float)):
            lines.append(f"| `{key}` | {value} |")
    lines += ["", f"_{config['oracle']['score_term_note']}_", ""]

    lines += [
        "## Component discrimination (does each weighted term earn its weight?)",
        "",
        "| Component | Weight | Mean on real | Mean on distractors | Discrimination |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, entry in sorted(
        report["component_analysis"].items(),
        key=lambda kv: -(kv[1]["discrimination"] or 0),
    ):
        ref = entry["reference_mean"]
        dis = entry["distractor_mean"]
        disc = entry["discrimination"]
        lines.append(
            f"| `{name}` | {entry['weight']:.1f} | "
            f"{'n/a' if ref is None else f'{ref:.3f}'} | "
            f"{'n/a' if dis is None else f'{dis:.3f}'} | "
            f"{'n/a' if disc is None else f'{disc:+.3f}'} |"
        )
    lines += [
        "",
        "A component whose discrimination is ~0 is carrying weight in the objective",
        "while contributing nothing to the decision. That is a candidate for removal,",
        "not a neutral cost — every point of weight it holds is weight the terms that",
        "do discriminate are not getting.",
        "",
        "**Do not reweight straight off this column.** Several distractors were built",
        "to break one specific component, so that component's discrimination partly",
        "measures the distractor design rather than real model error — `scope_resolved`",
        "and `metadata_complete` score well largely because `metadata_stripped` exists",
        "to strip exactly those fields. The non-circular signal is a component that",
        "separates across SEVERAL distractor kinds; use `by_kind_mean` in the JSON to",
        "check that before moving any weight.",
        "",
    ]

    failures = [
        (row["case_id"], pair["kind"], pair["delta"])
        for row in report["cases"]
        for pair in row["pairs"]
        if not pair["reference_wins"] and pair["kind"] in HYGIENE_KINDS
    ]
    lines += ["", "## Hygiene failures (the reward did not separate these)", ""]
    if failures:
        lines += ["| Case | Distractor | Margin |", "| --- | --- | ---: |"]
        lines += [f"| `{c}` | `{k}` | {d:+.4f} |" for c, k, d in failures]
    else:
        lines.append("None — the proxy outranked every hygiene distractor.")

    if report["skipped"]:
        lines += ["", "## Skipped cases", ""]
        lines += [f"- `{row['case_id']}` — {row['reason']}" for row in report["skipped"]]

    lines += [
        "",
        "## How to read this",
        "",
        "Hygiene top-1 is the number that gates wiring best-of-N. It says how often",
        "the label-free reward would pick the real extraction out of a set that also",
        "contains a fragment, a page-dump, a paraphrase, a heading and a",
        "metadata-stripped variant. Below ~90% the reward is not safe to select on.",
        "",
        "It does NOT say best-of-N will raise the benchmark. That needs real sampled",
        "candidates from a live model, which costs API spend; this run is the",
        "pre-flight that decides whether that spend is justified.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--with-llm",
        metavar="PROVIDER",
        default=None,
        help="Run EligibilityVerifier's blind LLM arm (costs API calls), e.g. deepseek",
    )
    args = parser.parse_args()

    report = measure(args.with_llm)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    stem = "rlvr-measurement-llm" if args.with_llm else "rlvr-measurement"
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    history_path = args.out_dir / f"{stem}-history.jsonl"

    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "generated_at": report["generated_at"],
                    "commit": report["commit"],
                    "case_set_sha256": report["case_set_sha256"],
                    **report["summary"],
                }
            )
            + "\n"
        )

    if not args.quiet:
        print(render_markdown(report))
        print(f"\nWrote {json_path}\n      {md_path}\n      {history_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
