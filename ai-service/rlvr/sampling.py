"""What varies across the k candidates of a best-of-N draw.

Every provider pins extraction at ``temperature=0`` (see
``openai_compatible._call_llm``, ``ollama.extract_features``). That is correct
for a single-shot submission run — it is also what makes a naive best-of-N
useless, because k greedy draws of the same prompt are k identical strings.
So sampling needs an explicit, auditable knob.

Design rules
------------
1. **Sample 0 is always greedy.** temperature=0, top_p=1.0 — byte-identical to
   what the pipeline produces today. Ties in the selector break toward the
   lowest index, so best-of-N can never score *below* the current pipeline on
   the proxy reward. That is the safety property that makes this safe to run
   near a submission deadline.
2. **Seeds are derived, not random.** ``Math.random``-style nondeterminism
   would break the "a judge re-runs the tool and gets our output" contract.
   The seed is a hash of (document, chunk, indicator, sample index), so the
   whole best-of-N run is reproducible while still being varied.
3. **Only decoding varies.** The model, the prompt, the feature spec, the
   chunker, the deterministic scorers and the validation rules are held fixed.
   Varying those would change what is being measured rather than give the
   selector a better draw to choose from.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


# Decoding ladder for samples 1..k-1. Sample 0 is always greedy and is not in
# this list. Kept short and boring on purpose: extraction is a copy-the-span
# task, and past ~1.0 the model starts paraphrasing the quote, which the
# grounding gate then rejects — burning budget to produce guaranteed zeros.
DEFAULT_TEMPERATURE_LADDER: tuple[float, ...] = (0.7, 0.9, 0.5, 1.0)
DEFAULT_TOP_P: float = 0.95


@dataclass(frozen=True)
class SamplingParams:
    """Decoding arguments for exactly one candidate draw."""

    sample_index: int
    temperature: float
    top_p: float
    seed: int | None = None

    @property
    def is_greedy(self) -> bool:
        return self.temperature == 0.0

    def as_record(self) -> dict:
        """Trajectory-record form — what was actually asked of the provider."""
        return {
            "sample_index": self.sample_index,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
        }


def derive_seed(*parts: object) -> int:
    """Deterministic 31-bit seed from run coordinates.

    Stable across processes and machines — ``hash()`` is not (PYTHONHASHSEED),
    and a run that cannot be reproduced cannot be submitted.
    """
    payload = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") & 0x7FFFFFFF


def sampling_ladder(
    n: int,
    *,
    document_id: str = "",
    chunk_index: int = 0,
    indicator_id: str = "",
    temperatures: tuple[float, ...] | None = None,
    top_p: float = DEFAULT_TOP_P,
) -> list[SamplingParams]:
    """Build the k sampling configs for one (chunk, indicator) draw.

    Index 0 is greedy; the rest cycle the temperature ladder. ``n <= 1``
    returns just the greedy config, which is exactly today's behaviour.
    """
    if n < 1:
        raise ValueError(f"best-of-N needs n >= 1, got {n}")

    ladder = temperatures if temperatures is not None else DEFAULT_TEMPERATURE_LADDER
    if n > 1 and not ladder:
        raise ValueError("temperature ladder is empty but n > 1 was requested")

    configs = [
        SamplingParams(
            sample_index=0,
            temperature=0.0,
            top_p=1.0,
            seed=derive_seed(document_id, chunk_index, indicator_id, 0),
        )
    ]
    for i in range(1, n):
        configs.append(
            SamplingParams(
                sample_index=i,
                temperature=ladder[(i - 1) % len(ladder)],
                top_p=top_p,
                seed=derive_seed(document_id, chunk_index, indicator_id, i),
            )
        )
    return configs



def best_of_n_from_env(default: int = 1) -> int:
    """Read ``RDTII_BEST_OF_N``. Default 1 = current single-shot pipeline."""
    raw = os.getenv("RDTII_BEST_OF_N", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


__all__ = [
    "DEFAULT_TEMPERATURE_LADDER",
    "DEFAULT_TOP_P",
    "SamplingParams",
    "best_of_n_from_env",
    "derive_seed",
    "sampling_ladder",
]
