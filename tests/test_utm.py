import pytest

from kinara.geo.utm import FALSE_EASTING, cell_id_at, in_lahore_bbox, utm43n


def test_central_meridian_has_false_easting():
    x, _ = utm43n(75.0, 31.5)
    assert abs(x - FALSE_EASTING) < 1e-6


def test_equator_on_central_meridian_is_origin():
    x, y = utm43n(75.0, 0.0)
    assert abs(x - 500000) < 1e-6 and abs(y) < 1e-6


def test_symmetric_about_central_meridian():
    xe, ye = utm43n(75.7, 31.5)
    xw, yw = utm43n(74.3, 31.5)
    assert abs((xe - 500000) - (500000 - xw)) < 1e-6
    assert abs(ye - yw) < 1e-6


def test_lahore_values_are_plausible():
    # Minar-e-Pakistan, about 74.31 E 31.59 N: west of the meridian, northing about 3.49 million m
    x, y = utm43n(74.3095, 31.5925)
    assert 430_000 < x < 440_000
    assert 3_490_000 < y < 3_500_000


def test_cell_id_format_and_size():
    cid = cell_id_at(74.3095, 31.5925, 500)
    col, row = cid[1:].split("_")
    x, y = utm43n(74.3095, 31.5925)
    assert int(col) == int(x // 500) and int(row) == int(y // 500)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        utm43n(74.3, -1.0)
    with pytest.raises(ValueError):
        utm43n(10.0, 31.5)
    with pytest.raises(ValueError):
        cell_id_at(74.3, 31.5, 0)


def test_bbox():
    assert in_lahore_bbox(74.3, 31.5)
    assert not in_lahore_bbox(73.0, 33.7)   # Islamabad
