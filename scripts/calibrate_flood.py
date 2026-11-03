"""Calibrate the flood thresholds on geolocated reference points (needs at least 30; TRD.md 5.3).

1. Fill data/reference/flood_validation_points.csv: one row per place seen flooded (or seen dry) in
   late August 2025, with the source (news URL, drone video, field report). Include dry places too,
   otherwise only sensitivity can be measured.
2. uv run python scripts/calibrate_flood.py [--points other.csv] [--orbit 107]
3. Read the report; if the cross-validated score is acceptable, copy the recommended values into
   config/settings.yaml (flood_mapping), set `applied: true` in data/interim/flood_calibration.json,
   re-run scripts/export_baseline.py --only flood and scripts/build_exposure.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

import ee

from kinara.calibrate import MIN_POINTS, confusion, cross_validated, grid_search, read_points
from kinara.config import load_settings
from kinara.detect.change import flood_mask
from kinara.gee import client, fetch
from kinara.gee.flood import sample_backscatter
from kinara.geo.utm import utm43n
from kinara.validate.metrics import block_folds, spatial_blocks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cfg = load_settings()
    ap.add_argument("--points", default=str(cfg["paths"]["reference"] / "flood_validation_points.csv"))
    ap.add_argument("--orbit", type=int, default=107, help="the orbit flood_2025.tif was made from")
    a = ap.parse_args()

    pts = read_points(a.points)
    if len(pts) < MIN_POINTS:
        raise SystemExit(f"{len(pts)} reference points in {a.points}; at least {MIN_POINTS} are needed "
                         "(PRD F3). Add more geolocated flooded and dry locations first.")
    client.init(cfg)
    aoi = client.district(cfg)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]), {"point_id": str(r.point_id)})
                               for r in pts.itertuples()])
    s = fetch.table(sample_backscatter(fc, aoi, cfg, a.orbit), ["point_id", "before_db", "after_db", "built"])
    s = pts.assign(point_id=pts["point_id"].astype(str)).merge(s, on="point_id", how="left")
    s["built"] = s["built"].fillna(0)

    fm = cfg["flood_mapping"]
    cur = flood_mask(s["before_db"].to_numpy(float), s["after_db"].to_numpy(float), s["built"].to_numpy(bool),
                     fm["open_water_max_db"], fm["open_water_drop_db"], fm["urban_rise_db"])
    ok = s["before_db"].notna().to_numpy()
    current = confusion(cur["flooded"][ok], s["flooded"].to_numpy(bool)[ok])
    table = grid_search(s)
    xy = [utm43n(lo, la) for lo, la in zip(s.lon, s.lat, strict=True)]
    blocks = spatial_blocks([p[0] for p in xy], [p[1] for p in xy], cfg["validation"]["cv_block_m"])
    cv = cross_validated(s, block_folds(blocks, 5, cfg["validation"]["random_seed"]))
    best = table.iloc[0]

    out = cfg["paths"]["interim"]
    s.to_csv(out / "flood_calibration_samples.csv", index=False)
    table.to_csv(out / "flood_calibration_grid.csv", index=False)
    report = {"run_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "points": a.points,
              "orbit": a.orbit, "n_points": len(s), "n_with_radar": int(ok.sum()),
              "current": {"thresholds": fm, "scores": current},
              "recommended": {k: float(best[k]) for k in ("open_water_max_db", "open_water_drop_db", "urban_rise_db")},
              "recommended_in_sample": {k: best[k] for k in ("balanced_accuracy", "sensitivity", "specificity")},
              "cross_validated": cv, "applied": False}
    (out / "flood_calibration.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")

    print(f"{ok.sum()} of {len(s)} points have radar values (orbit {a.orbit})")
    print(f"current thresholds   : balanced accuracy {current['balanced_accuracy']:.2f} "
          f"(sensitivity {current['sensitivity']}, specificity {current['specificity']})")
    print(f"recommended          : {report['recommended']}")
    print(f"  in-sample          : balanced accuracy {best['balanced_accuracy']:.2f} (optimistic)")
    print(f"  cross-validated    : balanced accuracy {cv['balanced_accuracy']}, accuracy {cv['accuracy']:.2f} "
          f"95% CI {cv['accuracy_ci'][0]:.2f}-{cv['accuracy_ci'][1]:.2f}   <- quote this one")
    print(f"details: {out / 'flood_calibration.json'}")


if __name__ == "__main__":
    main()
