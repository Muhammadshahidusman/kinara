"""Direct downloads from Earth Engine into memory (no Google Drive round trip).

Used for small or medium results that the pipeline needs every run: footprint centroids, river
lines, per-unit population, Sentinel-1 pixel stacks over the floodplain and evidence chips.
Large one-off layers still go through `kinara.gee.export` to Drive.
"""

from __future__ import annotations

import io
import json
import time
import urllib.request
from collections.abc import Callable

import ee
import numpy as np
import pandas as pd

from kinara.config import get_logger

log = get_logger("kinara.gee.fetch")

NODATA_I16 = -32768
HTTP_TIMEOUT_S = 600
RETRIES = 4               # transient network / EE errors: try this many times in all
BACKOFF_S = 5.0           # wait 5, 10, 20 s between attempts

def with_retry[T](fn: Callable[[], T], what: str, retries: int = RETRIES, backoff_s: float = BACKOFF_S) -> T:
    """Call fn, retrying network and Earth Engine errors with exponential backoff.

    Raises:
        The last error if every attempt fails.
    """
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except (OSError, ee.EEException) as e:   # URLError and socket errors are OSError
            if attempt == retries:
                raise
            wait = backoff_s * 2 ** (attempt - 1)
            log.warning(f"{what} failed ({type(e).__name__}: {e}); retry {attempt}/{retries - 1} in {wait:.0f} s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def _get(url: str) -> bytes:
    """Download one Earth Engine URL (thumbnail or table)."""
    def once() -> bytes:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as r:  # noqa: S310 (EE https URL)
            return r.read()
    return with_retry(once, "download")


def table(fc: ee.FeatureCollection, selectors: list[str]) -> pd.DataFrame:
    """A FeatureCollection's properties as a DataFrame, in one streamed CSV request.

    Args:
        fc: Features to download (geometry is dropped; put coordinates in properties first).
        selectors: Property names to keep, in order.
    """
    url = fc.getDownloadURL(filetype="csv", selectors=selectors)
    df = pd.read_csv(io.BytesIO(_get(url)))
    log.info(f"downloaded {len(df):,} rows ({', '.join(selectors)})")
    return df


def geojson(fc: ee.FeatureCollection) -> dict:
    """Small FeatureCollection as a GeoJSON dict (getInfo; keep it under a few thousand vertices)."""
    out = fc.getInfo()
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": f["geometry"], "properties": f.get("properties", {})}
                         for f in out["features"]]}


def tiles(width: int, height: int, tile: int) -> list[tuple[int, int, int, int]]:
    """Split a width x height grid into (col0, row0, w, h) tiles of at most tile x tile pixels."""
    if tile <= 0:
        raise ValueError("tile must be positive")
    return [(c, r, min(tile, width - c), min(tile, height - r))
            for r in range(0, height, tile) for c in range(0, width, tile)]


def pixels(img: ee.Image, bands: list[str], x0: float, y_top: float, width: int, height: int, scale: float,
           crs: str, tile: int = 1024, keep: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Download int16 bands on a fixed UTM grid, tile by tile, with ee.data.computePixels.

    Args:
        img: Image whose `bands` are int16 with masked pixels already set to NODATA_I16.
        bands: Band names to fetch.
        x0, y_top: Upper-left corner of the grid (map units of `crs`).
        width, height: Grid size in pixels.
        scale: Pixel size (m).
        crs: e.g. "EPSG:32643".
        tile: Tile size in pixels (computePixels caps each response at about 48 MB).
        keep: Optional boolean (height, width) mask; tiles with no True pixel are skipped.

    Returns:
        {band: int16 array (height, width)} with NODATA_I16 where not downloaded or masked.
    """
    out = {b: np.full((height, width), NODATA_I16, dtype="int16") for b in bands}
    todo = [t for t in tiles(width, height, tile) if keep is None or keep[t[1]:t[1] + t[3], t[0]:t[0] + t[2]].any()]
    for i, (c, r, w, h) in enumerate(todo, 1):
        req = {
            "expression": img.select(bands),
            "fileFormat": "NUMPY_NDARRAY",
            "grid": {"dimensions": {"width": w, "height": h},
                     "affineTransform": {"scaleX": scale, "shearX": 0, "translateX": x0 + c * scale,
                                         "shearY": 0, "scaleY": -scale, "translateY": y_top - r * scale},
                     "crsCode": crs},
        }
        arr = with_retry(lambda req=req: ee.data.computePixels(req), f"pixels tile {i}")
        for b in bands:
            out[b][r:r + h, c:c + w] = arr[b]
        log.info(f"pixels tile {i}/{len(todo)} ({w}x{h})")
    return out


def thumbnail(img: ee.Image, region: ee.Geometry, px: int) -> bytes:
    """PNG bytes of an already-visualised (RGB) image over `region`."""
    url = img.getThumbURL({"region": region, "dimensions": px, "format": "png"})
    return _get(url)


def dumps_scene_list(ids: list[str]) -> str:
    """Compact JSON for scene id lists stored in CSV / JSON provenance."""
    return json.dumps(sorted(set(ids)))
