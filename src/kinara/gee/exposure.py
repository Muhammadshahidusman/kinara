"""Exposure: buildings inside zones, and building year-of-appearance.

`footprint_stats` is adapted from LPVIS scripts/05c_building_morphology.py (morph): the same Open
Buildings v3 reducers, cut down to what PDMA needs per zone or mouza.
"""

from __future__ import annotations

import ee

from kinara.gee.collections import open_buildings_v3, open_buildings_year

SMALL_M2 = 60     # footprints under this are usually katcha / informal dwellings


def footprint_stats(feature: ee.Feature, min_confidence: float = 0.75) -> ee.Feature:
    """Building count, footprint area and small-building share inside one polygon."""
    g = feature.geometry()
    ha = g.area(10).divide(1e4)
    b = open_buildings_v3(g, min_confidence)
    n = b.size()
    total = ee.Number(ee.Algorithms.If(n.gt(0), b.aggregate_sum("area_in_meters"), 0))
    small = b.filter(ee.Filter.lt("area_in_meters", SMALL_M2)).size()
    return feature.set({
        "bld_n": n,
        "bld_per_ha": n.divide(ha),
        "bld_area_m2": total,
        "bld_cover": total.divide(ha.multiply(1e4)),
        "bld_small_share": ee.Algorithms.If(n.gt(0), small.divide(n.max(1)), None),
    })


def footprint_points(aoi: ee.Geometry, min_confidence: float = 0.75) -> ee.FeatureCollection:
    """Open Buildings v3 footprints touching aoi as centroid properties (lon, lat, area, confidence).

    Same selection as `footprint_stats`, so the local counts match exposure_zones.csv.
    """
    def centroid(f: ee.Feature) -> ee.Feature:
        xy = f.geometry().centroid(1).coordinates()
        return ee.Feature(None, {"lon": xy.get(0), "lat": xy.get(1), "area_m2": f.get("area_in_meters"),
                                 "confidence": f.get("confidence")})

    return open_buildings_v3(aoi, min_confidence).map(centroid)


def population(units: ee.FeatureCollection, dataset: str, year: int) -> ee.FeatureCollection:
    """Sum of WorldPop people per unit polygon (property `pop_est`), at the dataset's 100 m scale."""
    pop = ee.ImageCollection(dataset).filter(ee.Filter.eq("year", year)).filter(
        ee.Filter.eq("country", "PAK")).mosaic()
    return pop.reduceRegions(collection=units, reducer=ee.Reducer.sum().setOutputs(["pop_est"]), scale=100)


def first_built_year(first: int, last: int, threshold: float) -> ee.Image:
    """Year each pixel first crossed the building_presence threshold (masked where never built).

    Pixels already built in `first` get the value `first`, meaning "built on or before".
    """
    years = ee.List.sequence(first, last)

    def year_img(y):
        y = ee.Number(y)
        built = open_buildings_year_ee(y).select("building_presence").gte(threshold)
        return ee.Image.constant(y).toInt16().updateMask(built).rename("first_year")

    return ee.ImageCollection(years.map(year_img)).min()


def open_buildings_year_ee(year: ee.Number) -> ee.Image:
    """Server-side year filter for use inside ee.List.map (year is an ee.Number there)."""
    start = ee.Date.fromYMD(year, 1, 1).millis().divide(1000)
    end = ee.Date.fromYMD(year.add(1), 1, 1).millis().divide(1000)
    col = (ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1")
           .filter(ee.Filter.gte("inference_time_epoch_s", start))
           .filter(ee.Filter.lt("inference_time_epoch_s", end)))
    return col.mosaic().unmask(0)


__all__ = ["first_built_year", "footprint_points", "footprint_stats", "open_buildings_year",
           "open_buildings_year_ee", "population"]
