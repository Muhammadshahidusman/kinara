from pathlib import Path

import pytest

from kinara.config import ROOT, load_settings

# boundaries are kept locally and are not in the public repo
NO_BOUNDARIES = not load_settings()["area"]["district_boundary"].exists()


def test_default_settings_resolve_paths():
    cfg = load_settings()
    assert cfg["project"]["name"] == "Kinara"
    assert cfg["paths"]["processed"].is_absolute()
    assert cfg["paths"]["processed"].exists()
    assert cfg["area"]["district_boundary"] == ROOT / "data/reference/boundaries/Lahore_District_Boundary.shp"


@pytest.mark.skipif(NO_BOUNDARIES, reason="data/reference/boundaries not present")
def test_boundary_file_is_present():
    cfg = load_settings()
    assert cfg["area"]["district_boundary"].exists()


def test_private_values_come_from_env(monkeypatch):
    monkeypatch.setenv("KINARA_EE_PROJECT", "my-ee-project")
    monkeypatch.setenv("KINARA_MOUZA_FILE", "C:/somewhere/mouzas.shp")
    cfg = load_settings()
    assert cfg["gee"]["project_id"] == "my-ee-project"
    assert cfg["area"]["mouza_boundaries"] == Path("C:/somewhere/mouzas.shp").resolve()


def test_settings_file_holds_no_account_values():
    text = (ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "@" not in text and 'project_id: ""' in text


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.yaml")


def test_missing_section_raises(tmp_path: Path):
    f = tmp_path / "s.yaml"
    f.write_text("project: {name: x}\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_settings(f)
