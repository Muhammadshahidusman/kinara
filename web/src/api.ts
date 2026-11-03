// Typed calls to the Kinara API (src/kinara/api/main.py). Adds the sign-in token, keeps the last good
// response of each GET so the UI can show cached data when the server is unreachable (UIUX.md 7).
export type AlertStatus = "new" | "visited" | "confirmed" | "false_alarm" | "no_access";
export type Role = "viewer" | "field_officer" | "admin";
export const STATUSES: AlertStatus[] = ["new", "visited", "confirmed", "false_alarm", "no_access"];

export interface User { username: string; role: Role; full_name: string }
export interface SparkPoint { day: string; vv_db: number | null }
export interface Chip { available: boolean; scene?: string; date?: string; cloud_pct?: number; reason?: string }
export interface HistoryEvent { status: AlertStatus; note: string; user: string; at: string; distance_m?: number | null }

export interface AlertProps {
  alert_id: string;
  kind: "new_construction" | "land_clearing" | "flood";
  first_detected: string;
  last_seen?: string;
  n_detections?: number;
  area_ha: number;
  area_kanal?: number;
  mouza?: string | null;
  mouza_ur?: string | null;
  tehsil?: string | null;
  flooded_2025?: boolean | null;
  flooded_share?: number | null;
  distance_river_m?: number | null;
  rise_db?: number | null;
  orbit?: number;
  lon?: number;
  lat?: number;
  scenes_after?: string;
  baseline_window?: string;
  n_baseline_scenes?: number;
  sparkline?: SparkPoint[];
  s2_before?: Chip;
  s2_after?: Chip;
  status: AlertStatus;
  history?: HistoryEvent[];
}
export interface AlertFeature { type: "Feature"; geometry: GeoJSON.Geometry; properties: AlertProps }
export interface AlertCollection { type: "FeatureCollection"; features: AlertFeature[] }

export interface ExposureRow {
  unit_id: string; unit_type: "zone" | "tehsil" | "mouza"; name: string; name_ur?: string | null;
  tehsil?: string | null; n_tehsils?: number; area_km2?: number; bld_n: number; bld_post2016_n: number; bld_year_unknown_n?: number;
  bld_flooded_2025: number; pop_est?: number | null; pop_source?: string | null;
}

export interface Run {
  run_id: number; started_at: string; finished_at?: string; run_date?: string; ok: boolean; error?: string | null;
  n_alerts: number; n_repeats: number; scenes: Record<string, { day?: string; orbit?: number }>;
  orbits?: Record<string, { newest_pass?: string; skipped?: string; patches?: number }>;
}

export interface Summary {
  built: boolean;
  floodplain?: { definition: string; label: string; area_km2: number };
  buildings?: { n: number; post2016_n: number; year_unknown_n: number; flooded_2025_n: number; source: string };
  population?: { n: number | null; source: string | null };
  flood_2025?: { calibrated: boolean; orbit: number; scenes_event: string[]; open_ha: number; urban_ha: number;
    overlay?: { url: string; coordinates: [number, number][] } };
  data_dates?: { buildings: string; flood: string };
  alerts: { open: number; total: number; new_this_week: number };
  last_run: Run | null; last_successful_run: string | null; stale: boolean; stale_after_days: number;
  built_utc?: string;
}

export interface Precision { n: number; precision: number | null; ci_low: number | null; ci_high: number | null;
  meets_target: boolean; release_ready: boolean; min_verified: number }

const TOKEN_KEY = "kinara.token";
const USER_KEY = "kinara.user";
const CACHE_PREFIX = "kinara.cache:";

function safeGet(k: string): string | null { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k: string, v: string | null): void {
  try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* storage blocked */ }
}

export const session = {
  token: (): string | null => safeGet(TOKEN_KEY),
  user: (): User | null => { const u = safeGet(USER_KEY); try { return u ? JSON.parse(u) : null; } catch { return null; } },
  save(token: string, user: User) { safeSet(TOKEN_KEY, token); safeSet(USER_KEY, JSON.stringify(user)); },
  clear() { safeSet(TOKEN_KEY, null); safeSet(USER_KEY, null); },
};

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

type Listener = (s: { down: boolean; unauthorised: boolean }) => void;
const listeners = new Set<Listener>();
export const onApiState = (l: Listener) => { listeners.add(l); return () => { listeners.delete(l); }; };
const emit = (down: boolean, unauthorised = false) => listeners.forEach((l) => l({ down, unauthorised }));

export const authHeaders = (): Record<string, string> => {
  const t = session.token();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers: { ...authHeaders(), ...(init.headers ?? {}) } });
  } catch {
    emit(true);
    throw new ApiError(0, "network");
  }
  if (r.status === 401 && !path.endsWith("/auth/token")) { session.clear(); emit(false, true); }
  if (r.status >= 500) emit(true); else emit(false);
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(r.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r;
}

export async function get<T>(path: string): Promise<T> {
  try {
    const data = (await (await request(path)).json()) as T;
    safeSet(CACHE_PREFIX + path, JSON.stringify(data));
    return data;
  } catch (e) {
    const cached = safeGet(CACHE_PREFIX + path);
    if (e instanceof ApiError && e.status === 0 && cached) return JSON.parse(cached) as T;
    throw e;
  }
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await request(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  return r.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<User> {
  const r = await request("/api/auth/token", { method: "POST",
    body: new URLSearchParams({ username, password }) });
  const j = await r.json();
  session.save(j.access_token, j.user);
  return j.user as User;
}

/** Fetch a protected file (PDF, ZIP, PNG) and return an object URL. Caller revokes it. */
export async function blobUrl(path: string): Promise<string> {
  const r = await request(path);
  return URL.createObjectURL(await r.blob());
}

/** Open a protected PDF in a new tab, or download a protected file. */
export async function openFile(path: string, filename?: string): Promise<void> {
  const url = await blobUrl(path);
  const a = document.createElement("a");
  a.href = url;
  if (filename) a.download = filename; else a.target = "_blank";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export interface AlertFilters { status?: AlertStatus | ""; tehsil?: string; since?: string; min_ha?: string; flooded?: boolean }
export function alertsPath(f: AlertFilters = {}, limit = 1000): string {
  const q = new URLSearchParams({ limit: String(limit) });
  if (f.status) q.set("status", f.status);
  if (f.tehsil) q.set("tehsil", f.tehsil);
  if (f.since) q.set("since", f.since);
  if (f.min_ha) q.set("min_ha", f.min_ha);
  if (f.flooded) q.set("flooded", "true");
  return `/api/alerts?${q}`;
}

export const api = {
  summary: () => get<Summary>("/api/summary"),
  alerts: (f?: AlertFilters) => get<AlertCollection>(alertsPath(f)),
  alert: (id: string) => get<AlertFeature>(`/api/alerts/${encodeURIComponent(id)}`),
  exposure: (unitType?: "zone" | "tehsil" | "mouza") =>
    get<ExposureRow[]>(`/api/exposure${unitType ? `?unit_type=${unitType}` : ""}`),
  layer: (name: "zones" | "tehsils" | "mouzas" | "cells" | "river") =>
    get<GeoJSON.FeatureCollection>(`/api/layers/${name}`),
  verify: (id: string, body: { status: AlertStatus; note?: string; lon?: number; lat?: number }) =>
    post<HistoryEvent>(`/api/alerts/${encodeURIComponent(id)}/verification`, body),
  precision: () => get<Precision>("/api/precision"),
  runs: () => get<Run[]>("/api/runs"),
  users: () => get<(User & { active: boolean })[]>("/api/users"),
  addUser: (u: { username: string; password: string; role: Role; full_name: string }) => post("/api/users", u),
  settings: () => get<Record<string, unknown>>("/api/settings"),
};
