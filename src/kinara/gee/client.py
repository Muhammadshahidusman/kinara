"""Earth Engine sign-in and study-area geometry."""

from __future__ import annotations

import ee

from kinara.config import Settings, get_logger

log = get_logger("kinara.gee")

SIMPLIFY_M = 10.0          # boundary simplification before sending to Earth Engine (well below 10 m pixels)
MIN_AREA_RATIO = 0.95      # district geometry must be at least this share of the official area


def init(cfg: Settings) -> None:
    """Initialise Earth Engine with the project from settings.

    Raises:
        RuntimeError: If credentials are missing; run scripts/gee_auth.bat once first.
    """
    project = cfg["gee"]["project_id"]
    if not project:
        raise RuntimeError("No Earth Engine project set. Put KINARA_EE_PROJECT=<your-project> in .env "
                           "(see .env.example).")
    try:
        ee.Initialize(project=project)
    except ee.EEException as e:
        raise RuntimeError(
            f"Earth Engine could not start for project '{project}'. "
            "Run scripts\\gee_auth.bat once, then try again."
        ) from e
    log.info(f"Earth Engine ready (project {project}, ee {ee.__version__})")


def district(cfg: Settings) -> ee.Geometry:
    """Lahore District geometry from the official boundary.

    Uses `gee.district_asset` if set; otherwise reads the local shapefile in
    `area.district_boundary` and sends it to Earth Engine as GeoJSON (no upload needed).
    """
    asset = cfg["gee"].get("district_asset") or ""
    if asset:
        log.info(f"district boundary from asset {asset}")
        return ee.FeatureCollection(asset).geometry()

    from kinara.geo.vector import boundary_geojson  # geopandas only needed here

    path = cfg["area"]["district_boundary"]
    geojson = boundary_geojson(path, simplify_m=SIMPLIFY_M)
    log.info(f"district boundary from {path.name} (simplified to {SIMPLIFY_M:g} m)")
    return ee.Geometry(geojson, opt_proj="EPSG:4326", opt_geodesic=False)


def check_area(geom: ee.Geometry, cfg: Settings) -> float:
    """Return the district area in km2 and fail loudly if it is far below the official figure.

    Raises:
        ValueError: If the geometry is empty or much smaller than expected.
    """
    km2 = geom.area(10).divide(1e6).getInfo()
    expected = cfg["area"]["district_area_km2"]
    if km2 < MIN_AREA_RATIO * expected:
        raise ValueError(f"district geometry is {km2:,.1f} km2, expected about {expected:,.1f} km2. "
                         "Check area.district_boundary or gee.district_asset in settings.")
    return km2
