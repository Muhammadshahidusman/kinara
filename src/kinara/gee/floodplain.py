"""Floodplain zone, HAND proxy (from the Ravi_Floodplain spike script).

Land within `river_buffer_m` of the Ravi channel AND with Height Above Nearest Drainage below
`hand_max_m`. This is a first operational definition. The bund-to-river polygon is planned next
because officials recognise the bunds. The 2025 flood extent is never used to draw the floodplain.
"""

from __future__ import annotations

import ee

from kinara.config import Settings

MERIT_HYDRO = "MERIT/Hydro/v1_0_1"
HYDRO_RIVERS = "WWF/HydroSHEDS/v1/FreeFlowingRivers"


def ravi_reaches(aoi: ee.Geometry, min_upland_km2: float) -> ee.FeatureCollection:
    """HydroSHEDS reaches near the district with a large upstream area (the Ravi, not the drains)."""
    return (ee.FeatureCollection(HYDRO_RIVERS).filterBounds(aoi.buffer(20000))
            .filter(ee.Filter.gte("UPLAND_SKM", min_upland_km2)))


def hand_proxy_mask(aoi: ee.Geometry, cfg: Settings) -> ee.Image:
    """Self-masked image: 1 inside the floodplain proxy."""
    fp = cfg["floodplain"]
    corridor = ravi_reaches(aoi, fp["min_upland_km2"]).geometry().buffer(fp["river_buffer_m"], 100)
    corridor_img = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(corridor)]), 1)
    hand = ee.Image(MERIT_HYDRO).select("hnd")
    return hand.lte(fp["hand_max_m"]).And(corridor_img.eq(1)).selfMask().clip(aoi)


def hand_proxy_polygon(aoi: ee.Geometry, cfg: Settings) -> ee.Geometry:
    """Floodplain proxy as a geometry clipped to the district (90 m vectorisation, MERIT's resolution)."""
    return (hand_proxy_mask(aoi, cfg)
            .reduceToVectors(geometry=aoi, scale=90, geometryType="polygon", eightConnected=True,
                             labelProperty="fp", maxPixels=1e10)
            .geometry(100)
            .intersection(aoi, 100))
