"""Sentinel-1 monitoring inputs and Sentinel-2 evidence chips, server-side.

The change RULE is not here: Earth Engine only assembles the radar images (a linear-mean
baseline and the newest passes of one relative orbit) and `scripts/detect_alerts.py` applies the
tested numpy rule `kinara.detect.change.persistent_increase` to the downloaded pixels. That keeps a
single copy of the alert rule.
"""

from __future__ import annotations

import datetime as dt

import ee

from kinara.gee.collections import S2_SR, s1_linear_mean_db, s1_vv
from kinara.gee.fetch import NODATA_I16

DB_SCALE = 100          # dB x 100 stored as int16 (0.01 dB steps, range +-327 dB)
S2_VIS = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 2500, "gamma": 1.2}
OUTLINE_HEX = "FFD400"


def orbit_passes(aoi: ee.Geometry, orbit: int, start: str, end: str) -> list[dict]:
    """Sentinel-1 passes of one relative orbit over aoi, oldest first.

    Returns:
        [{"day": "YYYY-MM-DD", "ids": [scene ids]}]: scenes on the same day form one pass.
    """
    col = s1_vv(aoi, start, end, orbit)
    info = ee.Dictionary({"t": col.aggregate_array("system:time_start"),
                          "id": col.aggregate_array("system:index")}).getInfo()
    days: dict[str, list[str]] = {}
    for t, sid in sorted(zip(info["t"], info["id"], strict=True)):
        day = dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat()
        days.setdefault(day, []).append(sid)
    return [{"day": d, "ids": ids} for d, ids in sorted(days.items())]


def _next_day(day: str) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()


def pass_image(aoi: ee.Geometry, orbit: int, day: str) -> ee.Image:
    """VV (dB) of one pass: the same-day scenes of the orbit, mosaicked."""
    return s1_vv(aoi, day, _next_day(day), orbit).mosaic().rename("VV")


def change_stack(aoi: ee.Geometry, orbit: int, pass_days: list[str], baseline: tuple[str, str]) -> ee.Image:
    """Bands base, p0..pN-1 (oldest pass first) as int16 dB x 100, NODATA_I16 where masked."""
    base = s1_linear_mean_db(s1_vv(aoi, baseline[0], baseline[1], orbit)).rename("base")
    bands = [base] + [pass_image(aoi, orbit, d).rename(f"p{i}") for i, d in enumerate(pass_days)]
    return ee.Image.cat(bands).multiply(DB_SCALE).round().toInt16().unmask(NODATA_I16)


def baseline_ids(aoi: ee.Geometry, orbit: int, baseline: tuple[str, str]) -> list[str]:
    """Scene ids in the baseline window (provenance)."""
    return s1_vv(aoi, baseline[0], baseline[1], orbit).aggregate_array("system:index").getInfo()


def pass_means(alerts: ee.FeatureCollection, aoi: ee.Geometry, orbit: int, days: list[str]) -> ee.FeatureCollection:
    """Mean VV (dB, averaged in linear power) inside each alert for each pass day: the sparkline.

    Properties d0..dN-1 follow the order of `days`.
    """
    imgs = [ee.Image(10).pow(pass_image(aoi, orbit, d).divide(10)).rename(f"d{i}") for i, d in enumerate(days)]
    means = ee.Image.cat(imgs).reduceRegions(collection=alerts, reducer=ee.Reducer.mean(), scale=10)
    names = [f"d{i}" for i in range(len(days))]

    def to_db(f: ee.Feature) -> ee.Feature:
        return f.set(ee.Dictionary.fromLists(names, [
            ee.Algorithms.If(f.get(n), ee.Number(f.get(n)).log10().multiply(10), None) for n in names]))

    return means.map(to_db)


def s2_best_scene(region: ee.Geometry, start: str, end: str) -> ee.Image | None:
    """Least cloudy Sentinel-2 scene over region in [start, end), or None (properties kept)."""
    col = (ee.ImageCollection(S2_SR).filterBounds(region).filterDate(start, end)
           .sort("CLOUDY_PIXEL_PERCENTAGE"))
    return ee.Image(col.first()) if col.size().getInfo() else None


def s2_chip(scene: ee.Image, outline: ee.Geometry, region: ee.Geometry) -> ee.Image:
    """True-colour scene with the alert outline drawn in yellow (visible in colour and greyscale)."""
    rgb = scene.visualize(**S2_VIS)
    edge = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(outline)]), 1, 2)
    return rgb.blend(edge.visualize(palette=[OUTLINE_HEX])).clip(region)
