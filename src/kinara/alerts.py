"""Turn a detection mask into candidate alerts (TRD.md section 5.4, steps 4 to 6).

  patches   labelled patches -> polygons with area and per-patch radar statistics
  attach    tehsil / mouza by majority overlap, distance to the river, flooded-2025 share
  dedupe    match against existing alerts (IoU above a threshold, or touching within a buffer)
  ids       K-<year>-<4-digit sequence>
Wording rule: these are CANDIDATE new construction. Nothing here judges legality.
"""

from __future__ import annotations

import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from affine import Affine
from scipy import ndimage
from shapely.geometry import shape

from kinara.exposure import kanal
from kinara.geo.raster import polygonize
from kinara.geo.vector import majority_join

ID_RE = re.compile(r"^K-(\d{4})-(\d{4,})$")


def patches(labels: np.ndarray, transform: Affine, crs: str, pixel_m: float,
            stats: dict[str, np.ndarray] | None = None) -> gpd.GeoDataFrame:
    """One polygon per labelled patch with its area and the mean of each `stats` array inside it.

    Args:
        labels: (H, W) int labels from `min_area_filter` (0 = background).
        transform: Grid transform (UTM 43N).
        crs: Grid CRS.
        pixel_m: Pixel size, for the area (pixel count x pixel area, matching the 0.5 ha rule).
        stats: Optional arrays (H, W); NaN-aware mean per patch is stored under the same key.

    Returns:
        GeoDataFrame with label, area_ha, n_px, <stats...>, geometry (MultiPolygon), in `crs`.
    """
    n = int(labels.max())
    if n == 0:
        return gpd.GeoDataFrame(columns=["label", "area_ha", "n_px", "geometry"], geometry="geometry", crs=crs)
    parts = polygonize(labels, transform)
    g = gpd.GeoDataFrame({"label": [v for _, v in parts]}, geometry=[shape(p) for p, _ in parts], crs=crs)
    g = g.dissolve(by="label", as_index=False)
    g["geometry"] = [shapely.MultiPolygon([p]) if p.geom_type == "Polygon" else p for p in g.geometry]
    idx = g["label"].to_numpy()
    n_px = ndimage.sum(np.ones_like(labels), labels, idx)
    g["n_px"] = n_px.astype(int)
    g["area_ha"] = (n_px * pixel_m**2 / 10_000).round(2)
    for key, arr in (stats or {}).items():
        a = np.asarray(arr, float)
        ok = ~np.isnan(a)
        s = ndimage.sum(np.where(ok, a, 0), labels, idx)
        c = ndimage.sum(ok, labels, idx)
        g[key] = np.where(c > 0, s / np.maximum(c, 1), np.nan).round(2)
    return g


def attach(alerts: gpd.GeoDataFrame, tehsils: gpd.GeoDataFrame, mouzas: gpd.GeoDataFrame | None,
           river: gpd.GeoDataFrame | None, flooded: np.ndarray | None, labels: np.ndarray | None,
           flooded_share: float) -> gpd.GeoDataFrame:
    """Add tehsil, mouza (+ Urdu name), distance_river_m and flooded_2025 / flooded_share.

    All inputs must share the alerts' metric CRS. `flooded` and `labels` are on the detection grid.
    Fields that can't be computed are set to None, which the UI shows as "not available".
    """
    out = alerts.copy()
    key = "label"
    t = majority_join(out, tehsils.rename(columns={"name": "tehsil"}), ["tehsil"], key)
    out["tehsil"] = t["tehsil"].to_numpy()
    if mouzas is not None:
        m = majority_join(out, mouzas.rename(columns={"name": "mouza", "name_ur": "mouza_ur"}),
                          ["mouza", "mouza_ur"], key)
        out["mouza"], out["mouza_ur"] = m["mouza"].to_numpy(), m["mouza_ur"].to_numpy()
    else:
        out["mouza"], out["mouza_ur"] = None, None
    if river is not None and len(river):
        line = river.geometry.union_all()
        out["distance_river_m"] = out.geometry.distance(line).round().astype(int)
    else:
        out["distance_river_m"] = None
    if flooded is not None and labels is not None:
        share = ndimage.mean(np.nan_to_num(flooded) >= 0.5, labels, out["label"].to_numpy())
        out["flooded_share"] = np.round(share, 2)
        out["flooded_2025"] = share >= flooded_share
    else:
        out["flooded_share"], out["flooded_2025"] = None, None
    cols = [c for c in out.columns if c != "geometry"]
    out[cols] = out[cols].astype(object).where(out[cols].notna(), None)
    return out


def iou(a: shapely.Geometry, b: shapely.Geometry) -> float:
    """Intersection over union of two polygons (0 when they don't overlap)."""
    inter = a.intersection(b).area
    return 0.0 if inter == 0 else inter / a.union(b).area


def dedupe(new: gpd.GeoDataFrame, existing: gpd.GeoDataFrame, min_iou: float,
           buffer_m: float) -> tuple[list[int], dict[int, str]]:
    """Split new patches into genuinely new ones and repeats of existing alerts.

    A repeat is a patch whose IoU with an existing alert exceeds `min_iou`, or that touches an
    existing alert within `buffer_m` (construction tends to grow outward from the first detection).

    Args:
        new: Candidate patches (metric CRS), default RangeIndex.
        existing: Existing alerts in the same CRS with an `alert_id` column.

    Returns:
        (row positions of genuinely new patches, {row position: matching alert_id})
    """
    if existing is None or existing.empty:
        return list(range(len(new))), {}
    tree = shapely.STRtree(existing.geometry.values)
    fresh, repeats = [], {}
    for i, g in enumerate(new.geometry.values):
        hits = tree.query(g.buffer(buffer_m))
        best, best_score = None, 0.0
        for h in hits:
            eg = existing.geometry.values[h]
            score = iou(g, eg)
            if score > min_iou or g.distance(eg) <= buffer_m:
                score = max(score, 1e-9)
                if score > best_score:
                    best, best_score = existing["alert_id"].values[h], score
        if best is None:
            fresh.append(i)
        else:
            repeats[i] = str(best)
    return fresh, repeats


def next_ids(existing: list[str], year: int, n: int) -> list[str]:
    """Next n alert ids for `year`, continuing the highest existing sequence for that year."""
    seq = [int(m.group(2)) for m in (ID_RE.match(x) for x in existing) if m and int(m.group(1)) == year]
    start = max(seq, default=0) + 1
    return [f"K-{year}-{i:04d}" for i in range(start, start + n)]


def features(alerts: gpd.GeoDataFrame, ids: list[str], marla_sqft: float, kanal_marla: int,
             extra: dict | None = None) -> list[dict]:
    """GeoJSON features (EPSG:4326) with the alert properties the API and evidence card use."""
    web = alerts.to_crs("EPSG:4326")
    cent = alerts.geometry.centroid.to_crs("EPSG:4326")
    feats = []
    for (_, r), aid, c in zip(web.iterrows(), ids, cent, strict=True):
        props = {k: _plain(v) for k, v in r.items() if k not in ("geometry", "label", "n_px")}
        props.update({"alert_id": aid, "kind": "new_construction", "status": "new",
                      "area_kanal": round(kanal(float(r["area_ha"]), marla_sqft, kanal_marla), 1),
                      "lon": round(c.x, 6), "lat": round(c.y, 6), **(extra or {})})
        feats.append({"type": "Feature", "geometry": json.loads(shapely.to_geojson(r.geometry)),
                      "properties": props})
    return feats


def scene_day(scene_id: str) -> str:
    """Acquisition day of a Sentinel-1 scene id (S1A_IW_GRDH_1SDV_20250711T010809_...) as YYYY-MM-DD."""
    d = scene_id.split("_")[4][:8]
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def last_processed(runs: list[dict], orbit: int) -> str:
    """Newest pass day already processed successfully for this orbit ('' if none)."""
    days = [r.get("orbits", {}).get(str(orbit), {}).get("newest_pass", "") for r in runs if r.get("ok")]
    return max(days, default="")


def existing_gdf(fc: dict, crs: str) -> gpd.GeoDataFrame:
    """Existing alerts (GeoJSON FeatureCollection from the store) as a metric GeoDataFrame."""
    feats = [f for f in fc.get("features", []) if f.get("geometry")]
    if not feats:
        return gpd.GeoDataFrame(columns=["alert_id", "geometry"], geometry="geometry", crs=crs)
    g = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326").to_crs(crs)
    g["geometry"] = shapely.make_valid(g.geometry.values)
    return g


def _plain(v: object) -> object:
    """numpy / pandas scalars to plain Python for JSON."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, np.bool_ | bool):
        return bool(v)
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat()
    return v
