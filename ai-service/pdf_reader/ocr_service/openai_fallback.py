"""Optional OpenAI Vision fallback after local Tesseract returns too little text."""

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import cv2
import numpy as np


@dataclass(frozen=True)
class VisionOcrResult:
    text: str = ""
    provider: str = "openai"
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    pricing_date: str | None = None
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    latency_ms: int = 0
    status: str = "unavailable"
    error_type: str | None = None


def _to_b64_png(image: Union[np.ndarray, Path]) -> str:
    """Convert a numpy RGB array or file path to a base64-encoded PNG string."""
    if isinstance(image, np.ndarray):
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        _, buf = cv2.imencode(".png", bgr)
        return base64.b64encode(buf.tobytes()).decode()
    return base64.b64encode(Path(image).read_bytes()).decode()


def ocr_vision(image: Union[np.ndarray, Path]) -> str:
    """Send a page image to GPT-4o for OCR.

    Accepts either a numpy RGB array (from the fitz pipeline) or a file Path
    (legacy callers). Returns extracted text or empty string on failure.
    """
    return ocr_vision_with_usage(image).text


def ocr_vision_with_usage(image: Union[np.ndarray, Path]) -> VisionOcrResult:
    """Run Vision OCR and retain actual returned usage without storing the image."""
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
    if not api_key:
        return VisionOcrResult(model=model, status="unavailable")

    started = time.perf_counter()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        b64 = _to_b64_png(image)
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all text from this document image exactly as written. "
                            "Preserve paragraph structure and line breaks. "
                            "Return only the extracted text, no commentary."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=4096,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        input_price = _optional_price("OPENAI_VISION_INPUT_USD_PER_MTOK")
        output_price = _optional_price("OPENAI_VISION_OUTPUT_USD_PER_MTOK")
        pricing_date = os.getenv("OPENAI_VISION_PRICING_DATE")
        cost = None
        if (
            input_tokens is not None
            and output_tokens is not None
            and input_price is not None
            and output_price is not None
            and pricing_date
        ):
            cost = (
                input_tokens * input_price / 1_000_000
                + output_tokens * output_price / 1_000_000
            )
        return VisionOcrResult(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            pricing_date=pricing_date if cost is not None else None,
            input_usd_per_million=input_price,
            output_usd_per_million=output_price,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status="success",
        )
    except MemoryError:
        raise
    except Exception as exc:
        return VisionOcrResult(
            model=model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status="failed",
            error_type=type(exc).__name__,
        )


def _optional_price(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None
