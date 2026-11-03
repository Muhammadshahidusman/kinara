"""Precision with confidence intervals, field-verdict summaries and spatial blocks.

`spatial_blocks` and `block_folds` are reused from LPVIS (lahore-poverty/src/lpvis/cv.py), switched
from km on lon/lat to metres on projected coordinates, which is what Kinara stores.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

CONFIRMED = "confirmed"
FALSE_ALARM = "false_alarm"
VERDICTS = (CONFIRMED, FALSE_ALARM)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion (better than the normal interval for small n).

    Raises:
        ValueError: If n <= 0 or successes is outside 0..n.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def precision_report(verdicts: Iterable[str], target: float = 0.80) -> dict:
    """Precision of verified alerts with a 95% Wilson interval.

    Only 'confirmed' and 'false_alarm' count; other statuses (new, visited) are ignored.
    `meets_target` is True only when the LOWER bound clears the target, so a lucky small
    sample can't pass the release gate.
    """
    v = [x for x in verdicts if x in VERDICTS]
    n = len(v)
    if n == 0:
        return {"n": 0, "precision": None, "ci_low": None, "ci_high": None, "meets_target": False}
    tp = sum(1 for x in v if x == CONFIRMED)
    lo, hi = wilson_interval(tp, n)
    return {"n": n, "precision": tp / n, "ci_low": lo, "ci_high": hi, "meets_target": lo >= target}


def spatial_blocks(x_m: np.ndarray, y_m: np.ndarray, block_m: float) -> np.ndarray:
    """Assign projected points to square blocks of side block_m metres (block id per point)."""
    if block_m <= 0:
        raise ValueError("block_m must be positive")
    x_m, y_m = np.asarray(x_m, float), np.asarray(y_m, float)
    bx = np.floor((x_m - np.nanmin(x_m)) / block_m).astype(int)
    by = np.floor((y_m - np.nanmin(y_m)) / block_m).astype(int)
    return bx * 100_000 + by


def block_folds(blocks: np.ndarray, n_folds: int = 5, seed: int = 42) -> np.ndarray:
    """Randomly assign whole blocks to folds, so neighbours never sit in train and test together."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(blocks)
    fold_of_block = dict(zip(uniq, rng.permutation(len(uniq)) % n_folds, strict=True))
    return np.array([fold_of_block[b] for b in blocks])
