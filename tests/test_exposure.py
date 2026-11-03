"""Exposure counts from footprints and rasters, raster helpers, units."""

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import Point, box

from kinara import exposure
from kinara.gee.fetch import tiles
from kinara.geo.raster import grid_for_bounds, rasterize, rowcol, values_at

CRS = "EPSG:32643"
T4 = Affine(4, 0, 0, 0, -4, 40)    # 10 x 10 grid of 4 m pixels, top-left (0, 40)


def test_values_at_window_min_and_offgrid():
    arr = np.zeros((10, 10))
    arr[2, 2] = 2019
    arr[2, 3] = 2017
    # point in pixel (2, 2): centre value 2019; the 3x3 window also sees 2017
    x, y = 2 * 4 + 2, 40 - 2 * 4 - 2
    assert values_at(arr, T4, [x], [y], window=0, invalid=0)[0] == 2019
    assert values_at(arr, T4, [x], [y], window=1, invalid=0)[0] == 2017
    assert np.isnan(values_at(arr, T4, [30], [30], window=0, invalid=0)[0])     # all zero = never built
    assert np.isnan(values_at(arr, T4, [-50], [5], window=1)[0])                # off the raster
    with pytest.raises(ValueError):
        values_at(arr, T4, [x], [y], reducer="mean")


def test_rowcol_and_grid():
    r, c = rowcol(T4, np.array([0.1, 39.9]), np.array([39.9, 0.1]))
    assert r.tolist() == [0, 9] and c.tolist() == [0, 9]
    t, shape = grid_for_bounds((3, 5, 47, 38), 10)
    assert (t.c, t.f) == (0, 40) and shape == (4, 5)


def test_rasterize():
    m = rasterize([box(0, 20, 20, 40)], T4, (10, 10))
    assert m.sum() == 25 and m[0, 0] and not m[9, 9]
    assert not rasterize([], T4, (3, 3)).any()


def test_cohort_classes():
    assert exposure.cohort_class(np.array([2016, 2017, 2018, 2020, 2022, 2023, np.nan])).tolist() == \
        [0, 1, 1, 2, 3, 4, -1]


def _buildings():
    years = np.zeros((10, 10))
    years[0:5, 0:5] = 2016
    years[0:5, 5:10] = 2021
    flood = np.zeros((10, 10))
    flood[5:10, :] = 1
    pts = gpd.GeoDataFrame(geometry=[Point(2, 38), Point(30, 38), Point(30, 2), Point(2, 2)], crs=CRS)
    return exposure.attach_rasters(pts, (years, T4), (flood, T4), window=0)


def test_attach_and_unit_counts():
    b = _buildings()
    assert b.first_year.tolist()[:2] == [2016, 2021] and np.isnan(b.first_year.iloc[2])
    assert b.flooded.tolist() == [False, False, True, True]
    c = exposure.unit_counts(b, 2016)
    assert c == {"bld_n": 4, "bld_post2016_n": 1, "bld_year_unknown_n": 2, "bld_flooded_2025": 2}


def test_by_unit_keeps_empty_units():
    b = _buildings()
    units = gpd.GeoDataFrame({"unit_id": ["W", "E", "far"]},
                             geometry=[box(0, 0, 20, 40), box(20, 0, 40, 40), box(100, 100, 120, 120)], crs=CRS)
    df = exposure.by_unit(b, units, "unit_id", 2016)
    assert df.loc["W", "bld_n"] == 2 and df.loc["E", "bld_post2016_n"] == 1 and df.loc["far", "bld_n"] == 0


def test_cells_cumulative_years():
    b = _buildings()
    c = exposure.cells(b, 20, 2016, 2023, CRS)
    assert c.n.sum() == 4
    top_right = c.set_index("cell_id").loc["C1_1"]
    assert top_right.c2020 == 0 and top_right.c2021 == 1 and top_right.cohort == 3
    assert exposure.cells(b.iloc[0:0], 20, 2016, 2023, CRS).empty


def test_kanal():
    assert exposure.kanal(1.0) == pytest.approx(19.77, abs=0.01)
    assert exposure.kanal(1.0, marla_sqft=225) == pytest.approx(23.92, abs=0.01)    # LDA marla


def test_tiles_cover_grid_once():
    t = tiles(2500, 1100, 1024)
    assert len(t) == 6 and sum(w * h for _, _, w, h in t) == 2500 * 1100
    with pytest.raises(ValueError):
        tiles(10, 10, 0)
