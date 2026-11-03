"""Sentinel-1 change logic on numpy arrays.

Two jobs:
  1. New construction: backscatter rises (double bounce from new walls) and STAYS up on
     `persistence_passes` consecutive passes. Persistence filters out wet soil and crop cycles.
  2. Flood extent: open fields get darker (specular water), but flooded built-up areas get
     BRIGHTER (water + walls = stronger double bounce). A plain dark-water threshold misses the
     flooded housing societies, which are exactly the areas PDMA cares about.

All inputs are in dB except where noted. Earth Engine's COPERNICUS/S1_GRD is already in dB; average
in linear power, never in dB (see `mean_db`).
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

DB_FLOOR = 1e-6   # linear power floor before log10, avoids -inf


def to_db(linear: np.ndarray) -> np.ndarray:
    """Linear backscatter power to dB."""
    return 10.0 * np.log10(np.maximum(np.asarray(linear, float), DB_FLOOR))


def to_linear(db: np.ndarray) -> np.ndarray:
    """dB to linear backscatter power."""
    return np.power(10.0, np.asarray(db, float) / 10.0)


def mean_db(stack_db: np.ndarray, axis: int = 0) -> np.ndarray:
    """Average a stack of dB images in linear power, return dB (NaN-aware)."""
    return to_db(np.nanmean(to_linear(stack_db), axis=axis))


def log_ratio_db(before_db: np.ndarray, after_db: np.ndarray) -> np.ndarray:
    """After minus before in dB (equals 10*log10 of the linear ratio). Positive = brighter."""
    before_db, after_db = np.asarray(before_db, float), np.asarray(after_db, float)
    if before_db.shape != after_db.shape:
        raise ValueError(f"shape mismatch: {before_db.shape} vs {after_db.shape}")
    return after_db - before_db


def persistent_increase(baseline_db: np.ndarray, passes_db: np.ndarray, rise_db: float,
                        n_passes: int) -> np.ndarray:
    """Pixels whose backscatter rose by >= rise_db on the last `n_passes` consecutive passes.

    Args:
        baseline_db: (H, W) reference image, e.g. a linear-mean composite of the previous season.
        passes_db: (T, H, W) newest passes in time order (oldest first).
        rise_db: Minimum rise in dB on every pass.
        n_passes: How many of the newest passes must all show the rise.

    Returns:
        Boolean (H, W) mask. NaN in any required pass means False.
    """
    passes_db = np.asarray(passes_db, float)
    if passes_db.ndim != 3:
        raise ValueError("passes_db must be (T, H, W)")
    if not 1 <= n_passes <= passes_db.shape[0]:
        raise ValueError(f"n_passes must be between 1 and {passes_db.shape[0]}")
    diffs = passes_db[-n_passes:] - np.asarray(baseline_db, float)[None]
    with np.errstate(invalid="ignore"):
        return np.all(diffs >= rise_db, axis=0) & ~np.any(np.isnan(diffs), axis=0)


def flood_mask(before_db: np.ndarray, after_db: np.ndarray, built: np.ndarray,
               open_water_max_db: float, open_water_drop_db: float, urban_rise_db: float) -> dict[str, np.ndarray]:
    """Flood extent that handles both open land and built-up areas.

    Args:
        before_db, after_db: VV backscatter before and during the flood (dB).
        built: Boolean mask of built-up pixels (e.g. Open Buildings presence).
        open_water_max_db: After-event VV must be below this to count as open water.
        open_water_drop_db: ...and at least this many dB darker than before.
        urban_rise_db: Built-up pixels at least this many dB brighter count as flooded.

    Returns:
        Dict with boolean masks 'open', 'urban' and their union 'flooded'.
    """
    diff = log_ratio_db(before_db, after_db)
    built = np.asarray(built, bool)
    with np.errstate(invalid="ignore"):
        open_w = (~built) & (np.asarray(after_db) <= open_water_max_db) & (diff <= -open_water_drop_db)
        urban = built & (diff >= urban_rise_db)
    return {"open": open_w, "urban": urban, "flooded": open_w | urban}


def min_area_filter(mask: np.ndarray, pixel_m: float, min_area_ha: float) -> tuple[np.ndarray, np.ndarray]:
    """Drop connected patches smaller than min_area_ha (8-connected).

    Returns:
        (filtered mask, labels) where labels numbers the surviving patches 1..N (0 = background).
    """
    if pixel_m <= 0:
        raise ValueError("pixel_m must be positive")
    mask = np.asarray(mask, bool)
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    if n == 0:
        return mask.copy(), labels
    min_px = int(np.ceil(min_area_ha * 10_000 / pixel_m**2))
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_px
    keep[0] = False
    kept = keep[labels]
    new_labels, _ = ndimage.label(kept, structure=np.ones((3, 3), int))
    return kept, new_labels


def area_ha(mask: np.ndarray, pixel_m: float) -> float:
    """Area of True pixels in hectares."""
    return float(np.count_nonzero(mask) * pixel_m**2 / 10_000)
