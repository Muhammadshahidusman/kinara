"""Candidate new-construction alerts from the newest Sentinel-1 passes (TRD.md section 5.4).

For each relative orbit in settings (change_detection.orbits):
  1. find its passes in the last `lookback_days`; stop if the newest pass was already processed
  2. Earth Engine: linear-mean VV baseline (`baseline_days` before the persistence passes) and
     the newest `persistence_passes` passes, downloaded on a 10 m UTM grid over the floodplain
  3. numpy (kinara.detect.change): rise >= built_increase_db on every pass, inside the floodplain,
     not already built in Open Buildings 2023, patches >= min_alert_area_ha
  4. attach tehsil / mouza, distance to river, flooded-2025 share; de-duplicate; assign K-ids
  5. evidence: radar sparkline per alert and Sentinel-2 before/after chips
Every run is recorded (scenes, settings snapshot, counts, success) even when it finds nothing.

Run:  uv run python scripts/detect_alerts.py                 (today, all orbits)
      uv run python scripts/detect_alerts.py --date 2026-10-24 --orbit 107 --force
      uv run python scripts/detect_alerts.py --no-evidence      (skip Sentinel-2 chips)
      uv run python scripts/detect_alerts.py --backfill-evidence (retry missing evidence only)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import traceback

import ee
import geopandas as gpd
import numpy as np
from rasterio.enums import Resampling

from kinara import alerts as al
from kinara import units
from kinara.api.store import open_store
from kinara.config import get_logger, load_settings
from kinara.detect.change import min_area_filter, persistent_increase
from kinara.gee import client, fetch, monitor
from kinara.geo.raster import find_export, grid_for_bounds, rasterize, resample_to_grid

log = get_logger("kinara.detect_alerts")


def _days_before(day: str, n: int) -> str:
    return (dt.date.fromisoformat(day) - dt.timedelta(days=n)).isoformat()


class Grid:
    """The 10 m detection grid over the floodplain, with its static masks."""

    def __init__(self, cfg: dict):
        crs = cfg["project"]["crs_analysis"]
        res = cfg["change_detection"]["pixel_size_m"]
        self.zone = units.floodplain(cfg)
        self.crs = crs
        self.res = res
        self.transform, self.shape = grid_for_bounds(tuple(self.zone.total_bounds), res)
        self.fp = rasterize(list(self.zone.geometry), self.transform, self.shape)
        ex = cfg["paths"]["gee_exports"]
        years = find_export(ex, "first_built_year.tif")
        # any 4 m building pixel inside a 10 m cell makes the cell "already built" (max resampling)
        self.built = (np.nan_to_num(resample_to_grid(years, 1, self.transform, self.shape, crs, Resampling.max))
                      > 0) if years else np.zeros(self.shape, bool)
        flood = find_export(ex, "flood_2025.tif")
        self.flooded = resample_to_grid(flood, "flooded", self.transform, self.shape, crs) if flood else None
        log.info(f"grid {self.shape[1]}x{self.shape[0]} px at {res} m; floodplain {self.fp.mean():.1%} of it; "
                 f"already built {self.built[self.fp].mean():.1%} of the floodplain")


def detect_orbit(cfg: dict, grid: Grid, aoi: ee.Geometry, orbit: int, run_day: str, done_day: str,
                 force: bool) -> tuple[gpd.GeoDataFrame | None, dict, dict]:
    """Candidate patches for one orbit. Returns (patches or None, orbit report, scenes used)."""
    cd = cfg["change_detection"]
    n = cd["persistence_passes"]
    passes = monitor.orbit_passes(aoi, orbit, _days_before(run_day, cd["lookback_days"]),
                                  (dt.date.fromisoformat(run_day) + dt.timedelta(days=1)).isoformat())
    report: dict = {"passes_found": len(passes)}
    if len(passes) < n:
        report["skipped"] = f"only {len(passes)} pass(es) in the last {cd['lookback_days']} days"
        return None, report, {}
    use = passes[-n:]
    report["newest_pass"] = use[-1]["day"]
    if use[-1]["day"] <= done_day and not force:
        report["skipped"] = f"newest pass {use[-1]['day']} already processed"
        return None, report, {}
    baseline = (_days_before(use[0]["day"], cd["baseline_days"]), use[0]["day"])
    base_ids = monitor.baseline_ids(aoi, orbit, baseline)
    report.update({"passes": [p["day"] for p in use], "baseline": list(baseline), "baseline_scenes": len(base_ids)})
    scenes = {sid: {"day": p["day"], "orbit": orbit} for p in use for sid in p["ids"]}
    scenes.update({sid: {"day": al.scene_day(sid), "orbit": orbit} for sid in base_ids})
    if not base_ids:
        report["skipped"] = "no baseline scenes"
        return None, report, scenes

    img = monitor.change_stack(aoi, orbit, [p["day"] for p in use], baseline)
    bands = ["base"] + [f"p{i}" for i in range(n)]
    x0, y_top = grid.transform.c, grid.transform.f
    arr = fetch.pixels(img, bands, x0, y_top, grid.shape[1], grid.shape[0], grid.res, grid.crs,
                       tile=cd["tile_px"], keep=grid.fp)
    db = {b: np.where(a == fetch.NODATA_I16, np.nan, a / monitor.DB_SCALE) for b, a in arr.items()}
    stack = np.stack([db[f"p{i}"] for i in range(n)])
    rise = persistent_increase(db["base"], stack, cd["built_increase_db"], n)
    cand = rise & grid.fp & ~grid.built
    kept, labels = min_area_filter(cand, grid.res, cd["min_alert_area_ha"])
    min_rise = np.nanmin(stack - db["base"][None], axis=0)
    p = al.patches(labels, grid.transform, grid.crs, grid.res,
                   stats={"rise_db": min_rise, "base_db": db["base"], "last_db": db[f"p{n - 1}"]})
    report.update({"candidate_px": int(cand.sum()), "patches": len(p)})
    p["orbit"], p["first_detected"] = orbit, use[-1]["day"]
    p["scenes_after"] = [json.dumps([sid for q in use for sid in q["ids"]])] * len(p)
    p["baseline_window"] = f"{baseline[0]} to {baseline[1]}"
    p["n_baseline_scenes"] = len(base_ids)
    p.attrs["labels"] = labels
    return p, report, scenes


EVIDENCE_ERRORS = (ee.EEException, OSError, KeyError, ValueError)   # one bad alert must not stop the rest


def needs_evidence(p: dict, chips: bool) -> bool:
    """True if an alert still lacks its sparkline or (when chips are wanted) a Sentinel-2 chip attempt."""
    return "sparkline" not in p or (chips and ("s2_before" not in p or "s2_after" not in p))


def add_evidence(cfg: dict, feats: list[dict], aoi: ee.Geometry, chips: bool, store) -> int:
    """Radar sparkline and Sentinel-2 before/after chips, saved to the store alert by alert.

    Runs AFTER the alerts are stored, so a network failure here only leaves evidence missing; it is
    filled in later with --backfill-evidence. Returns the number of alerts updated.
    """
    cd = cfg["change_detection"]
    out_dir = cfg["paths"]["processed"] / "evidence"
    out_dir.mkdir(exist_ok=True)
    updated: set[str] = set()   # an alert can get a sparkline and chips; count it once
    for orbit in sorted({f["properties"]["orbit"] for f in feats}):
        group = [f for f in feats if f["properties"]["orbit"] == orbit and "sparkline" not in f["properties"]]
        if not group:
            continue
        try:
            day = max(f["properties"]["first_detected"] for f in group)
            hist = monitor.orbit_passes(aoi, orbit, _days_before(day, cd["revisit_days"] * (cd["history_passes"] + 2)),
                                        (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat())
            days = [h["day"] for h in hist][-cd["history_passes"]:]
            fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]),
                                                  {"alert_id": f["properties"]["alert_id"]}) for f in group])
            tab = fetch.table(monitor.pass_means(fc, aoi, orbit, days),
                              ["alert_id"] + [f"d{i}" for i in range(len(days))]).set_index("alert_id")
        except EVIDENCE_ERRORS as e:
            log.warning(f"orbit {orbit} sparklines failed ({type(e).__name__}: {e}); try --backfill-evidence later")
            continue
        for f in group:
            aid = f["properties"]["alert_id"]
            if aid not in tab.index:
                continue
            row = tab.loc[aid]
            spark = [{"day": d, "vv_db": None if np.isnan(row[f"d{i}"]) else round(float(row[f"d{i}"]), 2)}
                     for i, d in enumerate(days)]
            f["properties"]["sparkline"] = spark
            store.update_alert(aid, {"sparkline": spark})
            updated.add(aid)
    if not chips:
        return len(updated)
    buf = cd["evidence_buffer_m"]
    for n, f in enumerate(feats, 1):
        p = f["properties"]
        if "s2_before" in p and "s2_after" in p:
            continue
        outline = ee.Geometry(f["geometry"])
        region = outline.buffer(buf).bounds()
        start_base = p["baseline_window"].split(" to ")[0]
        windows = {"before": (start_base, _days_before(p["first_detected"], cd["revisit_days"] * 2)),
                   "after": (_days_before(p["first_detected"], cd["revisit_days"] * 3),
                             (dt.date.fromisoformat(p["first_detected"]) + dt.timedelta(days=6)).isoformat())}
        update = {}
        for side, (s0, e0) in windows.items():
            try:
                scene = monitor.s2_best_scene(region, s0, e0)
                if scene is None:
                    update[f"s2_{side}"] = {"available": False, "reason": f"no Sentinel-2 scene {s0} to {e0}"}
                    continue
                meta = ee.Dictionary({"id": scene.get("system:index"), "cloud": scene.get("CLOUDY_PIXEL_PERCENTAGE"),
                                      "t": scene.get("system:time_start")}).getInfo()
                png = fetch.thumbnail(monitor.s2_chip(scene, outline, region), region, cd["evidence_px"])
                (out_dir / f"{p['alert_id']}_{side}.png").write_bytes(png)
                update[f"s2_{side}"] = {"available": True, "scene": meta["id"], "cloud_pct": round(meta["cloud"], 1),
                                        "date": dt.datetime.fromtimestamp(meta["t"] / 1000, dt.UTC).date().isoformat()}
            except EVIDENCE_ERRORS as e:
                # not recorded, so --backfill-evidence tries this chip again
                log.warning(f"{p['alert_id']} {side} chip failed ({type(e).__name__}: {e})")
        if update:
            p.update(update)
            store.update_alert(p["alert_id"], update)
            updated.add(p["alert_id"])
        if n % 25 == 0:
            log.info(f"evidence chips: {n}/{len(feats)} alerts")
    return len(updated)


def backfill(cfg: dict, store, chips: bool) -> None:
    """Fill in missing sparklines / chips for alerts already in the store (after a network failure)."""
    client.init(cfg)
    aoi = client.district(cfg)
    todo = [f for f in store.alerts(limit=100_000)["features"] if needs_evidence(f["properties"], chips)]
    print(f"{len(todo)} alert(s) need evidence")
    if todo:
        print(f"updated {add_evidence(cfg, todo, aoi, chips, store)} alert(s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="run date (YYYY-MM-DD)")
    ap.add_argument("--orbit", type=int, nargs="+", help="orbits to process (default: settings)")
    ap.add_argument("--force", action="store_true", help="reprocess passes already done")
    ap.add_argument("--no-evidence", action="store_true", help="skip Sentinel-2 chips")
    ap.add_argument("--backfill-evidence", action="store_true",
                    help="only fill in missing sparklines / chips for existing alerts, then exit")
    a = ap.parse_args()

    cfg = load_settings()
    cd, ex = cfg["change_detection"], cfg["exposure"]
    store = open_store()
    if a.backfill_evidence:
        backfill(cfg, store, chips=not a.no_evidence)
        return
    run: dict = {"started_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "run_date": a.date,
                 "settings": json.loads(json.dumps(cfg, default=str)), "scenes": {}, "orbits": {},
                 "n_alerts": 0, "n_repeats": 0, "ok": False, "error": None}
    try:
        client.init(cfg)
        aoi = client.district(cfg)
        grid = Grid(cfg)
        teh, mou = units.tehsils(cfg), units.mouzas(cfg)
        river_file = cfg["paths"]["interim"] / "river.geojson"
        river = gpd.read_file(river_file).to_crs(grid.crs) if river_file.exists() else None
        prior = store.runs(500)
        existing = al.existing_gdf(store.alerts(limit=100_000), grid.crs)
        all_new: list[dict] = []
        seen: dict[str, str] = {}
        for orbit in a.orbit or cd["orbits"]:
            p, report, scenes = detect_orbit(cfg, grid, aoi, orbit, a.date, al.last_processed(prior, orbit), a.force)
            run["orbits"][str(orbit)] = report
            run["scenes"].update(scenes)
            log.info(f"orbit {orbit}: {report}")
            if p is None or p.empty:
                continue
            labels = p.attrs.pop("labels")
            p = al.attach(p, teh, mou, river, grid.flooded, labels, cd["flooded_share"])
            p["zone_id"] = grid.zone.iloc[0]["zone_id"]
            fresh, repeats = al.dedupe(p, existing, cd["dedupe_iou"], cd["dedupe_buffer_m"])
            for aid in repeats.values():
                seen[aid] = max(seen.get(aid, ""), p.iloc[0]["first_detected"])
            if fresh:
                new = p.iloc[fresh].reset_index(drop=True)
                ids = al.next_ids(list(existing.get("alert_id", [])) + [f["properties"]["alert_id"] for f in all_new],
                                  int(a.date[:4]), len(new))
                feats = al.features(new, ids, ex["marla_sqft"], ex["kanal_marla"],
                                    extra={"last_seen": new.iloc[0]["first_detected"], "n_detections": 1,
                                           "detected_by": "system"})
                all_new.extend(feats)
                existing = al.existing_gdf({"features": [*_as_features(existing), *feats]}, grid.crs)
        run.update({"n_alerts": len(all_new), "n_repeats": len(seen), "ok": True})
    except Exception as e:  # the run must be recorded as failed whatever went wrong
        run["error"] = f"{type(e).__name__}: {e}"
        log.error(traceback.format_exc())
        all_new, seen = [], {}
    run["finished_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    run_id = store.add_run(run)
    if run["ok"]:
        store.upsert_alerts(all_new, seen, run_id)
    print(f"run {run_id}: {'ok' if run['ok'] else 'FAILED'}; {run['n_alerts']} new alert(s), "
          f"{run['n_repeats']} repeat(s); {len(run['scenes'])} scenes")
    if not run["ok"]:
        raise SystemExit(1)
    if all_new:
        # alerts are already saved; evidence failures only leave gaps for --backfill-evidence
        n = add_evidence(cfg, all_new, aoi, not a.no_evidence, store)
        print(f"evidence added for {n} of {len(all_new)} new alert(s)")


def _as_features(g: gpd.GeoDataFrame) -> list[dict]:
    """Existing alerts back to minimal GeoJSON features (id + geometry) for the next orbit's de-duplication."""
    if g.empty:
        return []
    web = g.to_crs("EPSG:4326")
    return json.loads(web[["alert_id", "geometry"]].to_json())["features"]


if __name__ == "__main__":
    main()
