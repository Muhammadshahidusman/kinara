// Formatting rules from UIUX.md section 5-6: Western digits with separators, "26 Oct 2026", ha then kanal.
const NUM = new Intl.NumberFormat("en-US");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const fmtN = (v: number | null | undefined): string => (v == null ? "–" : NUM.format(Math.round(v)));

export function fmtDate(s: string | null | undefined): string {
  if (!s) return "–";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (!m) return s;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

/** ISO timestamp to "26 Oct 2026 14:05" in Pakistan time (UTC+5, no daylight saving). */
export function fmtPkt(iso: string | null | undefined): string {
  if (!iso) return "–";
  const t = new Date(iso);
  if (isNaN(t.getTime())) return iso;
  const p = new Date(t.getTime() + 5 * 3600_000);
  const hh = String(p.getUTCHours()).padStart(2, "0");
  const mm = String(p.getUTCMinutes()).padStart(2, "0");
  return `${p.getUTCDate()} ${MONTHS[p.getUTCMonth()]} ${p.getUTCFullYear()} ${hh}:${mm}`;
}

export const fmtPct = (part: number | null | undefined, whole: number | null | undefined): string =>
  part == null || !whole ? "–" : `${Math.round((100 * part) / whole)}%`;

/** Planar distance between two lon/lat points in metres (equirectangular; fine under a few km). */
export function distanceM(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const r = 6371008.8;
  const x = ((lon2 - lon1) * Math.PI) / 180 * Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180);
  const y = ((lat2 - lat1) * Math.PI) / 180;
  return Math.sqrt(x * x + y * y) * r;
}

export const googleMapsUrl = (lat: number, lon: number) =>
  `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;
