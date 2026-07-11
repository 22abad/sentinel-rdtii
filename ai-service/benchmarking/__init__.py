"""Measured OCR, runtime, and cost benchmarking utilities."""

from .cer import calculate_cer, normalize_ocr_text, summarize_cer

__all__ = ["calculate_cer", "normalize_ocr_text", "summarize_cer"]
