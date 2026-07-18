#!/usr/bin/env python3
"""Convert legal-review exports into pending golden positive/hard-negative cases.

Only decisions that can be grounded in an existing golden document and an exact
reference-text quote are emitted.  Rejections create a negative for the engine
indicator; reassignments create that negative plus positives for reviewer-chosen
indicators.  Output remains ``pending`` until the substantive lead approves it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATION = REPO_ROOT / "evaluation"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").casefold()).strip("-")[:70]


def _indicator(value: str) -> str:
    value = (value or "").strip().upper()
    match = re.fullmatch(r"P(\d+)-I(\d+(?:\.\d+)*)", value)
    return f"{match.group(1)}.{match.group(2)}" if match else value.lower()


def _load_documents() -> list[dict]:
    return [
        json.loads(line) for line in (EVALUATION / "golden/documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _match_document(decision: dict, documents: list[dict]) -> dict | None:
    url = str(decision.get("official_url") or decision.get("url") or decision.get("source_url") or "").strip()
    law = str(decision.get("law_name") or decision.get("source_legislation") or "")
    for document in documents:
        if url and url == document.get("official_source_url"):
            return document
    law_key = _norm(law)
    matches = [document for document in documents if law_key and (
        law_key in _norm(document.get("source_legislation", ""))
        or _norm(document.get("source_legislation", "")) in law_key
    )]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        quote = str(
            decision.get("verbatim_quote") or decision.get("verbatim_snippet")
            or decision.get("quote") or ""
        ).strip()
        quote_matches = [document for document in matches if quote and quote in _reference_text(document)]
        if len(quote_matches) == 1:
            return quote_matches[0]
    return None


def _reference_text(document: dict) -> str:
    return (REPO_ROOT / document["reference_text_path"]).read_text(encoding="utf-8")


def _verdict_kind(value: str) -> str:
    value = (value or "").strip().casefold()
    if value in {"valid", "ok", "correct", "approve", "confirmed"}:
        return "valid"
    if value in {"reject", "rejected", "wrong", "not valid evidence"}:
        return "reject"
    if value in {"reassign", "reassigned"}:
        return "reassign"
    return "skip"


def convert_document(export: dict, documents: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    documents = documents or _load_documents()
    cases: list[dict] = []
    warnings: list[str] = []
    reviewer = str(export.get("reviewer") or "Legal reviewer")

    for index, decision in enumerate(export.get("decisions", []), start=1):
        kind = _verdict_kind(str(decision.get("verdict") or ""))
        if kind == "skip":
            continue
        document = _match_document(decision, documents)
        if document is None:
            warnings.append(f"decision {index}: no unique existing golden document match")
            continue
        quote = str(
            decision.get("verbatim_quote") or decision.get("verbatim_snippet")
            or decision.get("quote") or ""
        ).strip()
        if not quote or quote not in _reference_text(document):
            warnings.append(f"decision {index}: quote is absent or not exact in reference text")
            continue

        engine = _indicator(str(
            decision.get("engine_indicator") or decision.get("indicator")
            or decision.get("our_suggested") or ""
        ))
        reviewer_values = decision.get("reviewer_indicators") or decision.get("correct_indicators") or []
        reviewed = [_indicator(str(value)) for value in reviewer_values if _indicator(str(value))]
        labels: list[tuple[str, bool]] = []
        if kind == "valid" and engine:
            labels.append((engine, True))
        elif kind == "reject" and engine:
            labels.append((engine, False))
        elif kind == "reassign":
            if engine:
                labels.append((engine, False))
            labels.extend((indicator, True) for indicator in reviewed if indicator != engine)

        score_raw = decision.get("reviewer_score", 0.0)
        try:
            reviewed_score = float(score_raw or 0.0)
        except (TypeError, ValueError):
            reviewed_score = 0.0
        for indicator, should_map in labels:
            case_id = _slug(
                f"review-{document['document_id']}-{indicator}-{'positive' if should_map else 'negative'}-{index}"
            )
            cases.append({
                "case_id": case_id,
                "country_code": document["country_code"],
                "document_id": document["document_id"],
                "source_legislation": document["source_legislation"],
                "official_source_url": document["official_source_url"],
                "source_status": document["source_status"],
                "indicator_id": indicator,
                "should_map": should_map,
                "article_clause": str(decision.get("article") or decision.get("article_clause") or ""),
                "verbatim_quote": quote,
                "expected_scope": str(decision.get("scope") or "unknown").lower(),
                "coverage_detail": str(decision.get("coverage") or "Legal-review feedback import"),
                "expected_raw_score": reviewed_score if should_map else 0.0,
                "expected_cat_score": reviewed_score if should_map else 0.0,
                "legal_rationale": str(
                    decision.get("note") or
                    f"Imported from {reviewer}: {kind} decision for indicator {indicator}."
                ),
                "review": {
                    "status": "pending",
                    "reviewer_role": "Substantive Lead",
                    "reviewed_at": None,
                    "framework_version": "RDTII 2.1",
                    "notes": f"Imported from review export by {reviewer}; requires golden-set approval.",
                },
            })
    return cases, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="Legal-review JSON export(s)")
    parser.add_argument("--output", required=True, help="Pending golden JSONL output path")
    args = parser.parse_args(argv)

    all_cases: list[dict] = []
    warnings: list[str] = []
    for filename in args.files:
        export = json.loads(Path(filename).read_text(encoding="utf-8"))
        cases, file_warnings = convert_document(export)
        all_cases.extend(cases)
        warnings.extend(f"{filename}: {warning}" for warning in file_warnings)
    output = Path(args.output)
    output.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in all_cases) + ("\n" if all_cases else ""),
        encoding="utf-8",
    )
    print(f"wrote {len(all_cases)} pending golden case(s) to {output}")
    for warning in warnings:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
