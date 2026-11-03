"""Phase 2 baseline exports to Google Drive (folder from settings: gee.drive_folder).

  zones_hand_proxy            floodplain proxy polygon (GeoJSON)
  exposure_zones              Open Buildings v3 stats: floodplain vs rest of district (CSV)
  first_built_year            year each pixel first became built, 2016-2023 (GeoTIFF, floodplain only)
  flood_2025                  August 2025 flood extent: open / urban / flooded / diff_db (GeoTIFF)
Each export gets a <name>_provenance.csv.

Run:  uv run python scripts/export_baseline.py            (all)
      uv run python scripts/export_baseline.py --only flood --orbit 100
      uv run python scripts/export_baseline.py --status
Download the files into data/gee_exports when the tasks finish.
"""

from __future__ import annotations

import argparse

import ee

from kinara.config import load_settings
from kinara.gee import client, export
from kinara.gee.exposure import first_built_year, footprint_stats
from kinara.gee.flood import event_scene_ids, flood_extent
from kinara.gee.floodplain import hand_proxy_polygon

PARTS = ("zones", "exposure", "first_built", "flood")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=PARTS, default=list(PARTS))
    ap.add_argument("--orbit", type=int, default=None, help="Sentinel-1 relative orbit (see check_gee.py)")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    cfg = load_settings()
    client.init(cfg)
    if a.status:
        export.status()
        return

    aoi = client.district(cfg)
    fp = hand_proxy_polygon(aoi, cfg)
    b = cfg["buildings"]

    if "zones" in a.only:
        fc = ee.FeatureCollection([ee.Feature(fp, {"zone_id": "fp_hand", "name": "Floodplain (HAND proxy)",
                                                   "definition": "hand_proxy"})])
        export.table_to_drive(fc, "zones_hand_proxy", cfg, fmt="GeoJSON")

    if "exposure" in a.only:
        zones = ee.FeatureCollection([
            ee.Feature(fp, {"unit_id": "fp_hand", "name": "Floodplain (HAND proxy)"}),
            ee.Feature(aoi.difference(fp, 100), {"unit_id": "rest", "name": "Rest of district"}),
        ]).map(lambda f: footprint_stats(f, b["v3_min_confidence"]))
        export.table_to_drive(zones, "exposure_zones", cfg)

    if "first_built" in a.only:
        img = first_built_year(b["first_year"], b["last_year"], b["presence_threshold"]).clip(fp)
        export.image_to_drive(img, "first_built_year", fp, cfg, scale=4,
                              years=f"{b['first_year']}-{b['last_year']}")

    if "flood" in a.only:
        img = flood_extent(aoi, cfg, a.orbit).toFloat()
        scenes = event_scene_ids(aoi, cfg, a.orbit).getInfo()
        export.image_to_drive(img, "flood_2025", aoi, cfg, scale=10, orbit=a.orbit,
                              scenes_pre=scenes["pre"], scenes=scenes["event"])


if __name__ == "__main__":
    main()
