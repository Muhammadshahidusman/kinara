"""Exports to Google Drive, each with a provenance sidecar. Also task status."""

from __future__ import annotations

import datetime as dt
import json

import ee

from kinara.config import Settings, get_logger

log = get_logger("kinara.gee.export")


def provenance(cfg: Settings, **extra) -> dict:
    """Everything needed to reproduce an export: run time, ee version, settings sections used."""
    return {
        "run_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "ee_version": ee.__version__,
        "gee_project": cfg["gee"]["project_id"],
        "crs": cfg["project"]["crs_analysis"],
        "floodplain": json.dumps(cfg.get("floodplain", {})),
        "buildings": json.dumps(cfg.get("buildings", {})),
        **{k: (json.dumps(v) if isinstance(v, dict | list) else v) for k, v in extra.items()},
    }


def table_to_drive(fc: ee.FeatureCollection, name: str, cfg: Settings, fmt: str = "CSV",
                   **prov) -> list[str]:
    """Start a table export plus its provenance CSV. Returns the two task ids."""
    folder = cfg["gee"]["drive_folder"]
    t1 = ee.batch.Export.table.toDrive(collection=fc, description=name, folder=folder,
                                       fileNamePrefix=name, fileFormat=fmt)
    t1.start()
    meta = ee.FeatureCollection([ee.Feature(None, provenance(cfg, export=name, **prov))])
    t2 = ee.batch.Export.table.toDrive(collection=meta, description=f"{name}_provenance", folder=folder,
                                       fileNamePrefix=f"{name}_provenance", fileFormat="CSV")
    t2.start()
    log.info(f"started {name} (task {t1.id}) and its provenance (task {t2.id})")
    return [t1.id, t2.id]


def image_to_drive(img: ee.Image, name: str, region: ee.Geometry, cfg: Settings, scale: float,
                   **prov) -> list[str]:
    """Start a cloud-optimised GeoTIFF export plus its provenance CSV."""
    folder = cfg["gee"]["drive_folder"]
    t1 = ee.batch.Export.image.toDrive(image=img, description=name, folder=folder, fileNamePrefix=name,
                                       region=region, scale=scale, crs=cfg["project"]["crs_analysis"],
                                       maxPixels=1e10, fileFormat="GeoTIFF",
                                       formatOptions={"cloudOptimized": True})
    t1.start()
    meta = ee.FeatureCollection([ee.Feature(None, provenance(cfg, export=name, scale_m=scale, **prov))])
    t2 = ee.batch.Export.table.toDrive(collection=meta, description=f"{name}_provenance", folder=folder,
                                       fileNamePrefix=f"{name}_provenance", fileFormat="CSV")
    t2.start()
    log.info(f"started {name} (task {t1.id}) and its provenance (task {t2.id})")
    return [t1.id, t2.id]


def status(limit: int = 20) -> None:
    """Log the most recent Earth Engine tasks."""
    for t in ee.batch.Task.list()[:limit]:
        s = t.status()
        log.info(f"{s.get('description', '?'):40s} {s.get('state', '?'):10s} {s.get('error_message', '')}")
