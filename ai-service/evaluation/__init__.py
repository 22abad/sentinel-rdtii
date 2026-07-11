"""Reproducible golden-set evaluation for RDTII extraction."""

from .metrics import evaluate_predictions
from .models import GoldenCase, GoldenDocument, PredictionRecord

__all__ = [
    "GoldenCase",
    "GoldenDocument",
    "PredictionRecord",
    "evaluate_predictions",
]
