"""Render OCR benchmark JSON payloads as bounded Markdown evidence."""

from __future__ import annotations


def render_ocr_markdown(report: dict) -> str:
    metadata = report["metadata"]
    summary = report["summary"]
    lines = [
        "# OCR CER benchmark",
        "",
        f"- Commit: `{metadata['commit_sha']}`",
        f"- Generated: `{metadata['generated_at']}`",
        f"- Cases evaluated: {summary['page_count']}",
        f"- Macro CER: {_percent(summary['macro_cer'])}",
        f"- Micro CER: {_percent(summary['micro_cer'])}",
        f"- Pages above {_percent(summary['target_cer'])}: {summary['pages_above_target']}",
        f"- OCR paths (PyMuPDF/Tesseract/Vision): {summary['pymupdf_pages']}/"
        f"{summary['tesseract_pages']}/{summary['vision_pages']}",
        f"- Vision tokens (input/output): {_display(summary['vision_input_tokens'])}/"
        f"{_display(summary['vision_output_tokens'])}",
        f"- Known Vision token subtotal (input/output): "
        f"{_display(summary['known_vision_input_tokens'])}/"
        f"{_display(summary['known_vision_output_tokens'])}",
        f"- Vision calls with unavailable usage: "
        f"{summary['vision_calls_with_unknown_usage']}",
        f"- Vision API cost: {_money(summary['vision_cost_usd'])}",
        "",
    ]
    if metadata["include_pending"]:
        lines.extend([
            "> Development-only: pending or machine-draft references were included. "
            "These CER values are not approved submission evidence.",
            "",
        ])
    lines.extend([
        "## Pages",
        "",
        "| Case | Requested / actual path | CER | Edits (S/D/I) | Runtime |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for page in report["pages"]:
        lines.append(
            f"| `{page['case_id']}` | {page['requested_path']} / {page['actual_path']} | "
            f"{_percent(page['cer'])} | {page['substitutions']}/{page['deletions']}/"
            f"{page['insertions']} | {page['runtime_seconds']:.3f}s |"
        )
    lines.extend([
        "",
        "## Normalization",
        "",
        "Unicode composition, line endings, whitespace, and line-break hyphenation "
        "are controlled per case and serialized in the JSON report. Headers/footers "
        "are not automatically removed. Punctuation and legally meaningful numbers "
        "are preserved.",
        "",
        "## Cost boundary",
        "",
        "PyMuPDF and Tesseract use no LLM tokens. Vision usage is reported per page "
        "when the provider returns it; unavailable usage is never recorded as zero.",
        "",
    ])
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value * 100:.2f}%"


def _display(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value:,}"


def _money(value: float | None) -> str:
    return "Unavailable" if value is None else f"${value:.6f}"
