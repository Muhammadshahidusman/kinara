# Kinara · Ravi Floodplain Watch

Portfolio: https://muhammadshahidusman.github.io

Flood exposure and candidate new-construction alerts for the Ravi floodplain in Lahore District, built on open satellite data from Google Earth Engine. First users: PDMA Punjab and the Lahore district administration.

## Quick start (Windows)

1. `scripts\setup.bat`: installs uv (if needed), Python 3.12 and all dependencies, then runs the tests.
2. Copy `.env.example` to `.env` and set `KINARA_EE_PROJECT` to your Earth Engine Cloud project (and `KINARA_MOUZA_FILE` if you have a mouza layer). `.env` is never committed.
3. Put the Lahore boundaries in `data\reference\boundaries\`: `Lahore_District_Boundary.shp` and `Lahore_Tehsil_Boundaries.shp` (UTM 43N, tehsil name in a `tehsil` field). They are not in the public repository; OCHA's Pakistan administrative boundaries on HDX are an open alternative.
4. `scripts\gee_auth.bat`: one-time Earth Engine sign-in; checks the datasets over Lahore.
5. Baseline layers: `uv run python scripts/export_baseline.py --orbit 107`, download the Drive folder into `data\gee_exports`, then `scripts\refresh_exposure.bat`.
6. Alerts: `scripts\run_detect.bat` (once) or `scripts\schedule_detect.bat` (daily at 09:00).
7. First login: `uv run python scripts/manage_users.py add <your-name> --role admin`.
8. `scripts\run_api.bat` (API at http://localhost:8000/docs) and `scripts\run_web.bat` (app at http://localhost:5173).

Calibrate the flood thresholds before quoting flooded-building numbers: fill `data\reference\flood_validation_points.csv` (at least 30 geolocated places) and run `uv run python scripts/calibrate_flood.py`.

## Documents

| File | What's in it |
|---|---|
| [PRD.md](PRD.md) | Problem, users, features, success metrics, release plan |
| [TRD.md](TRD.md) | Architecture, data sources, methods, API, data model, licensing |
| [UIUX.md](UIUX.md) | Screens, wireframes, colours, wording, accessibility |

Alerts are candidates from 10 m satellite data and must be verified on site. Kinara does not determine legality.
