"""WGS 84 to UTM zone 43N without pyproj, plus grid cell ids.

Reused from LPVIS (lahore-poverty/api/app/store.py: utm43n, cell_id_at). The API uses it to turn a
clicked lon/lat into a cell id without loading pyproj or a database.
"""

from __future__ import annotations

import math

A = 6378137.0                 # WGS 84 semi-major axis, m
F = 1 / 298.257223563         # WGS 84 flattening
K0 = 0.9996                   # UTM scale factor
FALSE_EASTING = 500000.0
LON0_43N = 75.0               # central meridian of zone 43N

# Rough Lahore District bounding box (degrees) used to reject obviously wrong points.
LAHORE_BBOX = (73.9, 31.1, 74.8, 31.8)


def utm43n(lon: float, lat: float) -> tuple[float, float]:
    """Convert WGS 84 lon/lat (degrees) to UTM 43N easting/northing (metres).

    Standard transverse Mercator series; accurate to well under a metre inside the zone.

    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees (northern hemisphere).

    Returns:
        (easting, northing) in metres.

    Raises:
        ValueError: If lat is south of the equator or lon is far outside zone 43N.
    """
    if lat < 0:
        raise ValueError("utm43n handles the northern hemisphere only")
    if not 66.0 <= lon <= 84.0:
        raise ValueError(f"longitude {lon} is far outside UTM zone 43N (72 to 78 E)")
    e2 = F * (2 - F)
    ep2 = e2 / (1 - e2)
    phi, lam = math.radians(lat), math.radians(lon)
    lam0 = math.radians(LON0_43N)
    n = A / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    t, c = math.tan(phi) ** 2, ep2 * math.cos(phi) ** 2
    aa = math.cos(phi) * (lam - lam0)
    m = A * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * phi)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
        - (35 * e2**3 / 3072) * math.sin(6 * phi)
    )
    x = K0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120)
    y = K0 * (
        m
        + n
        * math.tan(phi)
        * (aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
           + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720)
    )
    return x + FALSE_EASTING, y


def cell_id_at(lon: float, lat: float, cell_m: float = 500.0) -> str:
    """Grid cell id for a point: C{floor(easting/cell)}_{floor(northing/cell)}.

    Matches `kinara.geo.vector.make_grid`, so ids line up with the vector grid.
    """
    if cell_m <= 0:
        raise ValueError("cell_m must be positive")
    x, y = utm43n(lon, lat)
    return f"C{int(x // cell_m)}_{int(y // cell_m)}"


def in_lahore_bbox(lon: float, lat: float) -> bool:
    """True if the point falls inside the rough Lahore District bounding box."""
    x0, y0, x1, y1 = LAHORE_BBOX
    return x0 <= lon <= x1 and y0 <= lat <= y1
