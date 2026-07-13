"""RDTII AI Mapper FastAPI entry point.

This module intentionally stays small: it loads configuration, exposes a few
legacy patch points used by tests and agents, and creates the FastAPI app from
route modules under ``api/``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)
load_dotenv(override=False)

from api.app import create_app
from api.extraction import (
    _fetch_with_browser_mode,
    _is_error_page_content,
    _is_garbage_content,
    _is_thai_query,
)
from api.system import TextRequest
from chunker import regex_legal_chunker
from classifier import classify_indicator
from country_detector import detect_country
from coverage_classifier import classify_coverage
from features import get_feature_spec
from providers import canonical_name, get_default_provider, get_provider, list_providers
from providers.base import ExtractionError
from schemas import (
    ExtractionResponse,
    IndicatorMapping,
    RAGQueryRequest,
    RejectedExtraction,
    ReviewRequest,
)
from scoring import score_indicator
from services.extraction import run_extraction as _run_extraction
from services.mapping_cleanup import format_and_clean_mapping
from services.streaming_extraction import process_single as _process_single
from services.streaming_extraction import stream_extraction as _stream_extraction
from source_validator import grade_source, require_primary_source
from staleness_checker import check_staleness
from timeframe_extractor import build_timeframe_column, extract_timeframe, format_to_month_year
from verification import find_quote_offsets, verify_quote

logger = logging.getLogger(__name__)


_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer

        _embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _embed_model


_provider = None


def _get_provider():
    global _provider
    if _provider is None:
        try:
            _provider = get_default_provider()
        except ExtractionError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Provider unavailable: {exc}. Check .env for API keys.",
            )
    return _provider


def _active_provider_name() -> tuple[str, str | None]:
    raw = os.getenv("RDTII_LLM_PROVIDER", "deepseek")
    return raw, canonical_name(raw)


app = create_app()
