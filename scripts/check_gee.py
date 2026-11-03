"""Check Earth Engine access and the datasets Kinara needs. Prints counts only; exports nothing.

Run:  uv run python scripts/check_gee.py
"""

from __future__ import annotations

import ee

from kinara.config import load_settings
from kinara.gee import client
from kinara.gee.collections import OB_TEMPORAL, s1_vv


def main() -> None:
    cfg = load_settings()
    client.init(cfg)
    aoi = client.district(cfg)
    km2 = client.check_area(aoi, cfg)
    print(f"District area: {km2:,.1f} km2 (official boundary: {cfg['area']['district_area_km2']})")

    # one server-side request, no per-item getInfo loop
    years = (ee.ImageCollection(OB_TEMPORAL).filterBounds(aoi)
             .aggregate_array("inference_time_epoch_s")
             .map(lambda t: ee.Date(ee.Number(t).multiply(1000)).get("year"))
             .distinct().sort().getInfo())
    print(f"Open Buildings Temporal years over Lahore: {years}")

    ev = cfg["flood_event"]
    s1 = s1_vv(aoi, ev["event_start"], ev["event_end"])
    info = ee.Dictionary({
        "dates": s1.aggregate_array("system:time_start").map(lambda t: ee.Date(t).format("YYYY-MM-dd HH:mm")),
        "orbits": s1.aggregate_array("relativeOrbitNumber_start"),
        "passes": s1.aggregate_array("orbitProperties_pass"),
        "platforms": s1.aggregate_array("platform_number"),
    }).getInfo()
    print(f"Sentinel-1 scenes in the flood window ({ev['event_start']} to {ev['event_end']}): {len(info['dates'])}")
    rows = zip(info["dates"], info["platforms"], info["orbits"], info["passes"], strict=True)
    for d, plat, orb, pas in sorted(rows):
        print(f"  {d} UTC  S1{plat}  relative orbit {orb:>3}  {pas.lower()}")


if __name__ == "__main__":
    main()
