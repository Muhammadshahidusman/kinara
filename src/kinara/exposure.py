"""Exposure numbers from building footprints: what PDMA and the district asked for.

Inputs are Open Buildings v3 footprint centroids inside the floodplain (fetched by
scripts/fetch_inputs.py) plus two Earth Engine exports:
  first_built_year.tif   year each 4 m pixel first showed a building (2016 = on or before 2016)
  flood_2025.tif         August 2025 flood extent (band 'flooded')
Each footprint gets a first-built year and a flooded flag; counts are then summed per tehsil, mouza
and map cell. All counts are "estimated buildings": a footprint is a roof seen from space, not a
household.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from affine import Affine
from shapely.geometry import box

from kinara.geo.raster import values_at

# UIUX.md cohort classes, light (old) to dark (new)
COHORTS = ((0, "2016 or before", 0, 2016), (1, "2017-18", 2017, 2018), (2, "2019-20", 2019, 2020),
           (3, "2021-22", 2021, 2022), (4, "2023+", 2023, 9999))
UNKNOWN = -1


def cohort_class(year: np.ndarray) -> np.ndarray:
    """Cohort index 0..4 for each first-built year; -1 where the year is unknown (NaN)."""
    year = np.asarray(year, float)
    out = np.full(year.shape, UNKNOWN, dtype=int)
    for idx, _, lo, hi in COHORTS:
        out[(year >= lo) & (year <= hi)] = idx
    return out


def attach_rasters(points: gpd.GeoDataFrame, years: tuple[np.ndarray, Affine], flood: tuple[np.ndarray, Affine],
                   window: int = 1) -> gpd.GeoDataFrame:
    """Add `first_year` (float, NaN = not seen by Open Buildings Temporal) and `flooded` (bool).

    Args:
        points: Footprint centroids in EPSG:32643.
        years: (array, transform) of first_built_year.tif; 0 = never built.
        flood: (array, transform) of the 'flooded' band; NaN = outside the scene.
        window: first_built_year search half-width in pixels. A v3 centroid can fall on a courtyard
            pixel; the earliest year in a 3x3 (12 m) window is the building's year.

    Returns:
        A copy of `points` with the two new columns.
    """
    out = points.copy()
    xs, ys = out.geometry.x.to_numpy(), out.geometry.y.to_numpy()
    out["first_year"] = values_at(years[0], years[1], xs, ys, window=window, invalid=0, reducer="min")
    fl = values_at(flood[0], flood[1], xs, ys, window=0, invalid=-1, reducer="max")
    out["flooded"] = np.nan_to_num(fl, nan=0.0) >= 0.5
    return out


def unit_counts(buildings: gpd.GeoDataFrame, first_year: int) -> dict:
    """Counts for one group of buildings (already selected)."""
    fy = buildings["first_year"]
    return {
        "bld_n": int(len(buildings)),
        "bld_post2016_n": int((fy > first_year).sum()),
        "bld_year_unknown_n": int(fy.isna().sum()),
        "bld_flooded_2025": int(buildings["flooded"].sum()),
    }


def by_unit(buildings: gpd.GeoDataFrame, units: gpd.GeoDataFrame, id_col: str, first_year: int) -> pd.DataFrame:
    """Sum building counts per polygon unit (tehsil or mouza). Units with no buildings get zeros.

    Args:
        buildings: Output of `attach_rasters`, EPSG:32643.
        units: Polygons in the same CRS with a unique `id_col`.
        id_col: Unit id column.
        first_year: First Open Buildings Temporal year; buildings first seen after it count as new.

    Returns:
        DataFrame indexed by `id_col` with bld_n, bld_post2016_n, bld_year_unknown_n, bld_flooded_2025.
    """
    j = gpd.sjoin(buildings, units[[id_col, "geometry"]], how="inner", predicate="within")
    j = j[~j.index.duplicated()]   # a point on a shared edge counts once
    rows = {uid: unit_counts(g, first_year) for uid, g in j.groupby(id_col)}
    empty = {"bld_n": 0, "bld_post2016_n": 0, "bld_year_unknown_n": 0, "bld_flooded_2025": 0}
    df = pd.DataFrame([{id_col: u, **rows.get(u, empty)} for u in units[id_col]])
    return df.set_index(id_col)


def cells(buildings: gpd.GeoDataFrame, cell_m: float, first_year: int, last_year: int, crs: str) -> gpd.GeoDataFrame:
    """Square map cells with counts, cumulative counts per year (timeline slider) and dominant cohort.

    Cell ids follow `kinara.geo.utm.cell_id_at` (C{col}_{row}).
    """
    b = buildings
    cx = np.floor(b.geometry.x.to_numpy() / cell_m).astype(int)
    cy = np.floor(b.geometry.y.to_numpy() / cell_m).astype(int)
    df = pd.DataFrame({"cx": cx, "cy": cy, "fy": b["first_year"].to_numpy(), "fl": b["flooded"].to_numpy()})
    recs = []
    for (x, y), g in df.groupby(["cx", "cy"]):
        known = g["fy"].dropna()
        rec = {"cell_id": f"C{x}_{y}", "n": len(g), "n_new": int((known > first_year).sum()),
               "n_flooded": int(g["fl"].sum()),
               "cohort": int(cohort_class(np.array([known.median()]))[0]) if len(known) else UNKNOWN,
               "geometry": box(x * cell_m, y * cell_m, (x + 1) * cell_m, (y + 1) * cell_m)}
        for yr in range(first_year, last_year + 1):
            rec[f"c{yr}"] = int((known <= yr).sum())
        recs.append(rec)
    if not recs:
        cols = ["cell_id", "n", "n_new", "n_flooded", "cohort", "geometry"]
        return gpd.GeoDataFrame(columns=cols + [f"c{y}" for y in range(first_year, last_year + 1)],
                                geometry="geometry", crs=crs)
    return gpd.GeoDataFrame(recs, geometry="geometry", crs=crs)


def kanal(area_ha: float, marla_sqft: float = 272.25, kanal_marla: int = 20) -> float:
    """Hectares to kanal. Revenue kanal = 20 marla x 272.25 sq ft = 505.86 m2 (UIUX.md section 6)."""
    m2_per_kanal = kanal_marla * marla_sqft * 0.09290304
    return area_ha * 10_000 / m2_per_kanal
