"""Export a read-only snapshot of the Kinara API as static files for the public web demo.

Calls every viewer GET endpoint once through FastAPI's TestClient (same code path as the live API) and
writes the responses under <out>/demo-data/, where the demo build of the web app (VITE_DEMO=1) reads
them instead of calling /api. Nothing is written back to data/processed.

Usage: uv run python scripts/export_demo_data.py web/dist-demo
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import kinara.api.main as main
from kinara.api import auth

log = logging.getLogger("export_demo_data")


def main_(out_root: Path) -> None:
    out = out_root / "demo-data"
    if out.exists():
        shutil.rmtree(out)
    (out / "layers").mkdir(parents=True)
    (out / "alerts").mkdir()
    (out / "pdf").mkdir()

    admin = next(u for u in main.store.users() if u.get("role") == "admin")
    token = auth.make_token(admin["username"], "admin", main._key(), 30)
    c = TestClient(main.app, headers={"Authorization": f"Bearer {token}"})

    def get(path: str) -> bytes:
        r = c.get(path)
        r.raise_for_status()
        return r.content

    def save_json(path: str, name: str) -> object:
        data = json.loads(get(path))
        (out / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return data

    summary = json.loads(get("/api/summary"))
    # The run record carries a full copy of settings (local paths, Earth Engine project id): not public.
    for run_key in ("last_run",):
        if isinstance(summary.get(run_key), dict):
            summary[run_key].pop("settings", None)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                                      encoding="utf-8")
    save_json("/api/precision", "precision.json")
    for name in ("zones", "tehsils", "mouzas", "cells", "river"):
        save_json(f"/api/layers/{name}", f"layers/{name}.json")
    (out / "flood_2025.png").write_bytes(get("/api/layers/flood_2025.png"))
    save_json("/api/exposure", "exposure_all.json")
    for unit in ("zone", "tehsil", "mouza"):
        save_json(f"/api/exposure?unit_type={unit}", f"exposure_{unit}.json")

    fc = save_json("/api/alerts?limit=5000", "alerts.json")
    ids = [f["properties"]["alert_id"] for f in fc["features"]]
    n_img = 0
    for aid in ids:
        save_json(f"/api/alerts/{aid}", f"alerts/{aid}.json")
        (out / "pdf" / f"{aid}.pdf").write_bytes(get(f"/api/alerts/{aid}/evidence.pdf"))
        for side in ("before", "after"):
            r = c.get(f"/api/alerts/{aid}/image/{side}.png")
            if r.status_code == 200:
                (out / "evidence").mkdir(exist_ok=True)
                (out / "evidence" / f"{aid}_{side}.png").write_bytes(r.content)
                n_img += 1
    (out / "premonsoon.pdf").write_bytes(get("/api/report/pre-monsoon.pdf"))
    for name in ("exposure", "alerts"):
        (out / f"export_{name}.zip").write_bytes(get(f"/api/export/{name}.zip"))

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    log.info("%d alerts, %d evidence images, %.1f MB in %s", len(ids), n_img, size / 1e6, out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main_(Path(sys.argv[1] if len(sys.argv) > 1 else "web/dist-demo"))
