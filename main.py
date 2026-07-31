#!/usr/bin/env python3
"""SENTINEL — UN Digital Trade AI Mapper (judges' CLI entrypoint).

Round 1 contract (see requirements/README_template.md):

    python main.py --economy Singapore --pillar 6

Writes ``outputs/<Economy>_P<pillar>_<timestamp>.csv`` and ``.json`` with the
frozen 13-field schema. The same engine that powers the web app is reused here;
this file only wires the CLI to the submission adapter.

The LLM provider is selected from the environment (No Vendor Lock-in):

    RDTII_LLM_PROVIDER=ollama   # or openai, deepseek, mistral, gemini, claude
    OLLAMA_MODEL=qwen2.5:14b
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

load_dotenv(REPO_ROOT / ".env")


def _parse_pillars(token: str) -> list[int]:
    """Turn the --pillar argument into pillar ids.

    Round 2 spans all 12 pillars: accepts a single pillar ("7"), a comma list
    ("6,7,12"), "all" (1-12), or "round1" (the Round 1 scope, pillars 6-7).
    """

    token = token.strip().lower()
    if token == "all":
        return list(range(1, 13))
    if token == "round1":
        return [6, 7]
    try:
        pillars = sorted({int(part) for part in token.split(",") if part.strip()})
    except ValueError:
        pillars = []
    if pillars and all(1 <= p <= 12 for p in pillars):
        return pillars
    raise argparse.ArgumentTypeError(
        "--pillar must be 1-12, a comma list like 6,7, 'all', or 'round1'"
    )


def _pillar_label(pillars: list[int]) -> str:
    """Filename-safe label for one or more pillars (6, 7, or 6-7)."""

    return "-".join(str(p) for p in pillars)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="RDTII evidence discovery + indicator mapping (Pillars 6/7).",
    )
    parser.add_argument("--economy", required=True, help="Economy name or ISO-3 code, e.g. Singapore / SGP")
    parser.add_argument("--pillar", type=_parse_pillars, default=[6, 7], help="1-12, comma list (6,7), all, or round1")
    parser.add_argument("--pdf", default=None, help="Extract from this PDF path (bypasses the crawler)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Serve official texts from the local law library (no network crawl); "
             "recommended for reproducible / air-gapped runs",
    )
    parser.add_argument(
        "--from-corpus",
        action="store_true",
        help="Round-2 reproducible path: map the fetched official baseline corpus "
             "(data/round2_corpus) across all 12 pillars into evidence rows — the "
             "full Round-2 submission, no network. Covers the 7 Round-2 economies.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip the known-good seed pass and go straight to live discovery. "
             "By default a run seeds from the local library first, then falls "
             "back to discovery (seed-first hybrid).",
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Review mode: pure live discovery only; rejects fixtures, mock candidates, "
             "unverified/off-domain documents, and fails explicitly when no live evidence passes.",
    )
    parser.add_argument("--indicators", nargs="*", default=None, help="Restrict to specific indicators, e.g. 6.1 6.4")
    parser.add_argument("--output-dir", default="outputs", help="Directory for CSV/JSON output")
    parser.add_argument("--format", choices=("csv", "json", "both"), default="both")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty output files for research/debugging. By default, a run "
             "with no verified provisions fails without writing output.",
    )
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="Research mode: include ambiguous/flagged mappings in output. "
             "Formal submissions exclude them by default.",
    )
    parser.add_argument("--provider", default=None, help="Override RDTII_LLM_PROVIDER for this run")
    parser.add_argument("--limit", type=int, default=20, help="Max discovery candidates per pillar")
    parser.add_argument("--max-documents", type=int, default=None, help="Cap documents processed per pillar")
    parser.add_argument(
        "--registry-backend",
        choices=("file", "database"),
        default="file",
        help="Discovery source registry (default: checked-in file; database is for the full app)",
    )
    return parser.parse_args(argv)


def _formats(choice: str) -> tuple[str, ...]:
    return ("csv", "json") if choice == "both" else (choice,)


async def _run(args: argparse.Namespace) -> int:
    # The judge CLI is DB-free by default, while the full web app keeps the
    # registry module's database default. Set the CLI choice explicitly before
    # any deferred Discovery imports occur.
    os.environ["DISCOVERY_REGISTRY_BACKEND"] = args.registry_backend
    # Internal callers and tests may construct a partial Namespace instead of
    # going through parse_args(), so optional flags need a safe default.
    strict_live = getattr(args, "strict_live", False)
    if strict_live and (args.offline or args.pdf):
        raise ValueError("--strict-live cannot be combined with --offline or --pdf")

    from submission import (
        SubmissionRow,
        cap_rows_per_law,
        cap_rows_per_law_indicator,
        dedupe_submission_rows,
        reconcile_submission_tags,
        write_outputs,
    )
    from submission.pipeline import (
        discover_and_extract,
        run_corpus,
        run_library,
        run_pdf,
        run_seed_first,
    )
    from providers import pricing_basis
    from telemetry import cache_note
    from submission.schema import (
        economy_display_name,
        filter_formal_submission_rows,
        validate_submission_rows,
    )

    # RDTII_ANALYST=off is a legitimate cost switch for evaluation runs, but it
    # changes the content of an OFFICIAL submitted column ("Mapping Rationale"
    # falls back to the terse scorer sentence). A submission must never acquire
    # that quietly from a stale .env, so say it out loud at the top of the run.
    from agents.analyst import analyst_enabled

    if not analyst_enabled():
        print(
            "⚠ RDTII_ANALYST=off — the submitted 'Mapping Rationale' column will "
            "carry the terse deterministic scorer sentence, not the analyst's "
            "reasoning. Unset it (or pass --with-analyst on the evaluator) for a "
            "submission run.",
            file=sys.stderr,
        )

    # Provider preflight: the key-free default is Ollama at localhost:11434. If
    # it is not actually running, every extraction silently fails over and the
    # run crawls on connection errors (looked like a throughput wall for an
    # hour once). Warn loudly and up front so a judge running the default knows
    # to start Ollama or pass --provider deepseek, instead of watching it hang.
    _effective_provider = (args.provider or os.getenv("RDTII_LLM_PROVIDER") or "ollama").lower()
    if _effective_provider == "ollama":
        import socket

        _host = os.getenv("OLLAMA_HOST", "localhost")
        _port = int(os.getenv("OLLAMA_PORT", "11434"))
        try:
            with socket.create_connection((_host, _port), timeout=1.5):
                pass
        except OSError:
            print(
                f"⚠️  Provider 'ollama' is not reachable at {_host}:{_port}. "
                "Extractions will fail over on every call and the run will crawl.\n"
                "    Start Ollama, or re-run with a hosted provider, e.g. "
                "--provider deepseek (needs DEEPSEEK_API_KEY in .env).",
                file=sys.stderr, flush=True,
            )

    display = economy_display_name(args.economy)
    all_rows: list[SubmissionRow] = []
    combined_meta: dict = {
        "economy": display,
        "pillars": args.pillar,
        "retrieval_mode": (
            "strict_live"
            if strict_live
            else "live_discovery"
            if args.no_seed
            else "provided_pdf"
            if args.pdf
            else "seed"
            if args.offline
            else "seed_first"
        ),
        "evidence_counts": {"seed": 0, "live_discovered": 0, "fixture": 0},
        "runs": [],
    }

    # Live progress so a demo/judge sees the tool working during the
    # (silent-looking) discovery + LLM-extraction phase instead of a blank
    # screen. In an interactive terminal we draw two progress bars — overall
    # (pillars) and the current step (documents); otherwise we fall back to plain
    # narration lines. Everything goes to stderr, so it never pollutes the
    # CSV/JSON on stdout.
    from cli_progress import make_progress_ui
    ui = make_progress_ui(len(args.pillar), "pillars")

    def narrate(message: str, current: int | None = None, total: int | None = None) -> None:
        if ui is not None:
            ui.on_progress(message, current, total)
        else:
            print(f"   … {message}", file=sys.stderr, flush=True)

    for pillar in args.pillar:
        if ui is not None:
            ui.start_unit(f"Pillar {pillar}")
        else:
            print(f"\n▶ Pillar {pillar}: starting …", flush=True)
        if args.pdf:
            rows, meta = await run_pdf(
                args.economy, pillar, args.pdf,
                provider_name=args.provider, indicators=args.indicators,
            )
        elif getattr(args, "from_corpus", False):
            rows, meta = await run_corpus(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
                max_documents=args.max_documents,
                progress=narrate,
            )
        elif args.offline:
            rows, meta = await run_library(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
                progress=narrate,
            )
        elif strict_live or args.no_seed:
            rows, meta = await discover_and_extract(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
                limit=args.limit, max_documents=args.max_documents,
                strict_live=strict_live, progress=narrate,
            )
        else:
            rows, meta = await run_seed_first(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
                limit=args.limit, max_documents=args.max_documents,
                progress=narrate,
            )
        combined_meta["runs"].append(meta)
        for mode, count in meta.get("evidence_counts", {}).items():
            combined_meta["evidence_counts"][mode] = (
                combined_meta["evidence_counts"].get(mode, 0) + int(count)
            )
        all_rows.extend(rows)
        emit = ui.log if ui is not None else print
        emit(f"  Pillar {pillar}: {meta['provisions_mapped']} provisions mapped "
             f"({meta.get('documents_processed', 'n/a')} documents)")
        usage = meta.get("usage") or {}
        if usage.get("llm_calls"):
            emit(f"    Measured cost: {usage.get('llm_calls', 0)} LLM calls, "
                 f"{usage.get('input_tokens', 0):,} in / {usage.get('output_tokens', 0):,} out tokens, "
                 f"${usage.get('cost_usd', 0.0):.4f}{cache_note(usage)}")
        emit(f"    Retrieval mode: {meta.get('retrieval_mode', 'unknown')}")
        for warning in meta.get("warnings", []):
            emit(f"    ⚠ {warning}")
        if ui is not None:
            ui.unit_done()

    if ui is not None:
        ui.close()

    if strict_live and not all_rows:
        raise ValueError(
            "Strict live discovery failed: live discovery produced no formally "
            "submittable evidence. No output files were written."
        )

    counts = combined_meta["evidence_counts"]
    print(f"\nSeed evidence: {counts['seed']}")
    print(f"Live-discovered evidence: {counts['live_discovered']}")
    print(f"Fixture evidence: {counts['fixture']}")
    # Blind-verifier override rate: an independent checker model re-reads every
    # positive generic score from the quote alone (blind to the extractor's
    # score) and we keep the conservative minimum — so nothing ships unverified.
    try:
        from agents.score_checker import checker_stats

        bv = checker_stats()
        if bv.get("blind_checks"):
            print(
                f"Blind verifier: reviewed {bv['blind_checks']} positive scores, "
                f"overturned {bv['overturned']} ({bv['override_rate']:.0%}) → conservative min kept"
            )
    except Exception:  # noqa: BLE001
        pass
    # Cumulative cost ledger across every pillar this run — deployment cost is a
    # scored dimension (UN-readiness), so we report ours transparently.
    _calls = _in = _out = 0
    _cost = 0.0
    _totals: dict[str, int] = {"cache_hit_tokens": 0, "cache_miss_tokens": 0}
    for _m in combined_meta.get("runs", []):
        _u = _m.get("usage") or {}
        _calls += int(_u.get("llm_calls", 0) or 0)
        _in += int(_u.get("input_tokens", 0) or 0)
        _out += int(_u.get("output_tokens", 0) or 0)
        _cost += float(_u.get("cost_usd", 0.0) or 0.0)
        for _k in _totals:
            _totals[_k] += int(_u.get(_k, 0) or 0)
    if _calls:
        _totals["input_tokens"] = _in
        # "tokens measured" is a fact (the provider reported them); the dollar
        # figure is only as good as the configured rates, so the line says which
        # is which rather than calling the whole thing "measured cost".
        # FORMAT IS A CONTRACT: tools/cost_report.py parses this exact line
        # ("Total measured cost: N LLM calls, X in / Y out tokens, $Z (Economy)")
        # and README documents `main.py | tee run.log | cost_report.py`. Changing
        # the wording silently makes that workflow report 0 economies / $0 —
        # append after the economy paren, never rewrite what precedes it.
        print(
            f"Total measured cost: {_calls} LLM calls, {_in:,} in / {_out:,} out tokens, "
            f"${_cost:.4f} ({display}){cache_note(_totals)}"
        )
        # Own line, on stdout: cost_report.py's regex matches only the line
        # above, and README pipes stdout through `tee run.log` — a basis on
        # stderr would be missing from the artifact that gets quoted.
        print(pricing_basis(_effective_provider))
    # Discovery methods describe how a candidate was surfaced, not whether its
    # law is novel. Make the ESCAP inventory/library baseline authoritative at
    # the final submission boundary, after rows from every pillar/path have
    # been combined and immediately before CSV/JSON serialization.
    all_rows = reconcile_submission_tags(all_rows)
    # Collapse the one-URL-many-names hallucination before dedupe: every provision
    # from one document/URL is the SAME law, so force one canonical name (the
    # authoritative seed name if present) — the fabricated variants then merge away.
    from submission.schema import canonicalize_law_names_per_url

    all_rows = canonicalize_law_names_per_url(all_rows)
    all_rows = dedupe_submission_rows(all_rows)
    all_rows = cap_rows_per_law_indicator(all_rows)
    all_rows = cap_rows_per_law(all_rows)
    # First enforce the structural/source contract, then apply the precision-first
    # mapping gate.  Review-mode rows remain available only by explicit request.
    all_rows = validate_submission_rows(all_rows, allow_empty=True)
    all_rows = filter_formal_submission_rows(
        all_rows,
        include_review=getattr(args, "include_review", False),
    )
    if not all_rows and not getattr(args, "allow_empty", False):
        raise ValueError(
            "No formally submittable mappings remained after eligibility and "
            "human-review filtering. Re-run with --include-review for research "
            "output or --allow-empty to write an empty result."
        )

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    written = write_outputs(
        all_rows,
        economy=display,
        pillar=_pillar_label(args.pillar),
        timestamp=timestamp,
        output_dir=args.output_dir,
        formats=_formats(args.format),
        meta=combined_meta,
    )

    print(f"\n✅ {len(all_rows)} provisions written for {display} (Pillar {_pillar_label(args.pillar)}):")
    for fmt, path in written.items():
        print(f"   {fmt.upper()}: {path}")

    _report_new_laws(all_rows, display)
    return 0


def _report_new_laws(rows, economy_display: str) -> None:
    """Surface NEW laws (found beyond the KNOWN baseline) inline after a run.

    Every row is already tagged NEW/KNOWN by reconcile_submission_tags; this just
    makes the independent finds visible instead of buried in the CSV, grouping a
    law's title variants and its indicators. Marked as a lead for legal review.
    """

    from submission.novelty import normalize_law_name

    grouped: dict[str, dict] = {}
    for r in rows:
        if (getattr(r, "discovery_tag", "") or "").upper() != "NEW":
            continue
        law = (r.law_name or "").strip()
        if not law:
            continue
        key = normalize_law_name(law)
        g = grouped.setdefault(key, {"law": law, "indicators": set(), "url": r.source_url})
        g["indicators"].add(r.indicator_id)
        if len(law) > len(g["law"]):  # keep the fullest title variant
            g["law"] = law

    if not grouped:
        return
    print(f"\n🆕 {len(grouped)} law(s) discovered BEYOND the known baseline for "
          f"{economy_display} — independent NEW finds (a lead for legal review):")
    for g in grouped.values():
        inds = ", ".join(sorted(g["indicators"]))
        print(f"   • {g['law']}  [{inds}]")
        if g.get("url"):
            print(f"       {g['url']}")
    print("   (Verify each against the official source before relying on it.)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"SENTINEL — mapping {args.economy}, Pillar {_pillar_label(args.pillar)} …")
    try:
        return asyncio.run(_run(args))
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        # Judges stress-test with bad inputs — a clean message beats a traceback.
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
