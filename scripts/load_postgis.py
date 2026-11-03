"""Load the file-backend data (data/processed) into PostGIS, for multi-user use.

Copies zones, exposure, runs, alerts, verifications and users. Safe to re-run: zones and exposure
are replaced; alerts, runs and users are upserted; verifications are appended only if the alert has
none in the database yet (the audit trail is never rewritten).

Run:  set DATABASE_URL=postgresql://kinara:<password>@localhost:5432/kinara
      uv run python scripts/load_postgis.py
"""

from __future__ import annotations

import json
import os

from kinara.api.store import FileStore, PgStore
from kinara.config import load_settings


def main() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("set DATABASE_URL first (see docker-compose.yml)")
    cfg = load_settings()
    src, db = FileStore(cfg["paths"]["processed"]), PgStore(url)

    zones = src.zones()["features"]
    db._q("TRUNCATE exposure", write=True)
    for f in zones:
        p = f["properties"]
        db._q("INSERT INTO zones (zone_id, name, definition, area_km2, geom) VALUES (%s, %s, %s, %s, "
              "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))) ON CONFLICT (zone_id) DO UPDATE SET "
              "name = EXCLUDED.name, definition = EXCLUDED.definition, area_km2 = EXCLUDED.area_km2, "
              "geom = EXCLUDED.geom",
              (p["zone_id"], p["name"], p["definition"], p.get("area_km2"), json.dumps(f["geometry"])), write=True)
    cols = ("unit_id", "unit_type", "name", "name_ur", "tehsil", "n_tehsils", "area_km2", "bld_n", "bld_post2016_n",
            "bld_year_unknown_n", "bld_flooded_2025", "pop_est", "pop_source")
    for r in src.exposure():
        db._q(f"INSERT INTO exposure ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
              tuple(r.get(c) for c in cols), write=True)

    run_map: dict[int, int] = {}
    for r in sorted(src.runs(10_000), key=lambda r: r["run_id"]):
        run_map[r["run_id"]] = db.add_run(r)
    feats = src.alerts(limit=1_000_000)["features"]
    for f in feats:
        f["properties"]["run_id"] = run_map.get(f["properties"].get("run_id"))
    db.upsert_alerts(feats, {}, None)
    ver = json.loads((cfg["paths"]["processed"] / "verifications.json").read_text(encoding="utf-8")) \
        if (cfg["paths"]["processed"] / "verifications.json").exists() else {}
    n_ver = 0
    for aid, entry in ver.items():
        if db._q("SELECT 1 FROM verifications WHERE alert_id = %s LIMIT 1", (aid,)):
            continue
        for h in entry["history"]:
            db._q("INSERT INTO verifications (alert_id, status, note, user_name, distance_m, created_at) "
                  "VALUES (%s, %s, %s, %s, %s, %s)",
                  (aid, h["status"], h.get("note"), h["user"], h.get("distance_m"), h["at"]), write=True)
            n_ver += 1
        db._q("UPDATE alerts SET status = %s WHERE alert_id = %s", (entry["status"], aid), write=True)
    for u in src.users():
        full = src.user(u["username"])
        db.put_user(u["username"], full["password_hash"], u["role"], u["full_name"], u["active"])
    print(f"loaded {len(zones)} zone(s), {len(src.exposure())} exposure rows, {len(run_map)} runs, "
          f"{len(feats)} alerts, {n_ver} verification events, {len(src.users())} users")


if __name__ == "__main__":
    main()
