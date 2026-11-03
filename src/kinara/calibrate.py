"""Calibrate the August 2025 flood thresholds on geolocated reference points (TRD.md 5.3, PRD F3).

Reference points come from news photos, drone video and field reports, each marked flooded or not
flooded. Earth Engine samples before/after VV at every point (kinara.gee.flood.sample_backscatter);
this module scores the tested numpy rule `kinara.detect.change.flood_mask` over a grid of
thresholds. Scores carry Wilson intervals because 30 to 100 points is a small sample.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from kinara.detect.change import flood_mask
from kinara.validate.metrics import wilson_interval

MIN_POINTS = 30           # PRD F3 acceptance: at least 30 geolocated locations
REQUIRED = ("point_id", "lon", "lat", "flooded")
DEFAULT_GRID = {
    "open_water_max_db": [-22.0, -20.0, -19.0, -18.0, -17.0, -16.0, -15.0],
    "open_water_drop_db": [1.5, 2.0, 3.0, 4.0, 5.0],
    "urban_rise_db": [1.5, 2.0, 3.0, 4.0, 5.0],
}


def read_points(path: str) -> pd.DataFrame:
    """Reference points CSV (see data/reference/flood_validation_points.csv for the columns).

    Raises:
        ValueError: If a required column is missing or `flooded` is not 0/1.
    """
    df = pd.read_csv(path, comment="#")
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    if not df["flooded"].isin([0, 1]).all():
        raise ValueError(f"{path}: 'flooded' must be 0 or 1")
    return df


def confusion(pred: np.ndarray, truth: np.ndarray) -> dict:
    """Accuracy, sensitivity (flooded found) and specificity (dry kept dry), each with a 95% interval."""
    pred, truth = np.asarray(pred, bool), np.asarray(truth, bool)
    tp, tn = int((pred & truth).sum()), int((~pred & ~truth).sum())
    fp, fn = int((pred & ~truth).sum()), int((~pred & truth).sum())
    out = {"n": len(truth), "tp": tp, "tn": tn, "fp": fp, "fn": fn}
    for name, k, n in (("accuracy", tp + tn, len(truth)), ("sensitivity", tp, tp + fn), ("specificity", tn, tn + fp)):
        out[name] = k / n if n else None
        out[f"{name}_ci"] = list(wilson_interval(k, n)) if n else None
    s, p = out["sensitivity"], out["specificity"]
    out["balanced_accuracy"] = None if s is None or p is None else (s + p) / 2
    return out


def grid_search(samples: pd.DataFrame, grid: dict[str, list[float]] | None = None) -> pd.DataFrame:
    """Score every threshold combination; best balanced accuracy first.

    Args:
        samples: Columns before_db, after_db, built (0/1), flooded (0/1); rows with missing radar are dropped.
        grid: Candidate values per threshold (DEFAULT_GRID if None).

    Returns:
        One row per combination with the three thresholds and the `confusion` scores.
    """
    grid = grid or DEFAULT_GRID
    s = samples.dropna(subset=["before_db", "after_db"])
    before, after = s["before_db"].to_numpy(float), s["after_db"].to_numpy(float)
    built, truth = s["built"].to_numpy(bool), s["flooded"].to_numpy(bool)
    rows = []
    for mx, drop, rise in itertools.product(grid["open_water_max_db"], grid["open_water_drop_db"],
                                            grid["urban_rise_db"]):
        m = flood_mask(before, after, built, mx, drop, rise)
        c = confusion(m["flooded"], truth)
        rows.append({"open_water_max_db": mx, "open_water_drop_db": drop, "urban_rise_db": rise,
                     **{k: c[k] for k in ("n", "balanced_accuracy", "accuracy", "sensitivity", "specificity",
                                         "tp", "tn", "fp", "fn")}})
    df = pd.DataFrame(rows)
    return df.sort_values(["balanced_accuracy", "accuracy"], ascending=False, na_position="last").reset_index(drop=True)


def cross_validated(samples: pd.DataFrame, folds: np.ndarray, grid: dict[str, list[float]] | None = None) -> dict:
    """Honest score: thresholds chosen without each fold, then applied to it (spatial block folds).

    Picking the best thresholds and scoring them on the same points flatters the result; this
    number is the one to quote.

    Args:
        samples: As for `grid_search`.
        folds: Fold number per row of `samples` (e.g. `block_folds` of 2 km blocks).
        grid: Candidate thresholds.
    """
    ok = samples[["before_db", "after_db"]].notna().all(axis=1).to_numpy()
    s = samples[ok].reset_index(drop=True)
    folds = np.asarray(folds)[ok]       # folds are given per row of `samples`
    pred = np.zeros(len(s), bool)
    for k in np.unique(folds):
        train, test = s[folds != k], s[folds == k]
        if train["flooded"].nunique() < 2:
            continue
        best = grid_search(train, grid).iloc[0]
        m = flood_mask(test["before_db"].to_numpy(float), test["after_db"].to_numpy(float),
                       test["built"].to_numpy(bool), best["open_water_max_db"], best["open_water_drop_db"],
                       best["urban_rise_db"])
        pred[test.index.to_numpy()] = m["flooded"]
    return confusion(pred, s["flooded"].to_numpy(bool))
