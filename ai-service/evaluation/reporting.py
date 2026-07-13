"""Render a bounded human-readable summary from the JSON report payload."""

from __future__ import annotations


def render_markdown(report: dict) -> str:
    metadata = report["metadata"]
    dataset = report["dataset"]
    lines = [
        "# RDTII golden-set evaluation",
        "",
        f"- Mode: `{metadata['mode']}`",
        f"- Commit: `{metadata['commit_sha']}`",
        f"- Generated: `{metadata['generated_at']}` ({metadata['timezone']})",
        f"- Provider/model: `{metadata['provider']}` / `{metadata.get('model') or 'n/a'}`",
        f"- Case-set SHA-256: `{metadata['case_set_sha256']}`",
        f"- Cases evaluated: {dataset['cases_evaluated']} across {dataset['documents_evaluated']} documents",
        "",
    ]
    if metadata["include_pending"]:
        lines.extend([
            "> Development-only report: pending legal labels were included. "
            "Do not use these metrics as approved submission claims.",
            "",
        ])

    discovery = report.get("discovery")
    if discovery is not None:
        lines.extend([
            "## Document discovery",
            "",
            f"- Document recall: {_percent(discovery['document_recall'])}",
            f"- Official source rate: {_percent(discovery['official_source_rate'])}",
            f"- Valid URL rate: {_percent(discovery['valid_url_rate'])}",
            f"- Fixture/fallback used: {'yes' if discovery['fallback_used'] else 'no'}",
            "",
        ])

    evaluation = report.get("mapping_evaluation")
    if evaluation is not None:
        aggregate = evaluation["aggregate"]
        lines.extend([
            "## Mapping and citation metrics",
            "",
            "| Metric | Result |",
            "| --- | ---: |",
            f"| Mapping precision | {_percent(aggregate['mapping_precision'])} |",
            f"| Mapping recall | {_percent(aggregate['mapping_recall'])} |",
            f"| Mapping F1 | {_percent(aggregate['mapping_f1'])} |",
            f"| Citation exact-match | {_percent(aggregate['citation_exact_match_rate'])} |",
            f"| Article citation accuracy | {_percent(aggregate['article_citation_accuracy'])} |",
            f"| Raw score accuracy | {_percent(aggregate['raw_score_accuracy'])} |",
            f"| Category score accuracy | {_percent(aggregate['category_score_accuracy'])} |",
            f"| Scope accuracy | {_percent(aggregate['scope_accuracy'])} |",
            "",
            "## Case-level failures",
            "",
            f"- False positives: {len(evaluation['false_positives'])}",
            f"- False negatives: {len(evaluation['false_negatives'])}",
            f"- Explicit negative cases hit: {len(evaluation['negative_case_hits'])}",
            f"- Citation offset failures: {len(evaluation['citation_failures'])}",
            "",
        ])
        lines.extend(_dimension_table("Per-country metrics", evaluation["per_country"]))
        lines.extend(_dimension_table("Per-indicator metrics", evaluation["per_indicator"]))
        for failure in evaluation["false_negatives"]:
            lines.append(f"- FN `{failure['case_id']}`")
        for failure in evaluation["false_positives"]:
            lines.append(f"- FP `{failure['prediction_id']}` ({failure['indicator_id']})")
        for failure in evaluation["citation_failures"]:
            lines.append(
                f"- Citation `{failure['prediction_id']}`: {failure['reason']}"
            )
        if (
            evaluation["false_negatives"]
            or evaluation["false_positives"]
            or evaluation["citation_failures"]
        ):
            lines.append("")

    excluded_predictions = dataset.get("excluded_predictions", [])
    if excluded_predictions:
        lines.extend(["## Predictions excluded from scoring", ""])
        for prediction in excluded_predictions:
            case_ids = ", ".join(prediction["matched_excluded_case_ids"])
            lines.append(
                f"- `{prediction['prediction_id']}` matched excluded case(s): {case_ids}"
            )
        lines.append("")

    if report["source_failures"]:
        lines.extend(["## Source failures", ""])
        for failure in report["source_failures"]:
            lines.append(
                f"- `{failure['document_id']}` [{failure['stage']}]: {failure['reason']}"
            )
        lines.append("")

    lines.extend([
        "## Measured usage and cost",
        "",
        f"- Vision OCR calls: {_display(report.get('ocr_usage', {}).get('vision_calls'))}",
        f"- Vision calls with unavailable usage: "
        f"{report.get('ocr_usage', {}).get('calls_with_unknown_usage', 0)}",
        f"- Known Vision token subtotal: "
        f"{_display(report.get('ocr_usage', {}).get('known_input_tokens'))} input / "
        f"{_display(report.get('ocr_usage', {}).get('known_output_tokens'))} output",
        f"- Mapping LLM API cost: {_money(report.get('cost_usd', {}).get('llm'))}",
        f"- Vision OCR API cost: {_money(report.get('cost_usd', {}).get('ocr'))}",
        f"- Search cost: {_money(report.get('cost_usd', {}).get('search'))}",
        f"- Known LLM + OCR subtotal: {_money(report.get('cost_usd', {}).get('known_llm_ocr_subtotal'))}",
        f"- Total API cost: {_money(report.get('cost_usd', {}).get('total'))}",
        "",
        "## Stage timing",
        "",
        f"- Discovery: {report.get('timing_seconds', {}).get('discovery', 0.0):.3f} seconds",
        f"- Fetch: {report.get('timing_seconds', {}).get('fetch', 0.0):.3f} seconds",
        f"- PDF processing/OCR: {report.get('timing_seconds', {}).get('pdf_processing', 0.0):.3f} seconds",
        f"- Mapping: {report.get('timing_seconds', {}).get('mapping', 0.0):.3f} seconds",
        "",
        "## Reproducibility",
        "",
        f"- Runtime: {report['runtime_seconds']:.3f} seconds",
        f"- Document-set SHA-256: `{metadata['document_set_sha256']}`",
        f"- Command: `{metadata['command']}`",
        "- Machine-readable details are stored in the sibling JSON report.",
        "",
    ])
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value * 100:.2f}%"


def _money(value: float | None) -> str:
    return "Unavailable" if value is None else f"${value:.6f}"


def _display(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value:,}"


def _dimension_table(title: str, values: dict[str, dict]) -> list[str]:
    lines = [f"### {title}", "", "| Group | Precision | Recall | F1 |", "| --- | ---: | ---: | ---: |"]
    for group, metrics in values.items():
        lines.append(
            f"| {group} | {_percent(metrics['mapping_precision'])} | "
            f"{_percent(metrics['mapping_recall'])} | {_percent(metrics['mapping_f1'])} |"
        )
    lines.append("")
    return lines
