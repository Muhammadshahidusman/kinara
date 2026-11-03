"""Reporting units: the floodplain zone, tehsils and mouzas, all in EPSG:32643.

Tehsils come from the official boundary in data/reference. Mouzas come from an external file named
in settings (area.mouza_boundaries); when it is missing, mouza-level outputs say "not available"
instead of failing. Every unit is also clipped to the floodplain, because exposure is reported for
the part of each unit that lies inside it.
"""

from __future__ import annotations

import geopandas as gpd
import shapely

from kinara.config import Settings, get_logger
from kinara.geo.raster import find_export
from kinara.geo.vector import polygons_only

log = get_logger("kinara.units")

ZONE_EXPORT = "zones_hand_proxy.geojson"
MIN_PART_M2 = 100.0    # slivers smaller than this after clipping are dropped


def floodplain(cfg: Settings) -> gpd.GeoDataFrame:
    """Floodplain zone(s) from the Earth Engine export, dissolved per zone_id.

    Raises:
        FileNotFoundError: If zones_hand_proxy.geojson has not been downloaded yet.
    """
    path = find_export(cfg["paths"]["gee_exports"], ZONE_EXPORT)
    if path is None:
        raise FileNotFoundError(f"{ZONE_EXPORT} not found under {cfg['paths']['gee_exports']}; "
                                "run scripts/export_baseline.py --only zones and download it")
    z = gpd.read_file(path).to_crs(cfg["project"]["crs_analysis"])
    z = z.dissolve(by="zone_id", as_index=False)[["zone_id", "name", "definition", "geometry"]]
    z["geometry"] = shapely.make_valid(z.geometry.values)
    return z


def tehsils(cfg: Settings) -> gpd.GeoDataFrame:
    """Official tehsil polygons with columns unit_id, name."""
    t = gpd.read_file(cfg["area"]["tehsil_boundaries"]).to_crs(cfg["project"]["crs_analysis"])
    name = cfg["area"].get("tehsil_name_field", "tehsil")
    t = t.rename(columns={name: "name"})[["name", "geometry"]]
    t["unit_id"] = "T-" + t["name"].str.replace(" ", "_")
    return t[["unit_id", "name", "geometry"]]


def mouzas(cfg: Settings) -> gpd.GeoDataFrame | None:
    """Mouza polygons with unit_id, name, name_ur, tehsil; None when the file is not configured or absent."""
    path = cfg["area"].get("mouza_boundaries")
    if not path or not path.exists():
        log.warning("mouza boundaries not available; mouza fields will be empty")
        return None
    f = cfg["area"]["mouza_fields"]
    m = gpd.read_file(path).to_crs(cfg["project"]["crs_analysis"])
    m = m.rename(columns={f["id"]: "mouza_id", f["name"]: "name", f["name_ur"]: "name_ur", f["tehsil"]: "tehsil"})
    m["unit_id"] = "M-" + m["mouza_id"].astype(str)
    m["name"] = m["name"].fillna("Unnamed mouza " + m["mouza_id"].astype(str))
    m["geometry"] = shapely.make_valid(m.geometry.values)
    return m[["unit_id", "name", "name_ur", "tehsil", "geometry"]]


def clip_to(units: gpd.GeoDataFrame, zone: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The part of each unit inside the zone (units that miss the zone are dropped)."""
    outline = zone.geometry.union_all()
    c = units[units.intersects(outline)].copy()
    c["geometry"] = c.geometry.intersection(outline)
    c = polygons_only(c).dissolve(by="unit_id", as_index=False)
    return c[c.area >= MIN_PART_M2].reset_index(drop=True)
