"""Load config/settings.yaml and resolve paths relative to the project root.

Adapted from LPVIS (lahore-poverty/src/lpvis/config.py): one YAML file, paths resolved once,
data folders created on load.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "settings.yaml"
PATH_KEYS = ("raw", "interim", "processed", "reference", "gee_exports")
AREA_PATH_KEYS = ("district_boundary", "tehsil_boundaries", "mouza_boundaries")

Settings = dict[str, Any]


def _resolve(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (ROOT / p).resolve()


def load_settings(path: str | Path | None = None) -> Settings:
    """Read the settings file and turn every path entry into an absolute Path.

    Args:
        path: Settings file. Defaults to $KINARA_CONFIG, then config/settings.yaml.
            $KINARA_EE_PROJECT and $KINARA_MOUZA_FILE (from the environment or .env) override
            `gee.project_id` and `area.mouza_boundaries`.

    Returns:
        The settings dictionary with `paths.*` and `area.*` file entries as Path objects
        (None where an optional `area.*` file is left empty).

    Raises:
        FileNotFoundError: If the settings file does not exist.
        KeyError: If a required section is missing.
    """
    load_dotenv(ROOT / ".env", override=False)   # private local values; .env is never committed
    path = Path(path or os.getenv("KINARA_CONFIG") or DEFAULT_CONFIG)
    if not path.exists():
        raise FileNotFoundError(f"settings file not found: {path}")
    with open(path, encoding="utf-8") as f:
        cfg: Settings = yaml.safe_load(f)

    for section in ("project", "paths", "area", "gee"):
        if section not in cfg:
            raise KeyError(f"settings file {path} has no '{section}' section")

    # account-specific values come from the environment so the versioned settings file holds none
    cfg["gee"]["project_id"] = os.getenv("KINARA_EE_PROJECT") or cfg["gee"].get("project_id") or ""
    if os.getenv("KINARA_MOUZA_FILE"):
        cfg["area"]["mouza_boundaries"] = os.getenv("KINARA_MOUZA_FILE")

    for key in PATH_KEYS:
        cfg["paths"][key] = _resolve(cfg["paths"][key])
        cfg["paths"][key].mkdir(parents=True, exist_ok=True)
    for key in AREA_PATH_KEYS:
        if key in cfg["area"]:
            # an empty entry (e.g. no mouza layer) becomes None rather than the project root
            cfg["area"][key] = _resolve(cfg["area"][key]) if cfg["area"][key] else None
    return cfg


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Cached settings for code that only reads the default file."""
    return load_settings()


def get_logger(name: str) -> logging.Logger:
    """Leveled, timestamped logger shared by scripts and the API."""
    logging.basicConfig(
        level=os.getenv("KINARA_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)
