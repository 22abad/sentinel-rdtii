"""RLVR seam — verifiable rewards over extraction candidates.

Three pieces, deliberately kept apart:

  * ``reward``     — the PROXY reward. Computable at inference time with no
                     answer key. This is the only thing the selector may see.
  * ``oracle``     — the LABELLED reward. Needs a reviewed GoldenCase, and is
                     a per-prediction decomposition of the metrics the golden
                     harness already reports (``evaluation.metrics``).
  * ``trajectory`` — append-only JSONL of every sampled candidate with both
                     rewards attached, so a later RFT/GRPO run has data and so
                     we can measure whether the proxy predicts the oracle.

The separation is the whole point. If the selector could see oracle labels we
would be tuning on the benchmark, and the 55.7% headline would stop meaning
anything. ``best_of_n.select_best`` therefore accepts proxy rewards only.
"""

from rlvr.best_of_n import Candidate, Selection, select_best
from rlvr.reward import ProxyReward, RewardComponent, score_candidate
from rlvr.sampling import SamplingParams, sampling_ladder
from rlvr.trajectory import TrajectoryWriter

__all__ = [
    "Candidate",
    "ProxyReward",
    "RewardComponent",
    "SamplingParams",
    "Selection",
    "TrajectoryWriter",
    "sampling_ladder",
    "score_candidate",
    "select_best",
]
