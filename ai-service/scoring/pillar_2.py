from __future__ import annotations
from typing import Literal

Score = Literal[0.0, 0.25, 0.5, 1.0]

def score(indicator_id: str, features: dict) -> tuple[Score, str]:
    if indicator_id != "2.1":
        raise NotImplementedError(f"Pillar 2 indicator {indicator_id} not implemented")
    # RDTII Pillar 2.1 Logic for Public Procurement
    if bool(features.get("procurement_preference")):
        return 1.0, "Score 1: Local preference found in public procurement policy."
    return 0.5, "Score 0.5: Standard public procurement regulation."
