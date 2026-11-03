-- Kinara PostGIS schema (v0.2). Geometries are stored in EPSG:4326 for the web;
-- compute areas and distances in EPSG:32643 (ST_Transform(geom, 32643)).
-- Load data with: uv run python scripts/load_postgis.py

CREATE EXTENSION IF NOT EXISTS postgis;

-- Floodplain zones under each definition (hand_proxy, bunds, jrc_100yr)
CREATE TABLE IF NOT EXISTS zones (
    zone_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    definition  TEXT NOT NULL,
    area_km2    NUMERIC(10, 2),
    geom        geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS zones_gix ON zones USING GIST (geom);

-- Exposure per reporting unit (the part of a zone, mouza or tehsil inside the floodplain)
CREATE TABLE IF NOT EXISTS exposure (
    unit_id            TEXT PRIMARY KEY,
    unit_type          TEXT NOT NULL CHECK (unit_type IN ('zone', 'mouza', 'tehsil')),
    name               TEXT NOT NULL,
    name_ur            TEXT,
    tehsil             TEXT,
    n_tehsils          INTEGER,               -- mouza polygon crosses this many official tehsils
    area_km2           NUMERIC(10, 2),
    bld_n              INTEGER,
    bld_post2016_n     INTEGER,
    bld_year_unknown_n INTEGER,
    bld_flooded_2025   INTEGER,
    pop_est            INTEGER,
    pop_source         TEXT,
    updated_at         TIMESTAMPTZ DEFAULT now()
);

-- Satellite scenes used by each run (provenance)
CREATE TABLE IF NOT EXISTS scenes (
    scene_id     TEXT PRIMARY KEY,
    sensor       TEXT NOT NULL,           -- S1, S2
    acquired_at  DATE NOT NULL,
    orbit        INTEGER
);

-- One row per detection run
CREATE TABLE IF NOT EXISTS runs (
    run_id       SERIAL PRIMARY KEY,
    started_at   TIMESTAMPTZ DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    settings     JSONB NOT NULL,          -- copy of config/settings.yaml at run time
    scene_ids    TEXT[] NOT NULL,
    n_alerts     INTEGER,
    n_repeats    INTEGER,
    ok           BOOLEAN,
    error        TEXT,
    detail       JSONB                    -- per-orbit outcome (passes, baseline, skipped reason)
);

-- Candidate alerts. Evidence fields that are not filtered on (rise_db, sparkline, scene lists,
-- Sentinel-2 chip metadata) live in props.
CREATE TABLE IF NOT EXISTS alerts (
    alert_id         TEXT PRIMARY KEY,    -- e.g. K-2026-0001
    kind             TEXT NOT NULL CHECK (kind IN ('new_construction', 'land_clearing', 'flood')),
    first_detected   DATE NOT NULL,
    last_seen        DATE,
    n_detections     INTEGER DEFAULT 1,
    area_ha          NUMERIC(10, 2) NOT NULL,
    area_kanal       NUMERIC(10, 1),
    mouza            TEXT,
    mouza_ur         TEXT,
    tehsil           TEXT,
    zone_id          TEXT REFERENCES zones (zone_id),
    distance_river_m INTEGER,
    flooded_2025     BOOLEAN,
    flooded_share    NUMERIC(4, 2),
    status           TEXT NOT NULL DEFAULT 'new'
                     CHECK (status IN ('new', 'visited', 'confirmed', 'false_alarm', 'no_access')),
    run_id           INTEGER REFERENCES runs (run_id),
    orbit            INTEGER,
    lon              DOUBLE PRECISION,
    lat              DOUBLE PRECISION,
    props            JSONB NOT NULL DEFAULT '{}',
    geom             geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS alerts_gix ON alerts USING GIST (geom);
CREATE INDEX IF NOT EXISTS alerts_status ON alerts (status, first_detected DESC);

-- Field verdicts: append-only audit trail
CREATE TABLE IF NOT EXISTS verifications (
    id          SERIAL PRIMARY KEY,
    alert_id    TEXT NOT NULL REFERENCES alerts (alert_id),
    status      TEXT NOT NULL CHECK (status IN ('new', 'visited', 'confirmed', 'false_alarm', 'no_access')),
    note        TEXT,
    user_name   TEXT NOT NULL,
    distance_m  INTEGER,                  -- verifier's GPS distance from the alert, if shared
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS verifications_alert ON verifications (alert_id, created_at);

-- Append-only: nobody (not even the API role) may rewrite the audit trail
CREATE OR REPLACE FUNCTION verifications_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'verifications is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS verifications_no_change ON verifications;
CREATE TRIGGER verifications_no_change BEFORE UPDATE OR DELETE ON verifications
    FOR EACH ROW EXECUTE FUNCTION verifications_append_only();

-- Logins (TRD section 9): argon2 hashes only, never plain passwords
CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('viewer', 'field_officer', 'admin')),
    full_name      TEXT,
    active         BOOLEAN NOT NULL DEFAULT TRUE
);
