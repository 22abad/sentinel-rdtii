from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import fitz
import numpy as np
import pytest

from benchmarking.cer import calculate_cer, normalize_ocr_text, summarize_cer
from benchmarking.models import CerPageResult, OcrBenchmarkCase, OcrNormalization
from benchmarking.ocr_runner import load_ocr_cases, run_ocr_benchmark
from benchmarking.pipeline_runner import run_document_benchmark
from pdf_reader import _read_pdf_via_sidecar
from pdf_reader.ocr_service import tesseract_extractor
from pdf_reader.ocr_service.openai_fallback import ocr_vision_with_usage
from schemas import ExtractionResponse, RunUsageSummary
from services.document_fetch import CrawlQuality, DocumentText


REPO_ROOT = Path(__file__).resolve().parents[2]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cer_counts_substitutions_deletions_and_insertions():
    metrics = calculate_cer("ABCDE", "AXCYEZ")

    assert metrics["substitutions"] == 2
    assert metrics["deletions"] == 0
    assert metrics["insertions"] == 1
    assert metrics["edit_distance"] == 3
    assert metrics["cer"] == pytest.approx(0.6)


def test_normalization_preserves_punctuation_and_numbers():
    policy = OcrNormalization()
    normalized = normalize_ocr_text("Section 7-\n3:  five\r\nyears.", policy)

    assert normalized == "Section 73: five years."

    without_page_number = normalize_ocr_text(
        "Section 7 remains.\nPage 12\nFive years.",
        OcrNormalization(remove_page_numbers=True),
    )
    assert without_page_number == "Section 7 remains. Five years."


def test_macro_and_micro_cer_are_reported_separately():
    first = CerPageResult(
        case_id="first", document_id="doc-one", page_number=1, language="eng",
        requested_path="pymupdf", actual_path="pymupdf", fallback_used=False,
        substitutions=1, deletions=0, insertions=0, edit_distance=1,
        reference_characters=10, candidate_characters=10, cer=0.1,
        runtime_seconds=0.01,
    )
    second = first.model_copy(update={
        "case_id": "second",
        "reference_characters": 100,
        "candidate_characters": 100,
        "edit_distance": 20,
        "substitutions": 20,
        "cer": 0.2,
    })

    summary = summarize_cer([first, second])
    assert summary["macro_cer"] == pytest.approx(0.15)
    assert summary["micro_cer"] == pytest.approx(21 / 110)
    assert summary["pages_above_target"] == 2


def test_approved_case_requires_human_corrected_reference():
    payload = {
        "case_id": "test-page",
        "document_id": "test-document",
        "page_number": 1,
        "source_file_path": "source.pdf",
        "source_file_sha256": "0" * 64,
        "reference_text_path": "reference.txt",
        "reference_text_sha256": "1" * 64,
        "language": "eng",
        "extraction_path": "pymupdf",
        "review": {
            "status": "approved",
            "reference_origin": "machine_draft",
            "reviewed_at": "2026-07-11",
        },
    }

    with pytest.raises(ValueError, match="human_corrected"):
        OcrBenchmarkCase.model_validate(payload)


def test_checked_in_ocr_candidates_are_pending_machine_drafts():
    cases = load_ocr_cases(REPO_ROOT / "evaluation/ocr/cases.jsonl")

    assert len(cases) == 3
    assert {case.extraction_path for case in cases} == {"pymupdf", "tesseract"}
    assert all(case.review.status == "pending" for case in cases)
    assert all(case.review.reference_origin == "machine_draft" for case in cases)


def test_runner_writes_json_and_markdown_from_approved_page(tmp_path):
    source_root = tmp_path / "sources"
    source_root.mkdir()
    pdf_path = source_root / "source.pdf"
    reference_path = tmp_path / "reference.txt"
    cases_path = tmp_path / "cases.jsonl"
    output_path = tmp_path / "report.json"

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Section 7 requires records for five years.")
    document.save(pdf_path)
    document.close()
    reference_path.write_text(
        "Section 7 requires records for five years.\n",
        encoding="utf-8",
    )
    case = {
        "case_id": "approved-test-page",
        "document_id": "test-document",
        "page_number": 1,
        "source_file_path": "source.pdf",
        "source_file_sha256": _hash(pdf_path),
        "reference_text_path": str(reference_path.relative_to(tmp_path)),
        "reference_text_sha256": _hash(reference_path),
        "language": "eng",
        "extraction_path": "pymupdf",
        "review": {
            "status": "approved",
            "reference_origin": "human_corrected",
            "reviewer_role": "Test reviewer",
            "reviewed_at": "2026-07-11",
        },
    }
    cases_path.write_text(json.dumps(case) + "\n", encoding="utf-8")

    report = run_ocr_benchmark(
        repo_root=tmp_path,
        source_root=source_root,
        cases_path=cases_path,
        output_path=output_path,
    )

    assert report["summary"]["micro_cer"] == 0.0
    assert report["summary"]["vision_calls"] == 0
    assert report["summary"]["vision_cost_usd"] == 0.0
    assert report["pages"][0]["actual_path"] == "pymupdf"
    assert output_path.exists()
    assert "Macro CER: 0.00%" in output_path.with_suffix(".md").read_text()


def test_vision_ocr_records_actual_returned_tokens_and_configured_price(monkeypatch):
    usage = types.SimpleNamespace(prompt_tokens=1_000, completion_tokens=200)
    response = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="OCR text"))],
        usage=usage,
    )

    class FakeCompletions:
        def create(self, **_kwargs):
            return response

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions(),
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_VISION_INPUT_USD_PER_MTOK", "2.5")
    monkeypatch.setenv("OPENAI_VISION_OUTPUT_USD_PER_MTOK", "10")
    monkeypatch.setenv("OPENAI_VISION_PRICING_DATE", "2026-07-11")

    result = ocr_vision_with_usage(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result.input_tokens == 1_000
    assert result.output_tokens == 200
    assert result.cost_usd == pytest.approx(0.0045)
    assert result.pricing_date == "2026-07-11"
    assert result.status == "success"


@pytest.mark.anyio
async def test_document_benchmark_separates_ocr_and_mapping_cost(tmp_path, monkeypatch):
    fetched = DocumentText(
        source_url="https://example.gov/law.pdf",
        text="Section 7 requires records for five years. " * 30,
        content_type="pdf",
        pdf_metadata={
            "total_pages": 50,
            "source_file_sha256": "a" * 64,
            "vision_usage": [{
                "status": "success",
                "input_tokens": 500,
                "output_tokens": 100,
                "cost_usd": 0.002,
            }],
        },
        quality=CrawlQuality(status="good", should_extract=True),
        timing_seconds={"fetch": 1.25, "pdf_processing": 4.5},
    )

    async def fake_fetch(_url):
        return fetched

    async def fake_extract(_text, _provider, pdf_metadata=None):
        assert pdf_metadata["total_pages"] == 50
        return ExtractionResponse(
            provider="fake",
            usage=RunUsageSummary(
                run_id="test-run",
                llm_calls=2,
                successful_calls=2,
                input_tokens=1_000,
                output_tokens=200,
                known_input_tokens=1_000,
                known_output_tokens=200,
                cost_usd=0.003,
                known_cost_usd=0.003,
            ),
        )

    provider = types.SimpleNamespace(model_name="test-model")
    monkeypatch.setattr("benchmarking.pipeline_runner.fetch_document_text", fake_fetch)
    monkeypatch.setattr("benchmarking.pipeline_runner.run_extraction", fake_extract)
    monkeypatch.setattr(
        "benchmarking.pipeline_runner.get_provider",
        lambda *_args: provider,
    )
    output_path = tmp_path / "document-benchmark.json"

    report = await run_document_benchmark(
        repo_root=REPO_ROOT,
        source_url=fetched.source_url,
        document_id="fifty-page-law",
        provider_name="deepseek",
        model_name="test-model",
        output_path=output_path,
        command="benchmark test",
    )

    assert report["document"]["pages"] == 50
    assert report["cost_usd"]["llm"] == 0.003
    assert report["cost_usd"]["ocr"] == 0.002
    assert report["cost_usd"]["total"] == 0.005
    assert report["timing_seconds"]["fetch"] == 1.25
    assert output_path.with_suffix(".md").exists()


@pytest.mark.parametrize("function_name", ["extract_text_ocr", "extract_sections_ocr"])
def test_public_ocr_helpers_close_pdf_on_failure(monkeypatch, function_name):
    class FakeDocument:
        closed = False

        def __len__(self):
            return 1

        def close(self):
            self.closed = True

    document = FakeDocument()
    monkeypatch.setattr(fitz, "open", lambda *_args, **_kwargs: document)
    monkeypatch.setattr(
        tesseract_extractor,
        "_render_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("render failed")),
    )

    with pytest.raises(RuntimeError, match="render failed"):
        getattr(tesseract_extractor, function_name)("source.pdf")
    assert document.closed is True


def test_sidecar_vision_usage_and_page_durations_remain_explicitly_unknown(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"test-pdf")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "text": "Extracted legal text",
                "cache_hit": False,
                "ocr_provider": "openai_vision",
            }

    monkeypatch.setenv("EXTRACT_SIDECAR_URL", "https://sidecar.example")
    monkeypatch.setenv("SIDECAR_API_KEY", "test-key")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr("pdf_reader._inspect_pdf_for_sidecar", lambda _path: {
        "ocr_pages": 2,
        "text_pages": 0,
        "ocr_ratio": 1.0,
        "known_mean_conf": 0.0,
        "total_pages": 2,
        "page_confs": [0.0, 0.0],
    })

    result = _read_pdf_via_sidecar(str(pdf_path))

    assert result is not None
    assert result.page_durations_seconds == [None, None]
    assert result.vision_usage[0]["status"] == "unavailable"
    assert result.vision_usage[0]["call_count"] is None
    assert result.vision_usage[0]["cost_usd"] is None


def test_vision_ocr_does_not_swallow_memory_error(monkeypatch):
    class FailingOpenAI:
        def __init__(self, **_kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **_call_kwargs: (_ for _ in ()).throw(MemoryError()),
                ),
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FailingOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(MemoryError):
        ocr_vision_with_usage(np.zeros((10, 10, 3), dtype=np.uint8))
