"""Vector helpers (geopandas / shapely 2).

Reused from LPVIS (lahore-poverty/src/lpvis/geo.py): polygons_only, make_grid, majority_join,
accounting. Kinara uses them to clean boundaries, build the reporting grid and attach mouza or
tehsil names to alerts.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

POLY_TYPES = {"Polygon", "MultiPolygon"}


def accounting(log: logging.Logger, stage: str, n_in: int, n_out: int) -> None:
    """Log how many features a step kept, so silent data loss shows up in the logs."""
    log.info(f"[{stage}] {n_in:,} in -> {n_out:,} out ({n_in - n_out:+,} removed)")


def polygons_only(gdf: gpd.GeoDataFrame, log: logging.Logger | None = None) -> gpd.GeoDataFrame:
    """make_valid, explode collections and multiparts, keep polygon parts only."""
    n0 = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["src_fid"] = gdf.index
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    parts = gdf.explode(index_parts=False, ignore_index=True)
    while (parts.geom_type == "GeometryCollection").any():
        parts = parts.explode(index_parts=False, ignore_index=True)
    parts = parts[parts.geom_type.isin(POLY_TYPES)].copy()
    if log:
        log.info(f"[polygons_only] {n0:,} features -> {len(parts):,} polygon parts")
    return parts


def make_grid(outline: shapely.Geometry, crs: str, cell: float = 500.0) -> gpd.GeoDataFrame:
    """Square grid aligned to multiples of `cell` metres; keeps cells touching the outline.

    Cell ids follow C{column}_{row}, the same rule as `kinara.geo.utm.cell_id_at`.
    """
    if cell <= 0:
        raise ValueError("cell must be positive")
    x0, y0, x1, y1 = outline.bounds
    x0, y0 = np.floor(x0 / cell) * cell, np.floor(y0 / cell) * cell
    cells = [box(x, y, x + cell, y + cell) for y in np.arange(y0, y1, cell) for x in np.arange(x0, x1, cell)]
    g = gpd.GeoDataFrame(geometry=cells, crs=crs)
    g = g[g.intersects(outline)].copy()
    g["frac_in_area"] = g.intersection(outline).area / (cell * cell)
    g["cell_x"] = (g.geometry.bounds.minx // cell).astype(int)
    g["cell_y"] = (g.geometry.bounds.miny // cell).astype(int)
    g["cell_id"] = "C" + g.cell_x.astype(str) + "_" + g.cell_y.astype(str)
    return g.reset_index(drop=True)


def boundary_geojson(path: str | Path, simplify_m: float = 10.0, metric_crs: str = "EPSG:32643") -> dict:
    """Dissolve a boundary file into one WGS 84 GeoJSON geometry, simplified in metres.

    Simplifying in a metric CRS keeps the vertex tolerance meaningful; 10 m is far below
    Sentinel pixel size and keeps the payload small enough for an Earth Engine request.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file has no usable polygon.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"boundary file not found: {path}")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"{path.name} has no CRS (.prj missing)")
    gdf = polygons_only(gdf.to_crs(metric_crs))
    if gdf.empty:
        raise ValueError(f"{path.name} has no polygon features")
    geom = shapely.make_valid(gdf.geometry.union_all()).simplify(simplify_m, preserve_topology=True)
    wgs = gpd.GeoSeries([geom], crs=metric_crs).to_crs("EPSG:4326").iloc[0]
    return shapely.geometry.mapping(wgs)


def majority_join(target: gpd.GeoDataFrame, zones: gpd.GeoDataFrame, cols: list[str],
                  id_col: str) -> pd.DataFrame:
    """For each target feature, attributes of the zone polygon covering most of its area."""
    ov = gpd.overlay(target[[id_col, "geometry"]], zones[cols + ["geometry"]], how="intersection",
                     keep_geom_type=True)
    ov["a"] = ov.area
    best = ov.sort_values("a", ascending=False).drop_duplicates(id_col)
    return best.set_index(id_col)[cols].reindex(target[id_col])
