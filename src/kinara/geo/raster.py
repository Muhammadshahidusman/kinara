"""Raster helpers for the local half of the pipeline (rasterio / numpy).

Earth Engine exports land in data/gee_exports as GeoTIFFs in UTM 43N. These helpers sample them at
points, put masks on a common grid, turn labelled patches into polygons and render a web overlay.
Nothing here computes area in degrees: grids are always EPSG:32643.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio import features
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

WEB_MERCATOR = "EPSG:3857"


def find_export(folder: Path, name: str) -> Path | None:
    """Newest file called `name` anywhere under `folder` (Drive downloads arrive in nested folders).

    Args:
        folder: Usually settings paths.gee_exports.
        name: File name, e.g. "flood_2025.tif".

    Returns:
        The most recently modified match, or None.
    """
    hits = sorted(Path(folder).rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def rowcol(transform: Affine, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Row and column of map coordinates on a north-up grid (no rotation)."""
    cols = np.floor((np.asarray(xs, float) - transform.c) / transform.a).astype(int)
    rows = np.floor((np.asarray(ys, float) - transform.f) / transform.e).astype(int)
    return rows, cols


def values_at(arr: np.ndarray, transform: Affine, xs: np.ndarray, ys: np.ndarray, window: int = 0,
              invalid: float = 0, reducer: str = "min") -> np.ndarray:
    """Sample a 2-D array at points, optionally taking the min or max valid value in a small window.

    Args:
        arr: 2-D raster values.
        transform: Affine transform of `arr`.
        xs, ys: Point coordinates in the raster CRS.
        window: Half-width in pixels (1 = 3x3 window).
        invalid: Value meaning "no data"; NaN is always invalid.
        reducer: "min" or "max" over the valid values in the window.

    Returns:
        Float array, NaN where a point is off the raster or has no valid value in its window.
    """
    if reducer not in ("min", "max"):
        raise ValueError("reducer must be 'min' or 'max'")
    rows, cols = rowcol(transform, xs, ys)
    h, w = arr.shape
    fill = np.inf if reducer == "min" else -np.inf
    best = np.full(len(rows), fill)
    for dy in range(-window, window + 1):
        for dx in range(-window, window + 1):
            r, c = rows + dy, cols + dx
            ok = (r >= 0) & (r < h) & (c >= 0) & (c < w)
            v = np.full(len(rows), np.nan)
            v[ok] = arr[r[ok], c[ok]]
            v[(v == invalid) | np.isnan(v)] = fill
            best = np.minimum(best, v) if reducer == "min" else np.maximum(best, v)
    best[np.isinf(best)] = np.nan
    return best


def read_band(path: Path, band: int | str = 1) -> tuple[np.ndarray, Affine, str]:
    """Read one band at full resolution (overviews in EE COGs are averaged, so never use them for masks).

    Args:
        path: GeoTIFF.
        band: 1-based index or band description (e.g. "flooded").

    Returns:
        (array, transform, crs string)
    """
    with rasterio.open(path) as src:
        idx = band if isinstance(band, int) else list(src.descriptions).index(band) + 1
        return src.read(idx), src.transform, src.crs.to_string()


def grid_for_bounds(bounds: tuple[float, float, float, float], res: float) -> tuple[Affine, tuple[int, int]]:
    """North-up grid snapped to multiples of `res` that covers `bounds` (minx, miny, maxx, maxy)."""
    x0 = np.floor(bounds[0] / res) * res
    y1 = np.ceil(bounds[3] / res) * res
    width = int(np.ceil((bounds[2] - x0) / res))
    height = int(np.ceil((y1 - bounds[1]) / res))
    return Affine(res, 0, x0, 0, -res, y1), (height, width)


def resample_to_grid(path: Path, band: int | str, transform: Affine, shape: tuple[int, int], crs: str,
                     resampling: Resampling = Resampling.nearest) -> np.ndarray:
    """Put one band of a raster on another grid (e.g. 4 m building years onto the 10 m S1 grid)."""
    with rasterio.open(path) as src:
        idx = band if isinstance(band, int) else list(src.descriptions).index(band) + 1
        out = np.full(shape, np.nan, dtype="float32")
        reproject(source=rasterio.band(src, idx), destination=out, dst_transform=transform, dst_crs=crs,
                  resampling=resampling, dst_nodata=np.nan)
    return out


def rasterize(geoms: list, transform: Affine, shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask of pixels whose centre falls inside any of `geoms` (same CRS as the grid)."""
    if not geoms:
        return np.zeros(shape, bool)
    return features.rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform,
                              fill=0, dtype="uint8").astype(bool)


def polygonize(labels: np.ndarray, transform: Affine) -> list[tuple[dict, int]]:
    """GeoJSON-like polygons for every labelled patch (label > 0), 8-connected like `min_area_filter`."""
    lab = np.asarray(labels, dtype="int32")
    return [(geom, int(v)) for geom, v in features.shapes(lab, mask=lab > 0, transform=transform,
                                                         connectivity=8)]


def overlay_png(layers: list[tuple[np.ndarray, tuple[int, int, int, int], bool]], transform: Affine, crs: str,
                out_png: Path, max_px: int = 4096) -> list[list[float]]:
    """Render boolean layers as one RGBA PNG in Web Mercator for a MapLibre image source.

    Args:
        layers: (mask, RGBA colour, hatched) drawn in order; hatched layers get diagonal stripes so
            they stay distinguishable in black-and-white prints (UIUX: built-up flood is hatched).
        transform, crs: Grid of the masks.
        out_png: Output file.
        max_px: Longest side of the PNG.

    Returns:
        Corner coordinates [[lon, lat] top-left, top-right, bottom-right, bottom-left] for MapLibre.
    """
    from PIL import Image  # Pillow ships with reportlab

    h, w = layers[0][0].shape
    left, top = transform * (0, 0)
    right, bottom = transform * (w, h)
    dst_t, dw, dh = calculate_default_transform(crs, WEB_MERCATOR, w, h, left=left, bottom=bottom,
                                                right=right, top=top)
    scale = max(1.0, max(dw, dh) / max_px)
    dw, dh = int(dw / scale), int(dh / scale)
    dst_t = dst_t * Affine.scale(scale)
    rgba = np.zeros((dh, dw, 4), dtype="uint8")
    yy, xx = np.mgrid[0:dh, 0:dw]
    stripes = ((xx + yy) // 3) % 3 == 0
    for mask, colour, hatched in layers:
        out = np.zeros((dh, dw), dtype="float32")
        reproject(mask.astype("float32"), out, src_transform=transform, src_crs=crs, dst_transform=dst_t,
                  dst_crs=WEB_MERCATOR, resampling=Resampling.average)
        on = out >= 0.25
        if hatched:
            on &= stripes
        rgba[on] = colour
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out_png, optimize=True)
    x0, y1 = dst_t * (0, 0)
    x1, y0 = dst_t * (dw, dh)
    lon0, lat0, lon1, lat1 = transform_bounds(WEB_MERCATOR, "EPSG:4326", x0, y0, x1, y1)
    return [[lon0, lat1], [lon1, lat1], [lon1, lat0], [lon0, lat0]]
