"""Flood calibration scoring, auth helpers, PDF builders, store status rules."""

import numpy as np
import pandas as pd
import pytest

from kinara.calibrate import confusion, cross_validated, grid_search, read_points


def _samples():
    # flooded open land: dark and darker; flooded built-up: brighter; dry: unchanged
    rows = []
    for i in range(10):
        rows.append({"before_db": -10, "after_db": -21 - i * 0.1, "built": 0, "flooded": 1})
        rows.append({"before_db": -8, "after_db": -6 + i * 0.1, "built": 1, "flooded": 1})    # +2 to +2.9 dB
        rows.append({"before_db": -10, "after_db": -10.5, "built": 0, "flooded": 0})
        rows.append({"before_db": -8, "after_db": -8.2, "built": 1, "flooded": 0})
    return pd.DataFrame(rows)


def test_confusion_counts_and_intervals():
    c = confusion(np.array([1, 1, 0, 0], bool), np.array([1, 0, 0, 1], bool))
    assert (c["tp"], c["fp"], c["tn"], c["fn"]) == (1, 1, 1, 1)
    assert c["accuracy"] == 0.5 and c["balanced_accuracy"] == 0.5
    assert c["accuracy_ci"][0] < 0.5 < c["accuracy_ci"][1]


def test_grid_search_finds_lower_urban_threshold():
    best = grid_search(_samples()).iloc[0]
    assert best.balanced_accuracy == 1.0
    assert best.urban_rise_db <= 2.0          # the 3 dB default misses these flooded buildings


def test_cross_validated_runs_per_fold():
    s = _samples()
    c = cross_validated(s, np.arange(len(s)) // 4 % 5)     # every fold holds all four kinds of point
    assert c["n"] == len(s) and c["accuracy"] >= 0.9


def test_read_points_validates(tmp_path):
    f = tmp_path / "p.csv"
    f.write_text("# comment\npoint_id,lon,lat,flooded\n1,74.3,31.6,1\n", encoding="utf-8")
    assert len(read_points(str(f))) == 1
    f.write_text("point_id,lon,lat,flooded\n1,74.3,31.6,yes\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_points(str(f))
    f.write_text("point_id,lon,flooded\n1,74.3,1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_points(str(f))


def test_shipped_template_has_required_columns():
    from kinara.config import load_settings
    df = read_points(str(load_settings()["paths"]["reference"] / "flood_validation_points.csv"))
    assert df.empty                            # template only: real points must come from sources


def test_resolve_status():
    from kinara.api.store import resolve_status
    assert resolve_status("new", "visited") == "visited"
    assert resolve_status("confirmed", "visited") == "confirmed"
    assert resolve_status("visited", "false_alarm") == "false_alarm"


pytest.importorskip("jwt")


def test_password_and_token_roundtrip():
    from fastapi import HTTPException

    from kinara.api import auth
    h = auth.hash_password("correct horse")
    assert auth.verify_password("correct horse", h) and not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "not-a-hash")
    t = auth.make_token("ali", "viewer", "k", 5)
    assert auth.read_token(t, "k")["sub"] == "ali"
    with pytest.raises(HTTPException):
        auth.read_token(t, "other-key")
    with pytest.raises(HTTPException):
        auth.read_token(auth.make_token("ali", "viewer", "k", -1), "k")      # expired


def test_role_hierarchy():
    from kinara.api.auth import role_at_least
    assert role_at_least("admin", "field_officer") and role_at_least("viewer", "viewer")
    assert not role_at_least("viewer", "field_officer")


def test_premonsoon_pdf_with_map(tmp_path):
    from kinara.api.reports import fmt_date, premonsoon_pdf
    sq = {"type": "Polygon", "coordinates": [[[74.2, 31.5], [74.4, 31.5], [74.4, 31.7], [74.2, 31.7], [74.2, 31.5]]]}
    layers = {"zones": {"features": [{"geometry": sq, "properties": {}}]},
              "tehsils": {"features": [{"geometry": sq, "properties": {}}]},
              "river": {"features": [{"geometry": {"type": "LineString", "coordinates": [[74.2, 31.5], [74.4, 31.7]]},
                                      "properties": {}}]}}
    exposure = [{"unit_type": "tehsil", "name": "Ravi", "bld_n": 10, "area_km2": 1.0},
                {"unit_type": "mouza", "name": "Kot Begum", "tehsil": "Ravi", "bld_n": 5}]
    alerts = {"features": [{"properties": {"status": "confirmed", "lon": 74.3, "lat": 31.6, "tehsil": "Ravi"}}]}
    pdf = premonsoon_pdf({"buildings": {"n": 10, "post2016_n": 3}}, exposure, layers, alerts)
    assert pdf.startswith(b"%PDF") and len(pdf) > 3000
    assert fmt_date("2026-10-26") == "26 Oct 2026" and fmt_date(None) == "not available"
