"""Kinara API.

Endpoints (v0.2). Every /api route except health and auth/token needs a bearer token.
  GET   /api/health                                 backend and version (open)
  POST  /api/auth/token                             sign in (OAuth2 password form) -> JWT
  GET   /api/auth/me                                the signed-in user
  GET   /api/summary                                headline numbers, data dates, last run, stale flag
  GET   /api/zones                                  floodplain zones (GeoJSON)
  GET   /api/layers/{tehsils|mouzas|cells|river}    map layers (GeoJSON)
  GET   /api/layers/flood_2025.png                  August 2025 flood overlay (see summary.flood_2025.overlay)
  GET   /api/exposure?unit_type=tehsil|mouza|zone   buildings, flood and population per unit
  GET   /api/alerts?status=&tehsil=&since=&min_ha=&flooded=&limit=   candidate alerts, newest first
  GET   /api/alerts/{id}                            one alert with its verification history
  GET   /api/alerts/{id}/image/{before|after}.png   Sentinel-2 evidence chip
  GET   /api/alerts/{id}/evidence.pdf               one-page evidence sheet
  POST  /api/alerts/{id}/verification               record a verdict          (field_officer)
  GET   /api/report/pre-monsoon.pdf                 pre-monsoon exposure report
  GET   /api/export/{exposure|alerts}.zip           CSV / GeoJSON with a README of fields
  GET   /api/precision                              release-gate precision on verified alerts
  GET   /api/locate?lon=..&lat=..                   500 m reporting cell for a point
  GET   /api/runs, /api/settings, /api/users; POST /api/users                    (admin)
  GET   /docs                                       Swagger UI

Run:  uv run uvicorn kinara.api.main:app --reload
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import zipfile
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from kinara import __version__
from kinara.api import auth, reports
from kinara.api.store import LAYERS, ROLES, STATUSES, open_store, read_layer
from kinara.config import settings
from kinara.geo.utm import cell_id_at, in_lahore_bbox, utm43n
from kinara.validate.metrics import precision_report

store = open_store()
app = FastAPI(
    title="Kinara API",
    version=__version__,
    description="Ravi Floodplain Watch: flood exposure and candidate new-construction alerts for Lahore. "
                "Alerts are candidates detected from 10 m satellite data and must be field-verified.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings()["api"]["cors_origins"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)


def processed():
    return settings()["paths"]["processed"]


def _key() -> str:
    return auth.secret_key(processed())


def _user(username: str) -> dict | None:
    return store.user(username)


Viewer = Annotated[dict, Depends(auth.require("viewer", lambda: _key(), lambda u: _user(u)))]
Officer = Annotated[dict, Depends(auth.require("field_officer", lambda: _key(), lambda u: _user(u)))]
Admin = Annotated[dict, Depends(auth.require("admin", lambda: _key(), lambda u: _user(u)))]


class Verification(BaseModel):
    status: str = Field(..., description=f"one of {', '.join(STATUSES)}")
    note: str = Field("", max_length=2000)
    lon: float | None = Field(None, description="verifier's GPS position, if shared")
    lat: float | None = None


class NewUser(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=200)
    role: str = Field(..., description=f"one of {', '.join(ROLES)}")
    full_name: str = Field("", max_length=100)
    active: bool = True


# ---------------------------------------------------------------- open
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "backend": store.name, "version": __version__}


@app.post("/api/auth/token")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> dict:
    u = store.user(form.username)
    if not u or not u.get("active", True) or not auth.verify_password(form.password, u["password_hash"]):
        raise HTTPException(401, "wrong username or password", headers={"WWW-Authenticate": "Bearer"})
    t = auth.make_token(u["username"], u["role"], _key(), settings()["api"]["token_minutes"])
    return {"access_token": t, "token_type": "bearer",
            "user": {"username": u["username"], "role": u["role"], "full_name": u.get("full_name", "")}}


# ---------------------------------------------------------------- viewer
@app.get("/api/auth/me")
def me(user: Viewer) -> dict:
    return user


@app.get("/api/summary")
def summary(user: Viewer) -> dict:
    s = read_layer(processed(), "summary.json") or {}
    runs = store.runs(50)
    ok = [r for r in runs if r.get("ok")]
    last_ok = ok[0].get("finished_at") if ok else None
    stale_days = settings()["api"]["stale_after_days"]
    stale = last_ok is None or (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(str(last_ok))).days > stale_days
    feats = store.alerts(limit=100_000)["features"]
    week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    open_alerts = [f for f in feats if f["properties"].get("status") in ("new", "visited")]
    return {**s,
            "alerts": {"open": len(open_alerts), "total": len(feats),
                       "new_this_week": sum(1 for f in feats
                                 if str(f["properties"].get("first_detected")) >= week_ago)},
            "last_run": runs[0] if runs else None, "last_successful_run": last_ok, "stale": stale,
            "stale_after_days": stale_days, "built": bool(s)}


@app.get("/api/zones")
def zones(user: Viewer) -> dict:
    return store.zones()


@app.get("/api/layers/flood_2025.png")
def flood_png(user: Viewer) -> FileResponse:
    f = processed() / "flood_2025.png"
    if not f.exists():
        raise HTTPException(404, "flood overlay not built; run scripts/build_exposure.py")
    return FileResponse(f, media_type="image/png")


@app.get("/api/layers/{name}")
def layer(user: Viewer, name: str = Path(..., pattern=f"^({'|'.join(LAYERS)})$")) -> dict:
    data = store.zones() if name == "zones" else read_layer(processed(), f"{name}.geojson")
    return data or {"type": "FeatureCollection", "features": []}


@app.get("/api/exposure")
def exposure(user: Viewer, unit_type: str | None = Query(None, pattern="^(zone|tehsil|mouza)$")) -> list[dict]:
    return store.exposure(unit_type)


@app.get("/api/alerts")
def alerts(user: Viewer, status: str | None = Query(None), tehsil: str | None = None,
           since: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), min_ha: float | None = Query(None, ge=0),
           flooded: bool | None = None, limit: int = Query(200, ge=1, le=5000)) -> dict:
    if status and status not in STATUSES:
        raise HTTPException(422, f"status must be one of {STATUSES}")
    return store.alerts(status, limit, tehsil, since, min_ha, flooded)


def _alert_or_404(alert_id: str) -> dict:
    rec = store.alert(alert_id)
    if rec is None:
        raise HTTPException(404, f"no alert {alert_id}")
    return rec


@app.get("/api/alerts/{alert_id}")
def alert(alert_id: str, user: Viewer) -> dict:
    return _alert_or_404(alert_id)


@app.get("/api/alerts/{alert_id}/image/{side}.png")
def alert_image(alert_id: str, user: Viewer, side: str = Path(..., pattern="^(before|after)$")) -> FileResponse:
    _alert_or_404(alert_id)
    f = processed() / "evidence" / f"{alert_id}_{side}.png"
    if not f.exists():
        raise HTTPException(404, "no Sentinel-2 image for this alert")
    return FileResponse(f, media_type="image/png")


@app.get("/api/alerts/{alert_id}/evidence.pdf")
def evidence(alert_id: str, user: Viewer) -> Response:
    pdf = reports.evidence_pdf(_alert_or_404(alert_id), processed() / "evidence",
                               read_layer(processed(), "summary.json"))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="kinara_{alert_id}.pdf"'})


@app.get("/api/report/pre-monsoon.pdf")
def premonsoon(user: Viewer) -> Response:
    layers = {k: read_layer(processed(), f"{k}.geojson") for k in ("tehsils", "river")}
    layers["zones"] = store.zones()
    pdf = reports.premonsoon_pdf(read_layer(processed(), "summary.json") or {}, store.exposure(), layers,
                                 store.alerts(limit=100_000))
    name = f"kinara_premonsoon_{dt.date.today():%Y%m%d}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


EXPOSURE_FIELDS = {
    "unit_id": "Unit id (T- tehsil, M- mouza, fp_ zone)", "unit_type": "zone, tehsil or mouza",
    "name": "Name (official boundary attribute)", "name_ur": "Urdu name (mouza layer)",
    "tehsil": "Tehsil of the mouza (official tehsil layer, majority overlap)",
    "n_tehsils": "Official tehsils the mouza polygon crosses (above 1 = the boundary layers disagree)",
    "area_km2": "Area of the unit INSIDE the floodplain, km2 (UTM 43N)",
    "bld_n": "Estimated buildings: Open Buildings v3 footprints, confidence >= 0.75",
    "bld_post2016_n": "Footprints first seen 2017-2023 (Open Buildings 2.5D Temporal, presence >= 0.5)",
    "bld_year_unknown_n": "Footprints with no year in the temporal data",
    "bld_flooded_2025": "Footprints inside the Aug 2025 Sentinel-1 flood extent (see summary for calibration status)",
    "pop_est": "Estimated population (rounded to 10)", "pop_source": "Population dataset and year",
}
ALERT_FIELDS = {
    "alert_id": "K-<year>-<sequence>", "status": "new, visited, confirmed, false_alarm, no_access",
    "first_detected": "Date of the Sentinel-1 pass that completed the persistence rule",
    "last_seen": "Latest pass that detected it again", "area_ha": "Area, hectares (UTM 43N)",
    "area_kanal": "Area, revenue kanal (20 marla x 272.25 sq ft)", "mouza": "Mouza by majority overlap",
    "tehsil": "Tehsil by majority overlap", "distance_river_m": "Distance to the Ravi centreline (HydroSHEDS), m",
    "flooded_2025": "At least 10% of the alert inside the Aug 2025 flood extent",
    "rise_db": "Mean of the smallest per-pass VV rise over the baseline, dB", "orbit": "Sentinel-1 relative orbit",
}


def _readme(title: str, fields: dict, s: dict) -> str:
    fp = s.get("floodplain", {})
    lines = [f"Kinara export: {title}", f"Exported {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC", "",
             f"Floodplain: {fp.get('label', 'n/a')} ({fp.get('area_km2')} km2)",
             f"Exposure built: {s.get('built_utc', 'n/a')}", "", "Fields:"]
    lines += [f"  {k}: {v}" for k, v in fields.items()]
    lines += ["", "Candidate alerts come from 10 m satellite data and must be verified on site. Kinara does not",
              "judge legality. All counts are area-level planning estimates, not household records.",
              "Open data: Copernicus Sentinel-1/-2, Google Open Buildings (CC BY 4.0 / ODbL), MERIT Hydro,",
              "HydroSHEDS, WorldPop (CC BY 4.0)."]
    return "\n".join(lines)


@app.get("/api/export/{name}.zip")
def export(user: Viewer, name: str = Path(..., pattern="^(exposure|alerts)$")) -> Response:
    s = read_layer(processed(), "summary.json") or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if name == "exposure":
            rows = store.exposure()
            out = io.StringIO()
            w = csv.DictWriter(out, fieldnames=list(EXPOSURE_FIELDS), extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            z.writestr("kinara_exposure.csv", "﻿" + out.getvalue())   # BOM so Excel reads Urdu names
            z.writestr("README.txt", _readme("exposure by unit", EXPOSURE_FIELDS, s))
        else:
            fc = store.alerts(limit=100_000)
            z.writestr("kinara_alerts.geojson", json.dumps(fc, ensure_ascii=False))
            z.writestr("README.txt", _readme("candidate alerts (GeoJSON, EPSG:4326)", ALERT_FIELDS, s))
    fname = f"kinara_{name}_{dt.date.today():%Y%m%d}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/precision")
def precision(user: Viewer) -> dict:
    feats = store.alerts(limit=100_000)["features"]
    r = precision_report([f["properties"].get("status") for f in feats], settings()["validation"]["target_precision"])
    return {**r, "min_verified": 300, "release_ready": r["meets_target"] and r["n"] >= 300}


@app.get("/api/locate")
def locate(user: Viewer, lon: float = Query(...), lat: float = Query(...)) -> dict:
    if not in_lahore_bbox(lon, lat):
        raise HTTPException(422, "point is outside Lahore District")
    return {"cell_id": cell_id_at(lon, lat), "lon": lon, "lat": lat}


# ---------------------------------------------------------------- field officer
def distance_m(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    """Planar distance in UTM 43N (metres); fine at alert-to-verifier scale."""
    ax, ay = utm43n(a_lon, a_lat)
    bx, by = utm43n(b_lon, b_lat)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


@app.post("/api/alerts/{alert_id}/verification")
def verify(alert_id: str, body: Verification, user: Officer) -> dict:
    rec = _alert_or_404(alert_id)
    dist = None
    p = rec["properties"]
    if body.lon is not None and body.lat is not None and p.get("lon") is not None:
        if not in_lahore_bbox(body.lon, body.lat):
            raise HTTPException(422, "GPS position is outside Lahore District")
        dist = round(distance_m(body.lon, body.lat, p["lon"], p["lat"]))
    if body.status == "visited" and (dist is None or dist > settings()["api"]["visited_radius_m"]):
        raise HTTPException(422, f"'visited' needs a GPS position within {settings()['api']['visited_radius_m']} m")
    try:
        event = store.set_verification(alert_id, body.status, body.note, user["username"], dist)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return event


# ---------------------------------------------------------------- admin
@app.get("/api/runs")
def runs(user: Admin, limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "settings"} for r in store.runs(limit)]


@app.get("/api/settings")
def current_settings(user: Admin) -> dict:
    return json.loads(json.dumps(settings(), default=str))


@app.get("/api/users")
def list_users(user: Admin) -> list[dict]:
    return store.users()


@app.post("/api/users")
def add_user(body: NewUser, user: Admin) -> dict:
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    store.put_user(body.username, auth.hash_password(body.password), body.role, body.full_name, body.active)
    return {"username": body.username, "role": body.role, "full_name": body.full_name, "active": body.active}
