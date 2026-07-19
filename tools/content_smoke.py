#!/usr/bin/env python3
"""Content-truth smoke pack — the eyeball checks, automated.

Every case here is a CONTENT expectation a human once had to spot by eye in
the workbench ("the Cyber Security Act must map to 7.2 under its own name",
"the Service Tax quote must be the full limb, not a 3-word fragment"). Each
runs through ``services.extraction.run_extraction`` — the SAME entry point the
frontend /api/extract uses — so what this pack certifies is what the UI shows.

Run it BEFORE opening the frontend (a few minutes, ~$0.05 DeepSeek):

    RDTII_LLM_PROVIDER=deepseek .venv-eval/bin/python tools/content_smoke.py

Add a case for every new eyeball finding: the pack only ever grows stricter.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ai-service"))


@dataclass
class Case:
    name: str
    text_path: str                       # relative to repo root
    expect_indicator: str | None         # indicator that MUST appear (None = none may)
    forbid_law_substr: list[str] = field(default_factory=list)
    expect_law_substr: str | None = None
    expect_quote_substr: str | None = None
    min_quote_len: int = 0
    forbid_flag_substr: list[str] = field(default_factory=list)
    target_indicators: list[str] | None = None   # None = UI parity (classifier)


CASES = [
    Case(
        # Eyeball find 2026-07-19: pasted into the workbench, the dedicated
        # cybersecurity act produced NO 7.2 and one row named after the act
        # its provisions talk about, flagged with a bogus objectives reason.
        name="AUS Cyber Security Act 2024 → 7.2 under its own name (UI parity)",
        text_path="data/law_library/text/aus-cyber-security-act-2024-no-98-2024.txt",
        expect_indicator="7.2",
        expect_law_substr="Cyber Security Act",
        forbid_law_substr=["Privacy Act 1988"],
        forbid_flag_substr=["extent"],
    ),
    Case(
        # Eyeball find 2026-07-19 (morning): the 6.2 mapping died silently as
        # a heading, then as a <45-char fragment. Must come back as the full
        # provision limb.
        name="MYS Service Tax s24 → 6.2 full limb quote",
        text_path="data/law_library/text/mys-service-tax-act-2018-act-807-s24.txt",
        expect_indicator="6.2",
        expect_quote_substr="kept in Malaysia",
        min_quote_len=45,
        target_indicators=["6.2"],
    ),
    Case(
        # Honest-zero guard: the ITA s82 excerpt is retention-only — a 6.2 row
        # from it would be over-extraction (the official key cites it, but the
        # excerpt does not literally state local storage).
        name="MYS ITA s82 → honestly NO 6.2",
        text_path="data/law_library/text/mys-income-tax-act-1967-act-53-s82.txt",
        expect_indicator=None,
        target_indicators=["6.2"],
    ),
]


def check(case: Case, mappings) -> list[str]:
    errs: list[str] = []
    if case.expect_indicator is None:
        if mappings:
            errs.append(f"expected NO mappings, got {[m.indicator for m in mappings]}")
        return errs
    hits = [m for m in mappings if m.indicator == case.expect_indicator]
    if not hits:
        errs.append(
            f"indicator {case.expect_indicator} missing "
            f"(got {[m.indicator for m in mappings] or 'nothing'})"
        )
        return errs
    m = hits[0]
    law = m.source_legislation or ""
    quote = m.verbatim_quote or ""
    flags = " ; ".join(getattr(m, "flag_reasons", None) or [])
    if case.expect_law_substr and case.expect_law_substr.lower() not in law.lower():
        errs.append(f"law name {law!r} lacks {case.expect_law_substr!r}")
    for bad in case.forbid_law_substr:
        if bad.lower() in law.lower():
            errs.append(f"law name {law!r} contains forbidden {bad!r}")
    if case.expect_quote_substr and case.expect_quote_substr.lower() not in quote.lower():
        errs.append(f"quote lacks {case.expect_quote_substr!r}: {quote[:60]!r}")
    if len(quote) < case.min_quote_len:
        errs.append(f"quote too short ({len(quote)} < {case.min_quote_len}): {quote[:60]!r}")
    for bad in case.forbid_flag_substr:
        if re.search(rf"\b{re.escape(bad)}\b", flags, re.IGNORECASE):
            errs.append(f"flag reasons contain forbidden {bad!r}: {flags[:100]!r}")
    return errs


async def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    os.environ.setdefault("RDTII_LLM_PROVIDER", "deepseek")
    from providers import get_provider
    from services.extraction import run_extraction

    provider = get_provider(os.environ["RDTII_LLM_PROVIDER"])
    failures = 0
    for case in CASES:
        text = (REPO / case.text_path).read_text()
        result = await run_extraction(
            text, provider, target_indicators=case.target_indicators
        )
        errs = check(case, result.mappings)
        status = "PASS ✅" if not errs else "FAIL ❌"
        print(f"[{status}] {case.name}")
        for e in errs:
            print(f"    - {e}")
        failures += bool(errs)
    print(f"\n{len(CASES) - failures}/{len(CASES)} content checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
