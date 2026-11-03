"""Fetch the Earth Engine inputs the local pipeline needs, straight into data/interim (no Drive).

  buildings    Open Buildings v3 footprint centroids inside the floodplain   buildings_floodplain.csv
  river        HydroSHEDS Ravi reaches near the district                    river.geojson
  scenes       Sentinel-1 scenes behind flood_2025.tif (orbit from its provenance)  flood_2025_scenes.json
  population   WorldPop people per tehsil / mouza inside the floodplain     population_units.csv

Run:  uv run python scripts/fetch_inputs.py                 (all)
      uv run python scripts/fetch_inputs.py --only population
Then: uv run python scripts/build_exposure.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

import ee
import pandas as pd

from kinara import units
from kinara.config import load_settings
from kinara.gee import client, fetch
from kinara.gee.exposure import footprint_points, population
from kinara.gee.flood import event_scene_ids
from kinara.gee.floodplain import hand_proxy_polygon, ravi_reaches
from kinara.geo.raster import find_export

PARTS = ("buildings", "river", "scenes", "population")
SIMPLIFY_M = 20.0     # unit polygons sent to EE for population sums (100 m pixels)


def flood_orbit(cfg: dict) -> int | None:
    """Relative orbit recorded in flood_2025_provenance.csv (None if absent or all orbits)."""
    p = find_export(cfg["paths"]["gee_exports"], "flood_2025_provenance.csv")
    if p is None:
        return None
    v = pd.read_csv(p).get("orbit")
    return None if v is None or pd.isna(v.iloc[0]) else int(v.iloc[0])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=PARTS, default=list(PARTS))
    a = ap.parse_args()

    cfg = load_settings()
    client.init(cfg)
    out = cfg["paths"]["interim"]
    aoi = client.district(cfg)
    stamp = {"fetched_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "ee_version": ee.__version__}

    if "buildings" in a.only:
        fp = hand_proxy_polygon(aoi, cfg)
        conf = cfg["buildings"]["v3_min_confidence"]
        df = fetch.table(footprint_points(fp, conf), ["lon", "lat", "area_m2", "confidence"])
        df.to_csv(out / "buildings_floodplain.csv", index=False)
        (out / "buildings_floodplain.json").write_text(json.dumps(
            {**stamp, "source": "GOOGLE/Research/open-buildings/v3/polygons", "min_confidence": conf,
             "zone": "hand_proxy", "n": len(df)}, indent=1), encoding="utf-8")
        print(f"buildings: {len(df):,} footprints in the floodplain")

    if "river" in a.only:
        gj = fetch.geojson(ravi_reaches(aoi, cfg["floodplain"]["min_upland_km2"])
                           .select(["HYRIV_ID", "UPLAND_SKM"], retainGeometry=True))
        (out / "river.geojson").write_text(json.dumps(gj), encoding="utf-8")
        print(f"river: {len(gj['features'])} reaches")

    if "scenes" in a.only:
        orbit = flood_orbit(cfg)
        sc = event_scene_ids(aoi, cfg, orbit).getInfo()
        (out / "flood_2025_scenes.json").write_text(json.dumps({**stamp, "orbit": orbit, **sc}, indent=1),
                                                    encoding="utf-8")
        print(f"scenes: orbit {orbit}, {len(sc['pre'])} before, {len(sc['event'])} during the flood")

    if "population" in a.only:
        zone = units.floodplain(cfg)
        parts = [units.clip_to(units.tehsils(cfg), zone)]
        m = units.mouzas(cfg)
        if m is not None:
            parts.append(units.clip_to(m, zone))
        u = pd.concat([p[["unit_id", "geometry"]] for p in parts] + [zone.rename(columns={"zone_id": "unit_id"})
                                                                     [["unit_id", "geometry"]]])
        u["geometry"] = u.geometry.simplify(SIMPLIFY_M)
        fc = ee.FeatureCollection(json.loads(u.to_crs("EPSG:4326").to_json(drop_id=True)))
        e = cfg["exposure"]
        df = fetch.table(population(fc, e["population_dataset"], e["population_year"]), ["unit_id", "pop_est"])
        df["pop_source"] = f"WorldPop R2025A, {e['population_year']} (100 m)"
        df.to_csv(out / "population_units.csv", index=False)
        total = df.loc[df["unit_id"].isin(zone["zone_id"]), "pop_est"].sum()
        print(f"population: {len(df)} units, floodplain total about {total:,.0f} people")


if __name__ == "__main__":
    main()
