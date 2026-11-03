# Kinara: Technical Requirements Document

**Version:** 0.2 · **Date:** 3 November 2026 · **Companion to:** PRD.md, UIUX.md

---

## 1. Architecture

```
                       ┌────────────────────────── Google Earth Engine ──────────────────────────┐
                       │ S1_GRD · S2_SR_HARMONIZED · Cloud Score+ · Open Buildings (Temporal, v3) │
                       │ MERIT Hydro HAND · HydroSHEDS · (JRC flood hazard, WorldPop: planned)    │
                       └──────────────▲──────────────────────────────────┬───────────────────────┘
                                      │ ee API (kinara.gee)              │ exports (GeoTIFF, CSV, GeoJSON)
                                      │                                  ▼  + provenance CSV
  Scheduler (Windows Task   ┌─────────┴──────────┐            ┌──────────────────────┐
  Scheduler now, cron  ───▶ │  Pipeline (Python) │ ─────────▶ │ data/gee_exports     │
  later) every S1 pass      │  scripts/*.py      │            │ data/processed       │
                            │  kinara.detect     │            └──────────┬───────────┘
                            │  kinara.validate   │                       │ load
                            └────────────────────┘                       ▼
                                                              ┌──────────────────────┐
                                                              │ PostGIS 16 (Docker)  │  or FileStore (JSON)
                                                              └──────────┬───────────┘  for demos and tests
                                                                         │
                                                              ┌──────────▼───────────┐
                                                              │ FastAPI (kinara.api) │  /api/*
                                                              └──────────┬───────────┘
                                                                         │ JSON / GeoJSON
                                                              ┌──────────▼───────────┐
                                                              │ React + MapLibre     │  web/
                                                              │ (Vite, TypeScript)   │
                                                              └──────────────────────┘
```

Design rules:

1. **Earth Engine does the heavy pixel work; local Python does logic, storage and serving.** Nothing reads full-resolution stacks locally unless a step genuinely needs it.
2. **All Earth Engine access lives in `src/kinara/gee/`.** If licensing forces a move to STAC (Planetary Computer, Copernicus Data Space), only that package changes.
3. **Detection rules exist twice, deliberately**: as numpy functions in `kinara.detect.change` (unit-tested) and as ee expressions in `kinara.gee.flood` (mirrors). Any change to one must be made to the other, with a test. The new-construction rule is the exception: Earth Engine only assembles the radar images and the numpy rule runs on the downloaded pixels, so it exists once.
4. **Every number is traceable**: each export carries a provenance CSV; each run records scene IDs and settings.

## 2. Repository layout

```
Kinara/
├── CLAUDE.md  PRD.md  TRD.md  UIUX.md  README.md
├── pyproject.toml  .python-version  (uv.lock after first `uv sync`)
├── config/settings.yaml          single source of settings
├── src/kinara/
│   ├── config.py                 settings loader, logger
│   ├── geo/utm.py                lon/lat -> UTM 43N, cell ids (pure Python)
│   ├── geo/vector.py             geopandas helpers (clean, grid, majority join)
│   ├── gee/                      Earth Engine: client, collections, floodplain, exposure, flood, export
│   ├── geo/raster.py             sample rasters at points, common grids, polygonize, web overlay
│   ├── gee/                      also fetch (direct downloads) and monitor (S1 passes, S2 evidence chips)
│   ├── detect/change.py          change and flood logic on arrays
│   ├── units.py                  floodplain, tehsil and mouza units (UTM 43N)
│   ├── exposure.py               per-footprint year and flood flag; counts per unit and map cell
│   ├── alerts.py                 patches -> alerts: attributes, de-duplication, K-ids
│   ├── calibrate.py              flood threshold grid search and block cross-validation
│   ├── validate/metrics.py       Wilson precision, spatial blocks
│   └── api/                      FastAPI app, auth (JWT/argon2), reports (PDF), FileStore / PgStore
├── scripts/                      check_gee, export_baseline, fetch_inputs, build_exposure, detect_alerts,
│                                 calibrate_flood, precision_report, manage_users, load_postgis, *.bat
├── tests/                        pytest
├── db/schema.sql                 PostGIS schema
├── docker/ + docker-compose.yml  PostGIS + API
├── web/                          React + MapLibre frontend
└── data/{raw,interim,processed,gee_exports,reference}
```

## 3. Environment (uv)

- Python 3.12 (`.python-version`), managed by **uv**. No conda, no pip in this project.
- Dependencies in `pyproject.toml`: core (always), `api` extra (FastAPI, psycopg, reportlab), `dev` group (pytest, ruff, httpx), `explore` group (geemap, JupyterLab).
- `uv.lock` is created on the first `uv sync` and must be committed. It pins exact versions.

| Task | Command (PowerShell or CMD, from the Kinara folder) |
|---|---|
| First setup | `scripts\setup.bat` (or `uv sync --extra api`) |
| Earth Engine sign-in | `scripts\gee_auth.bat` |
| Run tests and lint | `scripts\run_tests.bat` |
| Start API | `scripts\run_api.bat` then open http://localhost:8000/docs |
| Baseline exports | `uv run python scripts/export_baseline.py` |
| Exposure layers | `scripts\refresh_exposure.bat` (fetch_inputs.py + build_exposure.py) |
| Alerts (one run) | `scripts\run_detect.bat` (detect_alerts.py); daily: `scripts\schedule_detect.bat` |
| Logins | `uv run python scripts/manage_users.py add <name> --role admin` |
| Add a package | `uv add <name>` (or `uv add --optional api <name>`) |
| Frontend | `cd web && npm install && npm run dev` then http://localhost:5173 |

## 4. Data access and licensing

### Sources (all open)

| Dataset | ID / source | Use | Resolution / time |
|---|---|---|---|
| Sentinel-1 GRD | `COPERNICUS/S1_GRD` | Flood extent, new construction | 10 m; 12-day per satellite (6-day where Sentinel-1A and 1C both acquire) |
| Sentinel-2 SR (harmonised) | `COPERNICUS/S2_SR_HARMONIZED` | Evidence imagery, cross-checks | 10 m; 5-day; clouds |
| Cloud Score+ | `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | S2 cloud mask (cs_cdf >= 0.6) | per scene |
| Open Buildings 2.5D Temporal | `GOOGLE/Research/open-buildings-temporal/v1` | Building presence by year | 4 m effective; annual 2016 to 2023 |
| Open Buildings v3 | `GOOGLE/Research/open-buildings/v3/polygons` | Building counts, footprint area | about 2022-23 imagery |
| MERIT Hydro | `MERIT/Hydro/v1_0_1` (band `hnd`) | HAND floodplain proxy | 90 m |
| HydroSHEDS rivers | `WWF/HydroSHEDS/v1/FreeFlowingRivers` | Ravi centreline | vector |
| JRC flood hazard (planned) | JRC Global Flood Hazard Maps, 100-yr | Floodplain definition C | 3 arc-sec |
| WorldPop R2025A | `WorldPop/GP/100m/R2025A/v1/pop` (CC BY 4.0) | Population estimate per unit (2025) | 100 m; 2015-2030 (later years projected) |
| OpenStreetMap (planned) | Geofabrik Pakistan extract | Bunds, roads | vector |
| Lahore boundaries | `data/reference/boundaries` (official, from MS_Project) | Study area, tehsils | vector, UTM 43N |
| Mouza boundaries | external file named in `area.mouza_boundaries` (MS_Project; 362 mouzas with Urdu names) | Mouza names on alerts and exposure | vector. **Source and licence not yet confirmed, so the file is not copied into this repo.** |
| Basemap (web only) | OpenFreeMap Positron; EOX Sentinel-2 cloudless 2023 | Map background; satellite toggle | tiles. EOX 2023 is CC BY-NC-SA 4.0 (non-commercial): confirm it fits the pilot or switch to the CC BY 2016 layer |

### Licensing (must read before handover)

Earth Engine is free for research and noncommercial use. Its terms say government agencies may **not** use it free for "the production of tooling for management, policy, or web applications" or for services "maintained on an on-going basis", unless the agency is in a UN Least Developed Country or doing scholarly research. Pakistan is not an LDC.

So: development, prototyping and a research-framed pilot run on the free tier under the developer's account. **Before a department uses Kinara operationally**, either (a) the department obtains an Earth Engine commercial licence, or (b) `kinara.gee` is replaced by a STAC backend (`pystac-client` + `odc-stac` on Microsoft Planetary Computer `sentinel-1-rtc` / `sentinel-2-l2a`, and Open Buildings Temporal downloaded from Google Cloud Storage under CC-BY 4.0 / ODbL). Decision owner: project owner with the pilot department. Source: https://earthengine.google.com/noncommercial

## 5. Processing methods

### 5.1 Floodplain zone (`kinara.gee.floodplain`)

v0.1: **HAND proxy** = within `river_buffer_m` (4,000 m) of HydroSHEDS reaches with `UPLAND_SKM >= 10,000` AND MERIT HAND <= `hand_max_m` (5 m), clipped to the district, vectorised at 90 m.
Planned: **bund-to-river polygon** (digitised from OSM and imagery; officials recognise it) and **JRC 100-year** extent. The UI shows which definition is active. The 2025 flood extent is never used to define the floodplain.

### 5.2 Building cohorts (`kinara.gee.exposure.first_built_year`)

For each year 2016 to 2023, `building_presence >= 0.5` (sensitivity 0.4 / 0.6). The minimum year with presence is the "first built" year; 2016 means "on or before 2016". Noise check: pixels built in 2016 but not 2023 ("lost") should be a small fraction of "new"; if lost/new > 0.2 the cohort map is not reliable at that threshold.

### 5.3 August 2025 flood extent (`kinara.gee.flood`, mirrored in `kinara.detect.change.flood_mask`)

- Before: linear-power mean of VV, 1 Jul to 15 Aug 2025. After: 26 Aug to 5 Sep 2025. Same relative orbit where possible (`--orbit`).
- Open land: after <= -18 dB AND at least 3 dB darker.
- Built-up (Open Buildings 2023 presence): at least 3 dB **brighter** (double bounce between floodwater and walls). A dark-only threshold misses flooded housing societies.
- Thresholds are starting values. Calibrate on at least 30 geolocated flood locations from news and drone imagery: fill `data/reference/flood_validation_points.csv` (flooded AND dry places) and run `scripts/calibrate_flood.py`. It samples the same composites in Earth Engine, grid-searches the three thresholds with the numpy rule and reports a 2 km block cross-validated score (quote that one, not the in-sample best). Record the chosen values in settings and set `applied: true` in `data/interim/flood_calibration.json`.
- First result with the starting values (orbit 107, one scene on 28 Aug 2025, three pre-flood scenes): 2,339 ha open-land flood, 214 ha built-up flood, 1,354 of 216,258 floodplain buildings flagged. Only 1.6% of buildings rose by 3 dB or more (7.6% at 1.5 dB), so the built-up threshold is probably too strict; the UI and reports label the flooded count provisional until calibration.

### 5.4 New-construction alerts (`kinara.detect.change`)

1. Baseline: linear-mean VV of the previous 3 months, same orbit.
2. Candidate pixels: VV rose by at least `built_increase_db` (3 dB) on each of the last `persistence_passes` (2) passes.
3. Restrict to the floodplain zone; drop pixels already built in Open Buildings 2023.
4. Connected components (8-connected); drop patches under `min_alert_area_ha` (0.5 ha).
5. Attach mouza and tehsil by majority overlap, distance to river, flooded-2025 flag.
6. De-duplicate against all earlier alerts (IoU > 0.3, or within 20 m: construction grows outward), updating `last_seen` and `n_detections`; a closed alert is not reopened.

Implementation (`scripts/detect_alerts.py`): per relative orbit (`change_detection.orbits`), Earth Engine builds the baseline and the newest passes as int16 dB×100 and `kinara.gee.fetch.pixels` downloads them in 1,024 px tiles on a fixed 10 m UTM grid over the floodplain (tiles outside it are skipped). Steps 2 to 6 run locally with `kinara.detect.change` and `kinara.alerts`. Evidence per new alert: mean VV per pass for the last 8 passes (sparkline) and Sentinel-2 before/after chips (least-cloudy scene, alert outline in yellow). A run whose newest pass was already processed exits quietly; every run, including failures, is written to `runs` with scene IDs and a settings snapshot. Alerts are stored before the evidence step; evidence downloads retry transient network errors (4 attempts, 5-20 s backoff) and anything still missing is filled later with `--backfill-evidence`, so a dropped connection never loses a run.

### 5.6 Exposure (`scripts/build_exposure.py`, `kinara.exposure`)

Open Buildings v3 footprints (confidence >= 0.75) touching the floodplain are downloaded as centroids (216,258; matches the Earth Engine export). Each centroid takes the earliest `first_built_year` in a 3×3 (12 m) window and the `flooded` value of `flood_2025.tif`; counts are summed per tehsil and mouza clipped to the floodplain and per 200 m map cell (with cumulative counts per year for the timeline). About 4% of footprints have no temporal year and are counted separately. Population: WorldPop R2025A (2025) summed over the floodplain part of each unit, rounded to 10.

### 5.5 Validation (`kinara.validate.metrics`)

- **Release gate**: precision >= 0.80 measured as the **lower** bound of the 95% Wilson interval on at least 300 verified alerts. 9 of 10 confirmed does not pass (lower bound about 0.60).
- Verification sample: stratified by tehsil and alert size; reviewers use Google Earth Pro historical imagery before field visits.
- Exposure areas reported to PDMA use stratified accuracy assessment with area adjustment (Olofsson et al. 2014), not raw pixel counts.
- Any model tuned on verdicts uses spatial block folds (`block_folds`, 2 km blocks) so neighbouring alerts never sit in train and test together.

## 6. Data model

Defined in `db/schema.sql`. Tables: `zones`, `exposure`, `scenes`, `runs`, `alerts` (filterable fields as columns, the rest of the evidence in `props` JSONB), `verifications` (append-only, enforced by a trigger), `users`. Geometries stored in EPSG:4326 for the web; areas and distances computed in EPSG:32643.

Alert statuses: `new`, `visited` (set automatically when a field officer opens the alert within 300 m by GPS; never overwrites a verdict), `confirmed`, `false_alarm`, `no_access` ("Couldn't access"; not counted in precision).

Alert ID format: `K-<year>-<4-digit sequence>`, e.g. `K-2026-0042`.

File backend (no database): `data/processed/zones.geojson`, `alerts.geojson`, `exposure.json`, `verifications.json`, `runs.json`, `users.json` (written atomically via a temp file). Static layers built by `build_exposure.py` (`tehsils`, `mouzas`, `cells`, `river` GeoJSON, `flood_2025.png`, `summary.json`) are files for both backends. `scripts/load_postgis.py` copies the file backend into PostGIS.

## 7. API (v0.2)

All routes except `health` and `auth/token` need a bearer token. The role in brackets is the minimum.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | backend, version (open) |
| POST | `/api/auth/token` | OAuth2 password form -> JWT (open) |
| GET | `/api/auth/me` | signed-in user [viewer] |
| GET | `/api/summary` | headline numbers, provenance, alert counts, last run, stale flag [viewer] |
| GET | `/api/zones`, `/api/layers/{tehsils,mouzas,cells,river}` | map layers (GeoJSON) [viewer] |
| GET | `/api/layers/flood_2025.png` | flood overlay; corners in `summary.flood_2025.overlay` [viewer] |
| GET | `/api/exposure?unit_type=` | exposure per zone / tehsil / mouza [viewer] |
| GET | `/api/alerts?status=&tehsil=&since=&min_ha=&flooded=&limit=` | alerts, newest first (GeoJSON) [viewer] |
| GET | `/api/alerts/{id}` | one alert + verification history [viewer] |
| GET | `/api/alerts/{id}/image/{before,after}.png` | Sentinel-2 evidence chip [viewer] |
| GET | `/api/alerts/{id}/evidence.pdf` | one-page A4 evidence sheet [viewer] |
| POST | `/api/alerts/{id}/verification` | `{status, note, lon?, lat?}`; user from the token [field_officer] |
| GET | `/api/report/pre-monsoon.pdf` | pre-monsoon report [viewer] |
| GET | `/api/export/{exposure,alerts}.zip` | CSV / GeoJSON + README of fields [viewer] |
| GET | `/api/precision` | release-gate precision [viewer] |
| GET | `/api/locate?lon=&lat=` | 500 m cell id for a point [viewer] |
| GET | `/api/runs`, `/api/settings`, `/api/users`; POST `/api/users` | operator views [admin] |

Backend chosen by `DATABASE_URL` (PostGIS) or its absence (files).

## 8. Scheduling

- Development: manual runs.
- Pilot: `scripts\schedule_detect.bat` registers a daily 09:00 Windows Task Scheduler job running `run_detect.bat`; it exits quietly when no new Sentinel-1 pass exists since the last successful run (tracked in `runs`) and logs to `data/interim/detect_log.txt`.
- Server: cron or a container scheduler, same script. Each run writes a `runs` row with scene IDs, settings snapshot, alert count and success flag.

## 9. Security and privacy

- OAuth2 password flow, argon2id hashes, JWT (12 h, `api.token_minutes`), roles `viewer` < `field_officer` < `admin`. The user record is re-read on every request, so disabling a user takes effect at once. Verifier names come from the token, never from the request body.
- Signing key: `KINARA_SECRET_KEY` (required by docker-compose). On the development PC a random key is kept in `data/processed/.secret_key` (git-ignored).
- Still localhost / intranet only until hosting is decided: the app has no rate limiting or TLS of its own; put it behind a reverse proxy with HTTPS.
- Secrets only in `.env` (never committed). Database password set via `POSTGRES_PASSWORD`.
- No personal data about residents is stored. Verifier names are stored for the audit trail only.

## 10. Quality requirements

| Area | Requirement |
|---|---|
| Tests | pytest for every function with logic; detection rules tested on synthetic arrays; API tested with FileStore |
| Lint | ruff clean before every commit |
| CRS | Analysis in EPSG:32643; never compute area in EPSG:4326 |
| Reproducibility | uv.lock committed; settings snapshot per run; provenance CSV per export |
| Performance | API p95 < 300 ms for alert list (1,000 alerts); map first load < 3 s on 4G |
| Availability (pilot) | Best effort; failed runs logged and visible to admin |

## 11. Reused from LPVIS (MS_Project/lahore-poverty)

| Kinara module | LPVIS source | Change |
|---|---|---|
| `kinara/config.py` | `src/lpvis/config.py` | settings.yaml, Kinara paths |
| `kinara/geo/utm.py` | `api/app/store.py` (`utm43n`, `cell_id_at`) | input checks, configurable cell size |
| `kinara/geo/vector.py` | `src/lpvis/geo.py` | kept `polygons_only`, `make_grid`, `majority_join`, `accounting` |
| `kinara/validate/metrics.py` | `src/lpvis/cv.py` | blocks in metres; added Wilson precision |
| `kinara/gee/collections.py` | `scripts/05_gee_export.py` (`buildings_collection`) | Open Buildings year filter with the UTC fix |
| `kinara/gee/exposure.py` | `scripts/05c_building_morphology.py` (`morph`) | reduced to exposure fields |
| `kinara/api/store.py` | `api/app/store.py` | same FileStore / PgStore pattern, new tables, psycopg 3 |
| `docker-compose.yml` | `docker-compose.yml` | password from .env, schema auto-load |
| `scripts/gee_auth.bat` | `bat_Files/gee_auth.bat` | uv instead of conda |
| `data/reference/place_names_roman.tsv` | `data/place_names_roman.tsv` | unchanged; for Urdu labels |

Not reused: wealth models, DHS/PSLM code (DHS data is not open), thesis figures.

## 12. Known limitations

- 10 m pixels: single houses and vertical additions are invisible.
- Sentinel-1 increases can come from metal sheds, parked vehicles, crop structures and wet soil; persistence and minimum area reduce but don't remove these.
- Open Buildings Temporal ends in 2023; 2024 onward comes from Sentinel-1 only.
- HAND at 90 m is coarse near embankments; the bund-based zone will replace it as the default.
- Flood thresholds are uncalibrated (section 5.3); the flooded-building count is provisional and probably low.
- Agricultural change: October-November rice harvest and post-monsoon drying raise backscatter against a monsoon-season baseline. The first complete run (3 Nov 2026, orbits 107, 34 and 100) produced 510 new candidate alerts after de-duplication (752 patches before); expect many false alarms until verdicts show which settings to tighten (`built_increase_db`, `persistence_passes`, or a same-season baseline from the previous year).
- Mouza names depend on an external boundary file whose licence is not yet confirmed.
