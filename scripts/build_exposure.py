"""Build the exposure layers and tables the API serves (local only, no Earth Engine).

Reads  data/gee_exports  zones_hand_proxy.geojson, first_built_year.tif, flood_2025.tif (+ provenance)
       data/interim      buildings_floodplain.csv, river.geojson, flood_2025_scenes.json,
                         population_units.csv (optional)
Writes data/processed    zones, tehsils, mouzas, river, cells (.geojson), flood_2025.png,
                         exposure.json, summary.json

Run:  uv run python scripts/build_exposure.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from kinara import exposure, units
from kinara.config import get_logger, load_settings
from kinara.geo.raster import find_export, overlay_png, read_band
from kinara.geo.vector import accounting, majority_join

log = get_logger("kinara.build_exposure")

WEB = "EPSG:4326"
SIMPLIFY_M = 15.0          # display geometries only; all numbers use the unsimplified polygons
OPEN_RGBA = (43, 108, 176, 115)     # --river at 45% opacity (UIUX.md)
URBAN_RGBA = (23, 64, 120, 230)     # darker river blue, hatched


def write_geojson(gdf: gpd.GeoDataFrame, path: Path, simplify_m: float = SIMPLIFY_M) -> None:
    """Simplify in metres, then write WGS 84 GeoJSON with 6-decimal coordinates (about 0.1 m)."""
    g = gdf.copy()
    if simplify_m:
        g["geometry"] = g.geometry.simplify(simplify_m, preserve_topology=True)
    g = g.to_crs(WEB)
    g["geometry"] = shapely.set_precision(g.geometry.values, 1e-6)    # about 0.1 m; halves the file size
    path.write_text(g.to_json(drop_id=True), encoding="utf-8")
    log.info(f"wrote {path.name} ({len(g):,} features, {path.stat().st_size / 1e6:.1f} MB)")


def provenance_value(cfg: dict, name: str, key: str) -> str | None:
    """One field of an export's _provenance.csv."""
    p = find_export(cfg["paths"]["gee_exports"], f"{name}_provenance.csv")
    if p is None:
        return None
    df = pd.read_csv(p)
    return None if key not in df or pd.isna(df[key].iloc[0]) else str(df[key].iloc[0])


def main() -> None:
    cfg = load_settings()
    crs = cfg["project"]["crs_analysis"]
    interim, out = cfg["paths"]["interim"], cfg["paths"]["processed"]
    b, e = cfg["buildings"], cfg["exposure"]

    zone = units.floodplain(cfg)
    zone["area_km2"] = (zone.area / 1e6).round(2)
    teh = units.tehsils(cfg)
    mou = units.mouzas(cfg)

    # ---- buildings: first-built year and flooded flag per footprint
    df = pd.read_csv(interim / "buildings_floodplain.csv")
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=WEB).to_crs(crs)
    years = read_band(find_export(cfg["paths"]["gee_exports"], "first_built_year.tif"), 1)
    flood_path = find_export(cfg["paths"]["gee_exports"], "flood_2025.tif")
    flood = read_band(flood_path, "flooded")
    bld = exposure.attach_rasters(pts, years[:2], flood[:2], window=e["sample_window_px"])
    log.info(f"buildings: {len(bld):,}; year unknown {bld.first_year.isna().mean():.1%}; "
             f"flooded {bld.flooded.mean():.1%}")
    bld.drop(columns="geometry").to_csv(interim / "buildings_attributed.csv", index=False)

    # ---- per-unit tables
    rows: list[dict] = []
    for z in zone.itertuples():
        rows.append({"unit_id": z.zone_id, "unit_type": "zone", "name": z.name, "area_km2": z.area_km2,
                     **exposure.unit_counts(bld, b["first_year"])})
    teh_fp = units.clip_to(teh, zone)
    tc = exposure.by_unit(bld, teh_fp, "unit_id", b["first_year"])
    for t in teh_fp.itertuples():
        rows.append({"unit_id": t.unit_id, "unit_type": "tehsil", "name": t.name,
                     "area_km2": round(t.geometry.area / 1e6, 2), **tc.loc[t.unit_id].to_dict()})
    mou_fp = None
    if mou is not None:
        mou_fp = units.clip_to(mou, zone)
        # tehsil from the OFFICIAL tehsil layer (majority overlap) so mouza and tehsil tables agree;
        # n_tehsils flags mouza polygons that cross tehsil boundaries (the two layers disagree)
        mou_fp["tehsil_src"] = mou_fp["tehsil"]
        mou_fp["tehsil"] = majority_join(mou_fp, teh_fp.rename(columns={"name": "teh"}), ["teh"], "unit_id")[
            "teh"].to_numpy()
        ov = gpd.overlay(mou_fp[["unit_id", "geometry"]], teh_fp[["name", "geometry"]], how="intersection")
        ov = ov[ov.area >= units.MIN_PART_M2 * 100]       # ignore slivers under 1 ha
        mou_fp["n_tehsils"] = mou_fp["unit_id"].map(ov.groupby("unit_id").size()).fillna(1).astype(int)
        mc = exposure.by_unit(bld, mou_fp, "unit_id", b["first_year"])
        for m in mou_fp.itertuples():
            rows.append({"unit_id": m.unit_id, "unit_type": "mouza", "name": m.name, "name_ur": m.name_ur,
                         "tehsil": m.tehsil, "n_tehsils": m.n_tehsils, "area_km2": round(m.geometry.area / 1e6, 2),
                         **mc.loc[m.unit_id].to_dict()})
        accounting(log, "mouzas in floodplain", len(mou), len(mou_fp))
    ex = pd.DataFrame(rows)
    pop_file = interim / "population_units.csv"
    if pop_file.exists():
        pop = pd.read_csv(pop_file)
        ex = ex.merge(pop, on="unit_id", how="left")
        ex["pop_est"] = ex["pop_est"].round(-1)       # an estimate: never show it to the last person
    else:
        ex["pop_est"], ex["pop_source"] = None, None
    ex = ex.astype(object).where(ex.notna(), None)
    (out / "exposure.json").write_text(json.dumps(ex.to_dict("records"), ensure_ascii=False, indent=0,
                                                  default=_jsonable), encoding="utf-8")
    log.info(f"wrote exposure.json ({len(ex)} units)")

    # ---- map layers
    write_geojson(zone, out / "zones.geojson")
    write_geojson(teh.assign(area_km2=(teh.area / 1e6).round(1)), out / "tehsils.geojson")
    if mou is not None:
        near = mou[mou.intersects(zone.geometry.union_all().buffer(2000))]
        write_geojson(near, out / "mouzas.geojson")
    river = gpd.read_file(interim / "river.geojson")
    river.to_file(out / "river.geojson", driver="GeoJSON")
    c = exposure.cells(bld, e["cell_m"], b["first_year"], b["last_year"], crs)
    if mou_fp is not None and len(c):
        cent = c.copy()
        cent["geometry"] = c.geometry.centroid
        j = gpd.sjoin(cent, mou_fp[["name", "geometry"]], how="left", predicate="within")
        c["mouza"] = j[~j.index.duplicated()]["name"].reindex(c.index)
    write_geojson(c, out / "cells.geojson", simplify_m=0)

    # flood overlay: open-land flood solid, built-up flood hatched (prints in black and white)
    opn, ft, fcrs = read_band(flood_path, "open")
    urb, _, _ = read_band(flood_path, "urban")
    corners = overlay_png([(np.nan_to_num(opn) >= 0.5, OPEN_RGBA, False),
                           (np.nan_to_num(urb) >= 0.5, URBAN_RGBA, True)], ft, fcrs, out / "flood_2025.png")

    # ---- summary (headline numbers + where every number came from)
    fp = ex[ex.unit_type == "zone"].iloc[0]
    scenes_file = interim / "flood_2025_scenes.json"
    scenes = json.loads(scenes_file.read_text(encoding="utf-8")) if scenes_file.exists() else {}
    px_ha = abs(ft.a * ft.e) / 1e4
    summary = {
        "built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "floodplain": {"definition": cfg["floodplain"]["definition"], "label": str(zone.iloc[0]["name"]),
                       "area_km2": float(zone.area_km2.sum()), **{k: cfg["floodplain"][k] for k in
                                                                  ("hand_max_m", "river_buffer_m")}},
        "buildings": {"n": int(fp.bld_n), "post2016_n": int(fp.bld_post2016_n),
                      "year_unknown_n": int(fp.bld_year_unknown_n), "flooded_2025_n": int(fp.bld_flooded_2025),
                      "source": "Open Buildings v3 (footprints, imagery about 2022-23) and 2.5D Temporal "
                                f"({b['first_year']}-{b['last_year']})",
                      "min_confidence": b["v3_min_confidence"], "presence_threshold": b["presence_threshold"],
                      "export_check_n": _export_bld_n(cfg)},
        "population": {"n": None if fp.pop_est is None else int(fp.pop_est), "source": fp.pop_source},
        "flood_2025": {"open_ha": round(float(np.nansum(opn >= 0.5)) * px_ha),
                       "urban_ha": round(float(np.nansum(urb >= 0.5)) * px_ha),
                       "orbit": scenes.get("orbit") or provenance_value(cfg, "flood_2025", "orbit"),
                       "scenes_pre": scenes.get("pre", []), "scenes_event": scenes.get("event", []),
                       "thresholds": cfg["flood_mapping"], "calibrated": False,
                       "overlay": {"url": "/api/layers/flood_2025.png", "coordinates": corners}},
        "data_dates": {"buildings": f"{b['last_year']}", "flood": cfg["flood_event"]["peak_date"]},
        "mouzas_available": mou is not None,
    }
    calib = interim / "flood_calibration.json"
    if calib.exists():
        summary["flood_2025"]["calibrated"] = json.loads(calib.read_text(encoding="utf-8")).get("applied", False)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=_jsonable), encoding="utf-8")
    print(f"Floodplain {summary['floodplain']['area_km2']:.1f} km2: {fp.bld_n:,} estimated buildings, "
          f"{fp.bld_post2016_n:,} first seen after {b['first_year']}, {fp.bld_flooded_2025:,} in the Aug 2025 "
          f"flood extent (Open Buildings export says {summary['buildings']['export_check_n']})")


def _export_bld_n(cfg: dict) -> int | None:
    """Building count in exposure_zones.csv (Earth Engine) as a cross-check of the local count."""
    p = find_export(cfg["paths"]["gee_exports"], "exposure_zones.csv")
    if p is None:
        return None
    df = pd.read_csv(p)
    r = df[df["unit_id"] == "fp_hand"]
    return int(r["bld_n"].iloc[0]) if len(r) else None


def _jsonable(v: object) -> object:
    """numpy scalars to Python for json.dumps."""
    return v.item() if hasattr(v, "item") else str(v)


if __name__ == "__main__":
    main()
