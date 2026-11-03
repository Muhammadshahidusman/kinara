"""August 2025 flood extent from Sentinel-1, server-side.

Same rule as kinara.detect.change.flood_mask (tested there on arrays):
  open land : VV after <= open_water_max_db AND at least open_water_drop_db darker than before
  built-up  : at least urban_rise_db BRIGHTER than before (double bounce between water and walls)
"""

from __future__ import annotations

import ee

from kinara.config import Settings
from kinara.gee.collections import open_buildings_year, s1_linear_mean_db, s1_vv


def flood_extent(aoi: ee.Geometry, cfg: Settings, orbit: int | None = None) -> ee.Image:
    """Bands: open (1/0), urban (1/0), flooded (1/0), diff_db."""
    ev, fm = cfg["flood_event"], cfg["flood_mapping"]
    before = s1_linear_mean_db(s1_vv(aoi, ev["pre_start"], ev["pre_end"], orbit))
    after = s1_linear_mean_db(s1_vv(aoi, ev["event_start"], ev["event_end"], orbit))
    diff = after.subtract(before).rename("diff_db")
    built = open_buildings_year(cfg["buildings"]["last_year"]).select("building_presence") \
        .gte(cfg["buildings"]["presence_threshold"]) \
        .reproject(crs=cfg["project"]["crs_analysis"], scale=10)
    open_w = built.Not().And(after.lte(fm["open_water_max_db"])).And(diff.lte(-fm["open_water_drop_db"]))
    urban = built.And(diff.gte(fm["urban_rise_db"]))
    return ee.Image.cat(open_w.rename("open"), urban.rename("urban"),
                        open_w.Or(urban).rename("flooded"), diff).clip(aoi)


def sample_backscatter(points: ee.FeatureCollection, aoi: ee.Geometry, cfg: Settings,
                       orbit: int | None = None) -> ee.FeatureCollection:
    """Before / after VV (dB) and built-up flag at reference points, for threshold calibration.

    Uses exactly the composites of `flood_extent`, so calibrated thresholds apply to it unchanged.
    Properties added: before_db, after_db, built (0/1).
    """
    ev = cfg["flood_event"]
    before = s1_linear_mean_db(s1_vv(aoi, ev["pre_start"], ev["pre_end"], orbit)).rename("before_db")
    after = s1_linear_mean_db(s1_vv(aoi, ev["event_start"], ev["event_end"], orbit)).rename("after_db")
    built = open_buildings_year(cfg["buildings"]["last_year"]).select("building_presence") \
        .gte(cfg["buildings"]["presence_threshold"]).reproject(crs=cfg["project"]["crs_analysis"], scale=10) \
        .rename("built")
    return ee.Image.cat(before, after, built).sampleRegions(collection=points, scale=10, geometries=False)


def event_scene_ids(aoi: ee.Geometry, cfg: Settings, orbit: int | None = None) -> ee.Dictionary:
    """IDs of the Sentinel-1 scenes `flood_extent` actually used, for the provenance record.

    Args:
        aoi: Study area.
        cfg: Settings (flood_event windows).
        orbit: The same relative orbit passed to `flood_extent`; None means all orbits.

    Returns:
        ee.Dictionary with lists 'pre' (before window) and 'event' (flood window).
    """
    ev = cfg["flood_event"]
    return ee.Dictionary({
        "pre": s1_vv(aoi, ev["pre_start"], ev["pre_end"], orbit).aggregate_array("system:index"),
        "event": s1_vv(aoi, ev["event_start"], ev["event_end"], orbit).aggregate_array("system:index"),
    })
