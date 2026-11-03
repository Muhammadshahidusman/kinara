"""Alert construction: patches, attributes, de-duplication, ids, run bookkeeping."""

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import LineString, box

from kinara import alerts as al
from kinara.detect.change import min_area_filter

CRS = "EPSG:32643"
T = Affine(10, 0, 400000, 0, -10, 3500000)     # 10 m grid, upper-left at (400000, 3500000)


def _labels():
    mask = np.zeros((40, 40), bool)
    mask[5:15, 5:15] = True       # 1 ha
    mask[20:30, 20:35] = True     # 1.5 ha
    mask[0:2, 38:40] = True       # tiny, dropped by min_area_filter
    return min_area_filter(mask, 10, 0.5)[1]


def test_patches_area_and_stats():
    labels = _labels()
    stats = np.where(labels == 1, 4.0, 6.0)
    stats[6, 6] = np.nan
    p = al.patches(labels, T, CRS, 10, {"rise_db": stats})
    assert sorted(p.area_ha.tolist()) == [1.0, 1.5]
    assert sorted(p.rise_db.tolist()) == [4.0, 6.0]                 # NaN ignored
    assert all(g.geom_type == "MultiPolygon" for g in p.geometry)
    assert abs(p.geometry.area.sum() / 10_000 - 2.5) < 1e-6         # polygons match pixel area


def test_patches_empty():
    assert al.patches(np.zeros((5, 5), int), T, CRS, 10).empty


def test_attach_tehsil_river_flood():
    labels = _labels()
    p = al.patches(labels, T, CRS, 10)
    tehsils = gpd.GeoDataFrame({"name": ["West", "East"]},
                               geometry=[box(399000, 3499000, 400180, 3501000), box(400180, 3499000, 401000, 3501000)],
                               crs=CRS)
    river = gpd.GeoDataFrame(geometry=[LineString([(400000, 3499000), (400000, 3501000)])], crs=CRS)
    flooded = np.zeros_like(labels, float)
    flooded[5:15, 5:10] = 1      # half of patch 1
    out = al.attach(p, tehsils, None, river, flooded, labels, flooded_share=0.10).sort_values("area_ha")
    assert out.tehsil.tolist() == ["West", "East"]
    assert out.distance_river_m.tolist() == [50, 200]
    assert out.flooded_2025.tolist() == [True, False]
    assert out.flooded_share.tolist() == [0.5, 0.0]
    assert out.mouza.tolist() == [None, None]
    assert out.crs == CRS                                           # features() reprojects from it
    assert len(al.features(out, ["K-2026-0001", "K-2026-0002"], 272.25, 20)) == 2


def test_dedupe_iou_and_buffer():
    existing = gpd.GeoDataFrame({"alert_id": ["K-2026-0001", "K-2026-0002"]},
                                geometry=[box(0, 0, 100, 100), box(1000, 0, 1100, 100)], crs=CRS)
    new = gpd.GeoDataFrame(geometry=[box(10, 10, 110, 110),       # overlaps 1 heavily
                                     box(1110, 0, 1200, 100),     # 10 m from 2: grows outward
                                     box(5000, 0, 5100, 100)],    # genuinely new
                           crs=CRS)
    fresh, repeats = al.dedupe(new, existing, min_iou=0.3, buffer_m=20)
    assert fresh == [2] and repeats == {0: "K-2026-0001", 1: "K-2026-0002"}
    assert al.dedupe(new, existing.iloc[0:0], 0.3, 20) == ([0, 1, 2], {})


def test_iou():
    assert al.iou(box(0, 0, 2, 2), box(1, 0, 3, 2)) == pytest.approx(1 / 3)
    assert al.iou(box(0, 0, 1, 1), box(5, 5, 6, 6)) == 0.0


def test_next_ids_continue_per_year():
    assert al.next_ids(["K-2026-0041", "K-2026-0007", "K-2025-0300", "junk"], 2026, 2) == ["K-2026-0042",
                                                                                         "K-2026-0043"]
    assert al.next_ids([], 2027, 1) == ["K-2027-0001"]


def test_features_are_wgs84_with_kanal():
    p = al.patches(_labels(), Affine(10, 0, 430000, 0, -10, 3495000), CRS, 10)
    f = al.features(p, ["K-2026-0001", "K-2026-0002"], 272.25, 20)
    lon, lat = f[0]["geometry"]["coordinates"][0][0][0]
    assert 74 < lon < 75 and 31 < lat < 32
    one_ha = next(x for x in f if x["properties"]["area_ha"] == 1.0)["properties"]
    assert one_ha["area_kanal"] == pytest.approx(19.8, abs=0.05)    # 1 ha = 19.77 revenue kanal
    assert one_ha["status"] == "new" and one_ha["kind"] == "new_construction"


def test_scene_day_and_last_processed():
    assert al.scene_day("S1A_IW_GRDH_1SDV_20250828T010809_20250828T010834_060729_078ED9_5292") == "2025-08-28"
    runs = [{"ok": True, "orbits": {"107": {"newest_pass": "2026-10-12"}}},
            {"ok": False, "orbits": {"107": {"newest_pass": "2026-10-24"}}},     # failed runs don't count
            {"ok": True, "orbits": {"34": {"newest_pass": "2026-10-30"}}}]
    assert al.last_processed(runs, 107) == "2026-10-12"
    assert al.last_processed(runs, 100) == ""


def test_with_retry_recovers_then_gives_up(monkeypatch):
    from kinara.gee import fetch
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("unreachable network")
        return "ok"

    assert fetch.with_retry(flaky, "test") == "ok" and calls["n"] == 3

    def broken():
        raise OSError("down")

    with pytest.raises(OSError):
        fetch.with_retry(broken, "test", retries=2)


def test_update_alert_merges_evidence_but_not_status(tmp_path):
    import json

    from kinara.api.store import FileStore
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": None,
                                                     "properties": {"alert_id": "K-2026-0001", "status": "new"}}]}
    (tmp_path / "alerts.geojson").write_text(json.dumps(fc), encoding="utf-8")
    s = FileStore(tmp_path)
    assert s.update_alert("K-2026-0001", {"sparkline": [1], "status": "confirmed"})
    p = s.alert("K-2026-0001")["properties"]
    assert p["sparkline"] == [1] and p["status"] == "new"
    assert not s.update_alert("K-2099-0001", {"x": 1})
