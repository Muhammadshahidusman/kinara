"""Vector helpers. Skipped unless geopandas is installed (it is after `uv sync`)."""

import pytest

pytest.importorskip("geopandas")

from kinara.config import load_settings  # noqa: E402
from kinara.geo.utm import in_lahore_bbox  # noqa: E402
from kinara.geo.vector import boundary_geojson  # noqa: E402

# boundaries are kept locally and are not in the public repo
NO_BOUNDARIES = not load_settings()["area"]["district_boundary"].exists()


@pytest.mark.skipif(NO_BOUNDARIES, reason="data/reference/boundaries not present")
def test_official_boundary_to_geojson():
    gj = boundary_geojson(load_settings()["area"]["district_boundary"], simplify_m=10)
    assert gj["type"] in ("Polygon", "MultiPolygon")
    ring = gj["coordinates"][0] if gj["type"] == "Polygon" else gj["coordinates"][0][0]
    lon, lat = ring[0]
    assert in_lahore_bbox(lon, lat)          # really WGS 84 degrees, inside Lahore


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        boundary_geojson(tmp_path / "none.shp")
