import numpy as np
import pytest

from kinara.detect.change import (
    area_ha,
    flood_mask,
    log_ratio_db,
    mean_db,
    min_area_filter,
    persistent_increase,
    to_db,
    to_linear,
)


def test_db_roundtrip():
    x = np.array([0.01, 0.1, 1.0])
    assert np.allclose(to_linear(to_db(x)), x)


def test_mean_db_averages_in_linear_power():
    stack = np.array([[-10.0], [-20.0]])
    # linear mean of 0.1 and 0.01 = 0.055 -> -12.6 dB, NOT the dB mean of -15
    assert abs(mean_db(stack)[0] - to_db(np.array([0.055]))[0]) < 1e-9
    assert mean_db(stack)[0] > -15


def test_log_ratio_shape_check():
    with pytest.raises(ValueError):
        log_ratio_db(np.zeros((2, 2)), np.zeros((3, 3)))


def test_persistence_rejects_one_off_spikes():
    base = np.full((1, 3), -15.0)
    passes = np.array([
        [[-10.0, -10.0, -15.0]],   # older pass
        [[-10.0, -15.0, -10.0]],   # newest pass
    ])
    m = persistent_increase(base, passes, rise_db=3.0, n_passes=2)
    assert m.tolist() == [[True, False, False]]


def test_persistence_nan_is_false():
    base = np.full((1, 1), -15.0)
    passes = np.array([[[np.nan]], [[-5.0]]])
    assert not persistent_increase(base, passes, 3.0, 2)[0, 0]


def test_persistence_bad_n():
    with pytest.raises(ValueError):
        persistent_increase(np.zeros((1, 1)), np.zeros((2, 1, 1)), 3.0, 3)


def test_flood_mask_catches_bright_flooded_buildings():
    before = np.array([[-12.0, -8.0, -12.0]])
    after = np.array([[-22.0, -3.0, -11.0]])   # field went dark, buildings went bright, third unchanged
    built = np.array([[False, True, False]])
    m = flood_mask(before, after, built, open_water_max_db=-18, open_water_drop_db=3, urban_rise_db=3)
    assert m["open"].tolist() == [[True, False, False]]
    assert m["urban"].tolist() == [[False, True, False]]
    assert m["flooded"].tolist() == [[True, True, False]]


def test_min_area_filter_drops_small_patches():
    mask = np.zeros((20, 20), bool)
    mask[0:2, 0:2] = True          # 4 px = 0.04 ha at 10 m
    mask[10:20, 10:20] = True      # 100 px = 1 ha
    kept, labels = min_area_filter(mask, pixel_m=10, min_area_ha=0.5)
    assert area_ha(kept, 10) == 1.0
    assert labels.max() == 1


def test_min_area_filter_empty():
    kept, labels = min_area_filter(np.zeros((5, 5), bool), 10, 0.5)
    assert not kept.any() and labels.max() == 0
