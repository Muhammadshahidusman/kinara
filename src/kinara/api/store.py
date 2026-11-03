"""Data access for the API, two interchangeable backends with the same methods.

Pattern reused from LPVIS (lahore-poverty/api/app/store.py):
  FileStore  reads GeoJSON / JSON in data/processed (no database; good for demos and tests)
  PgStore    queries PostGIS (db/schema.sql) for multi-user use
`open_store()` picks PgStore when DATABASE_URL is set, otherwise FileStore.

Static map layers built by scripts/build_exposure.py (tehsils, mouzas, cells, river, flood overlay,
summary) are files in data/processed for both backends; see `read_layer`.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import threading
from pathlib import Path
from typing import Any, Protocol

from kinara.config import settings

STATUSES = ("new", "visited", "confirmed", "false_alarm", "no_access")
FINAL = ("confirmed", "false_alarm", "no_access")
ROLES = ("viewer", "field_officer", "admin")
LAYERS = ("zones", "tehsils", "mouzas", "cells", "river")
Record = dict[str, Any]
EMPTY_FC: Record = {"type": "FeatureCollection", "features": []}


def _clean(rec: Record) -> Record:
    """numpy scalars to Python, NaN to None, floats rounded, dates to ISO strings for JSON."""
    out: Record = {}
    for k, v in rec.items():
        if hasattr(v, "item"):
            v = v.item()
        if isinstance(v, float):
            v = None if math.isnan(v) else round(v, 4)
        elif isinstance(v, dt.datetime | dt.date):
            v = v.isoformat()
        elif v.__class__.__name__ == "Decimal":
            v = float(v)
        out[k] = v
    return out


def resolve_status(current: str, incoming: str) -> str:
    """Status after a verification event. An automatic 'visited' never overwrites a field verdict."""
    if incoming == "visited" and current != "new":
        return current
    return incoming


def matches(p: Record, status: str | None, tehsil: str | None, since: str | None, min_ha: float | None,
            flooded: bool | None) -> bool:
    """Alert filter shared by both backends' Python paths (UIUX.md 4.3)."""
    return ((not status or p.get("status") == status)
            and (not tehsil or p.get("tehsil") == tehsil)
            and (not since or str(p.get("first_detected", "")) >= since)
            and (min_ha is None or (p.get("area_ha") or 0) >= min_ha)
            and (flooded is None or bool(p.get("flooded_2025")) == flooded))


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def read_layer(processed: Path, name: str) -> Any:
    """A static file built by scripts/build_exposure.py, or None when it hasn't been built."""
    f = Path(processed) / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


class Store(Protocol):
    name: str

    def zones(self) -> Record: ...
    def exposure(self, unit_type: str | None = None) -> list[Record]: ...
    def alerts(self, status: str | None = None, limit: int = 200, tehsil: str | None = None,
               since: str | None = None, min_ha: float | None = None, flooded: bool | None = None) -> Record: ...
    def alert(self, alert_id: str) -> Record | None: ...
    def set_verification(self, alert_id: str, status: str, note: str, user: str,
                         distance_m: float | None = None) -> Record | None: ...
    def upsert_alerts(self, new: list[Record], seen: dict[str, str], run_id: int | None) -> None: ...
    def update_alert(self, alert_id: str, props: Record) -> bool: ...
    def add_run(self, run: Record) -> int: ...
    def runs(self, limit: int = 50) -> list[Record]: ...
    def user(self, username: str) -> Record | None: ...
    def users(self) -> list[Record]: ...
    def put_user(self, username: str, password_hash: str, role: str, full_name: str = "",
                 active: bool = True) -> None: ...


class FileStore:
    """JSON files in data/processed: alerts.geojson, verifications.json, runs.json, users.json."""

    name = "files"

    def __init__(self, processed: Path | None = None):
        self.P = Path(processed or settings()["paths"]["processed"])
        self._lock = threading.Lock()

    def _read(self, name: str, default: Any) -> Any:
        f = self.P / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default

    def _write(self, name: str, data: Any) -> None:
        tmp = self.P / f"{name}.tmp"
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.P / name)       # atomic on the same drive

    def _verifications(self) -> dict[str, Record]:
        return self._read("verifications.json", {})

    def zones(self) -> Record:
        return self._read("zones.geojson", EMPTY_FC)

    def exposure(self, unit_type: str | None = None) -> list[Record]:
        rows = [_clean(r) for r in self._read("exposure.json", [])]
        rows = [r for r in rows if not unit_type or r.get("unit_type") == unit_type]
        return sorted(rows, key=lambda r: r.get("bld_n") or 0, reverse=True)

    def _alert_features(self) -> list[Record]:
        fc = self._read("alerts.geojson", EMPTY_FC)
        ver = self._verifications()
        for f in fc["features"]:
            v = ver.get(str(f["properties"].get("alert_id")))
            f["properties"]["status"] = v["status"] if v else f["properties"].get("status", "new")
        return fc["features"]

    def alerts(self, status: str | None = None, limit: int = 200, tehsil: str | None = None,
               since: str | None = None, min_ha: float | None = None, flooded: bool | None = None) -> Record:
        feats = [f for f in self._alert_features()
                 if matches(f["properties"], status, tehsil, since, min_ha, flooded)]
        feats.sort(key=lambda f: (f["properties"].get("first_detected", ""), f["properties"]["alert_id"]),
                   reverse=True)
        return {"type": "FeatureCollection", "features": feats[:limit]}

    def alert(self, alert_id: str) -> Record | None:
        for f in self._alert_features():
            if str(f["properties"].get("alert_id")) == alert_id:
                f["properties"]["history"] = self._verifications().get(alert_id, {}).get("history", [])
                return f
        return None

    def set_verification(self, alert_id: str, status: str, note: str, user: str,
                         distance_m: float | None = None) -> Record | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        current = self.alert(alert_id)
        if current is None:
            return None
        with self._lock:
            ver = self._verifications()
            entry = ver.get(alert_id, {"history": []})
            event = {"status": status, "note": note, "user": user, "distance_m": distance_m, "at": now_utc()}
            entry["history"].append(event)
            entry["status"] = resolve_status(current["properties"]["status"], status)
            ver[alert_id] = entry
            self._write("verifications.json", ver)
        return event

    def upsert_alerts(self, new: list[Record], seen: dict[str, str], run_id: int | None) -> None:
        """Append new alert features; for repeats, update last_seen and the detection count."""
        with self._lock:
            fc = self._read("alerts.geojson", {"type": "FeatureCollection", "features": []})
            for f in fc["features"]:
                p = f["properties"]
                if p["alert_id"] in seen:
                    p["last_seen"] = max(str(p.get("last_seen") or ""), seen[p["alert_id"]])
                    p["n_detections"] = int(p.get("n_detections") or 1) + 1
            for f in new:
                f["properties"].setdefault("run_id", run_id)
            fc["features"].extend(new)
            self._write("alerts.geojson", fc)

    def update_alert(self, alert_id: str, props: Record) -> bool:
        """Merge evidence properties (sparkline, Sentinel-2 chips) into one alert. Never touches status."""
        props = {k: v for k, v in props.items() if k not in ("alert_id", "status", "history")}
        with self._lock:
            fc = self._read("alerts.geojson", {"type": "FeatureCollection", "features": []})
            for f in fc["features"]:
                if f["properties"].get("alert_id") == alert_id:
                    f["properties"].update(props)
                    self._write("alerts.geojson", fc)
                    return True
        return False

    def add_run(self, run: Record) -> int:
        with self._lock:
            runs = self._read("runs.json", [])
            run_id = max((r["run_id"] for r in runs), default=0) + 1
            runs.append({"run_id": run_id, **run})
            self._write("runs.json", runs)
        return run_id

    def runs(self, limit: int = 50) -> list[Record]:
        return sorted(self._read("runs.json", []), key=lambda r: r["run_id"], reverse=True)[:limit]

    def user(self, username: str) -> Record | None:
        u = self._read("users.json", {}).get(username)
        return {"username": username, **u} if u else None

    def users(self) -> list[Record]:
        return [{"username": k, **{f: v[f] for f in ("role", "full_name", "active")}}
                for k, v in sorted(self._read("users.json", {}).items())]

    def put_user(self, username: str, password_hash: str, role: str, full_name: str = "",
                 active: bool = True) -> None:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        with self._lock:
            users = self._read("users.json", {})
            users[username] = {"password_hash": password_hash, "role": role, "full_name": full_name,
                               "active": active}
            self._write("users.json", users)


# columns stored first-class in PostGIS; every other alert property lives in alerts.props (JSONB)
ALERT_COLS = ("alert_id", "kind", "first_detected", "last_seen", "n_detections", "area_ha", "area_kanal",
              "mouza", "mouza_ur", "tehsil", "zone_id", "distance_river_m", "flooded_2025", "flooded_share",
              "status", "run_id", "orbit", "lon", "lat")


class PgStore:
    """PostGIS backend. Tables and columns are defined in db/schema.sql."""

    name = "postgis"

    def __init__(self, url: str):
        import psycopg  # imported here so the file backend works without it

        self._psycopg = psycopg
        self.url = url

    def _q(self, sql: str, params: tuple = (), write: bool = False) -> list[Record]:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self.url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            if write:
                conn.commit()
            return [_clean(dict(r)) for r in rows]

    @staticmethod
    def _fc(rows: list[Record]) -> Record:
        feats = []
        for r in rows:
            geom = json.loads(r.pop("geom"))
            props = {**(r.pop("props", None) or {}), **r}
            feats.append({"type": "Feature", "geometry": geom, "properties": props})
        return {"type": "FeatureCollection", "features": feats}

    def zones(self) -> Record:
        return self._fc(self._q("SELECT zone_id, name, definition, ST_AsGeoJSON(geom) AS geom FROM zones"))

    def exposure(self, unit_type: str | None = None) -> list[Record]:
        if unit_type:
            return self._q("SELECT * FROM exposure WHERE unit_type = %s ORDER BY bld_n DESC", (unit_type,))
        return self._q("SELECT * FROM exposure ORDER BY bld_n DESC")

    def alerts(self, status: str | None = None, limit: int = 200, tehsil: str | None = None,
               since: str | None = None, min_ha: float | None = None, flooded: bool | None = None) -> Record:
        where, params = [], []
        for cond, val in (("status = %s", status), ("tehsil = %s", tehsil), ("first_detected >= %s", since),
                          ("area_ha >= %s", min_ha), ("flooded_2025 = %s", flooded)):
            if val is not None and val != "":
                where.append(cond)
                params.append(val)
        sql = (f"SELECT {', '.join(ALERT_COLS)}, props, ST_AsGeoJSON(geom) AS geom FROM alerts "
               f"{'WHERE ' + ' AND '.join(where) if where else ''} "
               "ORDER BY first_detected DESC, alert_id DESC LIMIT %s")
        return self._fc(self._q(sql, (*params, limit)))

    def alert(self, alert_id: str) -> Record | None:
        rows = self._q(f"SELECT {', '.join(ALERT_COLS)}, props, ST_AsGeoJSON(geom) AS geom FROM alerts "
                       "WHERE alert_id = %s", (alert_id,))
        if not rows:
            return None
        f = self._fc(rows)["features"][0]
        f["properties"]["history"] = self._q(
            "SELECT status, note, user_name AS user, distance_m, created_at AS at FROM verifications "
            "WHERE alert_id = %s ORDER BY created_at", (alert_id,))
        return f

    def set_verification(self, alert_id: str, status: str, note: str, user: str,
                         distance_m: float | None = None) -> Record | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        cur = self._q("SELECT status FROM alerts WHERE alert_id = %s", (alert_id,))
        if not cur:
            return None
        self._q("UPDATE alerts SET status = %s WHERE alert_id = %s",
                (resolve_status(cur[0]["status"], status), alert_id), write=True)
        return self._q("INSERT INTO verifications (alert_id, status, note, user_name, distance_m) "
                       "VALUES (%s, %s, %s, %s, %s) "
                       "RETURNING status, note, user_name AS user, distance_m, created_at AS at",
                       (alert_id, status, note, user, distance_m), write=True)[0]

    def upsert_alerts(self, new: list[Record], seen: dict[str, str], run_id: int | None) -> None:
        for aid, day in seen.items():
            self._q("UPDATE alerts SET last_seen = GREATEST(COALESCE(last_seen, first_detected), %s::date), "
                    "n_detections = COALESCE(n_detections, 1) + 1 WHERE alert_id = %s", (day, aid), write=True)
        for f in new:
            p = {**f["properties"], "run_id": f["properties"].get("run_id", run_id)}
            cols = [c for c in ALERT_COLS if c in p]
            extra = {k: v for k, v in p.items() if k not in ALERT_COLS and k != "history"}
            self._q(f"INSERT INTO alerts ({', '.join(cols)}, props, geom) VALUES "
                    f"({', '.join(['%s'] * len(cols))}, %s::jsonb, "
                    "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))) ON CONFLICT (alert_id) DO NOTHING",
                    (*[p[c] for c in cols], json.dumps(extra), json.dumps(f["geometry"])), write=True)

    def update_alert(self, alert_id: str, props: Record) -> bool:
        extra = {k: v for k, v in props.items() if k not in ALERT_COLS and k != "history"}
        return bool(self._q("UPDATE alerts SET props = props || %s::jsonb WHERE alert_id = %s RETURNING alert_id",
                            (json.dumps(extra), alert_id), write=True))

    def add_run(self, run: Record) -> int:
        for sid, info in (run.get("scenes") or {}).items():
            self._q("INSERT INTO scenes (scene_id, sensor, acquired_at, orbit) VALUES (%s, 'S1', %s, %s) "
                    "ON CONFLICT DO NOTHING", (sid, info.get("day"), info.get("orbit")), write=True)
        return self._q("INSERT INTO runs (started_at, finished_at, settings, scene_ids, n_alerts, n_repeats, ok, "
                       "error, detail) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb) RETURNING run_id",
                       (run.get("started_at"), run.get("finished_at"), json.dumps(run.get("settings", {})),
                        list(run.get("scenes") or {}), run.get("n_alerts"), run.get("n_repeats"), run.get("ok"),
                        run.get("error"), json.dumps(run.get("orbits", {}))), write=True)[0]["run_id"]

    def runs(self, limit: int = 50) -> list[Record]:
        rows = self._q("SELECT run_id, started_at, finished_at, scene_ids, n_alerts, n_repeats, ok, error, "
                       "detail AS orbits FROM runs ORDER BY run_id DESC LIMIT %s", (limit,))
        for r in rows:
            r["scenes"] = {s: {} for s in r.pop("scene_ids") or []}
        return rows

    def user(self, username: str) -> Record | None:
        rows = self._q("SELECT username, password_hash, role, full_name, active FROM users WHERE username = %s",
                       (username,))
        return rows[0] if rows else None

    def users(self) -> list[Record]:
        return self._q("SELECT username, role, full_name, active FROM users ORDER BY username")

    def put_user(self, username: str, password_hash: str, role: str, full_name: str = "",
                 active: bool = True) -> None:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        self._q("INSERT INTO users (username, password_hash, role, full_name, active) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, "
                "full_name = EXCLUDED.full_name, active = EXCLUDED.active",
                (username, password_hash, role, full_name, active), write=True)


def open_store() -> Store:
    url = os.getenv("DATABASE_URL")
    return PgStore(url) if url else FileStore()
