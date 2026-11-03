"""Earth Engine collections Kinara uses, prepared the same way every time.

Collection IDs (all open, public catalog):
  GOOGLE/Research/open-buildings-temporal/v1    annual building presence/height 2016-2023, 4 m effective
  GOOGLE/Research/open-buildings/v3/polygons    building footprints (about 2022-23 imagery)
  COPERNICUS/S1_GRD                             Sentinel-1 backscatter, dB, 12-day repeat
  COPERNICUS/S2_SR_HARMONIZED                   Sentinel-2 surface reflectance, 2022 offset already harmonised
  GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED      cloud mask for Sentinel-2
"""

from __future__ import annotations

import datetime as dt

import ee

OB_TEMPORAL = "GOOGLE/Research/open-buildings-temporal/v1"
OB_V3 = "GOOGLE/Research/open-buildings/v3/polygons"
S1_GRD = "COPERNICUS/S1_GRD"
S2_SR = "COPERNICUS/S2_SR_HARMONIZED"
CLOUD_SCORE_PLUS = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
CS_THRESHOLD = 0.6        # Cloud Score+ cs_cdf: keep pixels at or above this


def open_buildings_year(year: int) -> ee.Image:
    """Open Buildings Temporal mosaic for one year, unmasked to 0, native 0.5 m projection kept.

    Reused from LPVIS 05_gee_export.buildings_collection: each year's inference time is stamped at
    midnight US Pacific on 30 June, so match the whole UTC calendar year rather than one instant.
    """
    start = int(dt.datetime(year, 1, 1, tzinfo=dt.UTC).timestamp())
    end = int(dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC).timestamp())
    col = (ee.ImageCollection(OB_TEMPORAL)
           .filter(ee.Filter.gte("inference_time_epoch_s", start))
           .filter(ee.Filter.lt("inference_time_epoch_s", end)))
    return col.mosaic().unmask(0).setDefaultProjection(col.first().projection())


def open_buildings_v3(aoi: ee.Geometry, min_confidence: float = 0.75) -> ee.FeatureCollection:
    """Open Buildings v3 footprints inside aoi above a confidence cut-off."""
    return (ee.FeatureCollection(OB_V3).filterBounds(aoi)
            .filter(ee.Filter.gte("confidence", min_confidence)))


def s1_vv(aoi: ee.Geometry, start: str, end: str, orbit: int | None = None) -> ee.ImageCollection:
    """Sentinel-1 IW VV backscatter (dB) with a 3x3 focal median against speckle.

    Pass `orbit` (relativeOrbitNumber_start) to compare like with like: mixing orbits changes the
    viewing geometry and shows up as fake change.
    """
    col = (ee.ImageCollection(S1_GRD).filterBounds(aoi).filterDate(start, end)
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
           .select("VV"))
    if orbit is not None:
        col = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit))
    return col.map(lambda img: img.focalMedian(1.5, "square", "pixels").copyProperties(img, img.propertyNames()))


def s1_linear_mean_db(col: ee.ImageCollection) -> ee.Image:
    """Average dB images in linear power, return dB (averaging dB directly biases low)."""
    lin = col.map(lambda img: ee.Image(10).pow(img.divide(10)))
    return lin.mean().log10().multiply(10).rename("VV")


def s2_sr(aoi: ee.Geometry, start: str, end: str) -> ee.ImageCollection:
    """Sentinel-2 surface reflectance (harmonised) masked with Cloud Score+. Never re-apply the 2022 offset."""
    cs = ee.ImageCollection(CLOUD_SCORE_PLUS)

    def mask(img: ee.Image) -> ee.Image:
        score = img.linkCollection(cs, ["cs_cdf"]).select("cs_cdf")
        return img.updateMask(score.gte(CS_THRESHOLD)).divide(10000).copyProperties(img, ["system:time_start"])

    return ee.ImageCollection(S2_SR).filterBounds(aoi).filterDate(start, end).map(mask)
