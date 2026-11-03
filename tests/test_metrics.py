import numpy as np
import pytest

from kinara.validate.metrics import block_folds, precision_report, spatial_blocks, wilson_interval


def test_wilson_known_value():
    lo, hi = wilson_interval(8, 10)
    assert abs(lo - 0.4902) < 1e-3 and abs(hi - 0.9433) < 1e-3


def test_wilson_edges():
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0
    with pytest.raises(ValueError):
        wilson_interval(1, 0)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


def test_precision_ignores_unverified_and_uses_lower_bound():
    verdicts = ["confirmed"] * 9 + ["false_alarm"] + ["new"] * 50
    r = precision_report(verdicts, target=0.80)
    assert r["n"] == 10 and r["precision"] == 0.9
    assert r["meets_target"] is False          # 9/10 looks great but the lower bound is about 0.60


def test_precision_large_sample_passes():
    r = precision_report(["confirmed"] * 270 + ["false_alarm"] * 30, target=0.80)
    assert r["meets_target"] is True


def test_precision_empty():
    assert precision_report([])["precision"] is None


def test_blocks_and_folds_keep_neighbours_together():
    x = np.array([0, 100, 5000, 5100], float)
    y = np.zeros(4)
    b = spatial_blocks(x, y, 2000)
    assert b[0] == b[1] and b[2] == b[3] and b[0] != b[2]
    blocks = np.repeat(np.arange(20), 5)
    folds = block_folds(blocks, 5)
    for blk in range(20):
        assert len(set(folds[blocks == blk])) == 1
