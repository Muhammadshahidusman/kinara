"""API tests against a temporary FileStore. Skipped unless the api extra is installed."""

import json
import zipfile
from io import BytesIO

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

ALERT_LON, ALERT_LAT = 74.25, 31.60


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KINARA_SECRET_KEY", "test-key-not-secret")
    alerts = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "MultiPolygon", "coordinates": [[[[74.249, 31.599], [74.251, 31.599], [74.251, 31.601],
                                                                [74.249, 31.601], [74.249, 31.599]]]]},
        "properties": {"alert_id": "K-2026-0001", "kind": "new_construction", "first_detected": "2026-10-20",
                       "area_ha": 1.2, "area_kanal": 23.7, "tehsil": "Ravi", "mouza": "Kot Begum",
                       "flooded_2025": True, "lon": ALERT_LON, "lat": ALERT_LAT, "status": "new",
                       "sparkline": [{"day": "2026-09-26", "vv_db": -12.0}, {"day": "2026-10-08", "vv_db": -8.1},
                                     {"day": "2026-10-20", "vv_db": -7.5}]},
    }]}
    (tmp_path / "alerts.geojson").write_text(json.dumps(alerts), encoding="utf-8")
    (tmp_path / "exposure.json").write_text(json.dumps([
        {"unit_id": "fp_hand", "unit_type": "zone", "name": "Floodplain", "bld_n": 100},
        {"unit_id": "T-Ravi", "unit_type": "tehsil", "name": "Ravi", "bld_n": 60, "name_ur": None},
    ]), encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({"buildings": {"n": 100}, "floodplain": {"label": "FP"}}),
                                           encoding="utf-8")
    import kinara.api.main as main
    from kinara.api.auth import hash_password
    from kinara.api.store import FileStore

    store = FileStore(tmp_path)
    for name, role in (("viewer1", "viewer"), ("field1", "field_officer"), ("admin1", "admin")):
        store.put_user(name, hash_password("password123"), role, name.title())
    store.put_user("gone", hash_password("password123"), "admin", active=False)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "processed", lambda: tmp_path)
    return TestClient(main.app)


def login(client, user, password="password123"):
    r = client.post("/api/auth/token", data={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_is_open(client):
    assert client.get("/api/health").json()["backend"] == "files"


def test_everything_else_needs_a_token(client):
    for path in ("/api/alerts", "/api/summary", "/api/exposure", "/api/layers/tehsils", "/api/runs"):
        assert client.get(path).status_code == 401, path


def test_bad_password_and_inactive_user(client):
    assert client.post("/api/auth/token", data={"username": "field1", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/token", data={"username": "gone", "password": "password123"}).status_code == 401


def test_alert_flow_records_signed_in_user(client):
    h = login(client, "field1")
    assert client.get("/api/alerts", headers=h).json()["features"][0]["properties"]["status"] == "new"
    r = client.post("/api/alerts/K-2026-0001/verification", headers=h,
                    json={"status": "confirmed", "note": "boundary wall seen", "user": "someone-else"})
    assert r.status_code == 200
    a = client.get("/api/alerts/K-2026-0001", headers=h).json()
    assert a["properties"]["status"] == "confirmed"
    assert a["properties"]["history"][0]["user"] == "field1"        # from the token, not the body
    assert client.get("/api/alerts?status=new", headers=h).json()["features"] == []


def test_viewer_cannot_verify_and_admin_routes_are_guarded(client):
    v = login(client, "viewer1")
    assert client.post("/api/alerts/K-2026-0001/verification", headers=v,
                       json={"status": "confirmed"}).status_code == 403
    assert client.get("/api/runs", headers=v).status_code == 403
    assert client.get("/api/runs", headers=login(client, "field1")).status_code == 403
    assert client.get("/api/runs", headers=login(client, "admin1")).status_code == 200


def test_visited_needs_gps_nearby_and_never_overrides_a_verdict(client):
    h = login(client, "field1")
    url = "/api/alerts/K-2026-0001/verification"
    assert client.post(url, headers=h, json={"status": "visited"}).status_code == 422
    assert client.post(url, headers=h, json={"status": "visited", "lon": 74.30, "lat": 31.60}).status_code == 422
    r = client.post(url, headers=h, json={"status": "visited", "lon": ALERT_LON + 0.001, "lat": ALERT_LAT})
    assert r.status_code == 200 and 80 < r.json()["distance_m"] < 110
    client.post(url, headers=h, json={"status": "false_alarm", "note": "crop shed"})
    client.post(url, headers=h, json={"status": "visited", "lon": ALERT_LON, "lat": ALERT_LAT})
    a = client.get("/api/alerts/K-2026-0001", headers=h).json()["properties"]
    assert a["status"] == "false_alarm" and len(a["history"]) == 3


def test_filters(client):
    h = login(client, "viewer1")
    assert len(client.get("/api/alerts?tehsil=Ravi", headers=h).json()["features"]) == 1
    assert client.get("/api/alerts?tehsil=Wahga", headers=h).json()["features"] == []
    assert client.get("/api/alerts?min_ha=2", headers=h).json()["features"] == []
    assert client.get("/api/alerts?since=2026-11-01", headers=h).json()["features"] == []
    assert len(client.get("/api/alerts?flooded=true", headers=h).json()["features"]) == 1


def test_bad_status_and_missing_alert(client):
    h = login(client, "field1")
    assert client.post("/api/alerts/K-2026-0001/verification", headers=h, json={"status": "maybe"}).status_code == 422
    assert client.get("/api/alerts/NOPE", headers=h).status_code == 404


def test_summary_exposure_and_precision(client):
    h = login(client, "viewer1")
    s = client.get("/api/summary", headers=h).json()
    assert s["buildings"]["n"] == 100 and s["alerts"]["open"] == 1 and s["stale"] is True
    assert [r["unit_id"] for r in client.get("/api/exposure?unit_type=tehsil", headers=h).json()] == ["T-Ravi"]
    p = client.get("/api/precision", headers=h).json()
    assert p["n"] == 0 and p["release_ready"] is False


def test_pdfs_and_exports(client):
    h = login(client, "viewer1")
    r = client.get("/api/alerts/K-2026-0001/evidence.pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = client.get("/api/report/pre-monsoon.pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    z = zipfile.ZipFile(BytesIO(client.get("/api/export/exposure.zip", headers=h).content))
    assert set(z.namelist()) == {"kinara_exposure.csv", "README.txt"}
    assert "bld_n" in z.read("kinara_exposure.csv").decode("utf-8-sig").splitlines()[0]
    z = zipfile.ZipFile(BytesIO(client.get("/api/export/alerts.zip", headers=h).content))
    assert json.loads(z.read("kinara_alerts.geojson"))["features"][0]["properties"]["alert_id"] == "K-2026-0001"


def test_admin_creates_user(client):
    a = login(client, "admin1")
    r = client.post("/api/users", headers=a, json={"username": "ac_ravi", "password": "longenough",
                                                    "role": "field_officer"})
    assert r.status_code == 200
    assert "ac_ravi" in [u["username"] for u in client.get("/api/users", headers=a).json()]
    assert "password_hash" not in client.get("/api/users", headers=a).json()[0]
    login(client, "ac_ravi", "longenough")


def test_locate_rejects_outside(client):
    h = login(client, "viewer1")
    assert client.get("/api/locate?lon=73.0&lat=33.7", headers=h).status_code == 422
    assert client.get("/api/locate?lon=74.3&lat=31.5", headers=h).json()["cell_id"].startswith("C")
