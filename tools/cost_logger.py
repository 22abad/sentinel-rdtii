#!/usr/bin/env python3
"""Measure the real per-document cost of a SENTINEL run.

Hackathon sustainability rubric — judges require measured costs, not estimates:

    python tools/cost_logger.py --pdf data/benchmark/benchmark_50pages.pdf \
        --economy Singapore --pillar 6

Reads the PDF, runs the same extraction pipeline the CLI uses, and records
measured token counts, processing time, and cost to ``logs/cost_report.json``.
The LLM provider comes from the environment (RDTII_LLM_PROVIDER); use
``RDTII_LLM_PROVIDER=ollama`` for the $0-API open-weight measurement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

load_dotenv(REPO_ROOT / ".env")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cost_logger.py", description=__doc__)
    parser.add_argument("--pdf", required=True, help="Benchmark document to measure")
    parser.add_argument("--economy", default="Singapore", help="Economy label for the report")
    parser.add_argument("--pillar", default="6", help="Pillar label for the report")
    parser.add_argument("--provider", default=None, help="Override RDTII_LLM_PROVIDER")
    parser.add_argument("--output", default=str(REPO_ROOT / "logs" / "cost_report.json"))
    parser.add_argument("--today", default=None, help="Override measured_on date (YYYY-MM-DD)")
    return parser.parse_args(argv)


async def _measure(args: argparse.Namespace) -> dict:
    from pdf_reader import read_pdf
    from providers import get_default_provider, get_provider
    from services.extraction import run_extraction
    from submission.cost import build_cost_report

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    provider = get_provider(args.provider) if args.provider else get_default_provider()
    model = getattr(provider, "model_name", getattr(provider, "name", "unknown"))

    print(f"Reading {pdf_path.name} …")
    pdf = read_pdf(str(pdf_path), source_url=str(pdf_path))
    text = "\n".join(pdf.pages)
    ocr_engine = "tesseract" if pdf.ocr_pages else "none"

    print(f"Running extraction on {pdf.total_pages} pages via {model} …")
    t0 = time.time()
    result = await run_extraction(text, provider)
    elapsed = time.time() - t0

    usage = result.usage
    input_tokens = usage.known_input_tokens if usage else 0
    output_tokens = usage.known_output_tokens if usage else 0
    llm_calls = usage.llm_calls if usage else 0
    reported_cost = usage.known_cost_usd if (usage and usage.known_cost_usd) else None

    return build_cost_report(
        document=pdf_path.name,
        measured_on=args.today or date.today().isoformat(),
        model=str(model),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        llm_calls=llm_calls,
        processing_time_seconds=elapsed,
        provider_reported_cost_usd=reported_cost,
        ocr_engine=ocr_engine,
        ocr_pages=pdf.ocr_pages,
        ocr_cost_usd=0.0,  # Tesseract is local/self-hosted.
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = asyncio.run(_measure(args))
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    llm = report["llm"]
    print("\n─── Measured cost report ─────────────────────────────")
    print(f"  Document:      {report['document']}")
    print(f"  Model:         {llm['model']}")
    print(f"  Tokens:        {llm['input_tokens']:,} in / {llm['output_tokens']:,} out ({llm['llm_calls']} calls)")
    print(f"  LLM cost:      {llm['cost_usd']}  ({llm['cost_basis']})")
    print(f"  Total cost:    ${report['total_cost_usd']} per document")
    print(f"  Wall-clock:    {report['processing_time_seconds']}s")
    print(f"  Written to:    {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
