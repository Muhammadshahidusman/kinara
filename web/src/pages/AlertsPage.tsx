// UIUX.md 4.3: filters, sort (nearest uses GPS), list + map side by side on desktop, list/map toggle on mobile.
import { useEffect, useMemo, useState } from "react";
import { api, STATUSES, type AlertCollection, type AlertFilters, type AlertStatus, type ExposureRow,
  type Summary } from "../api";
import { Skeleton, StatusBadge } from "../components";
import { distanceM, fmtDate } from "../format";
import { useI18n } from "../i18n";
import KinaraMap, { DEFAULT_VISIBLE } from "../KinaraMap";
import { go, href } from "../router";

type Sort = "newest" | "largest" | "nearest";

function nextPassHint(summary: Summary | null): string {
  const last = summary?.last_run?.orbits;
  const days = Object.values(last ?? {}).map((o) => o.newest_pass).filter(Boolean) as string[];
  if (!days.length) return "–";
  const d = new Date(days.sort().slice(-1)[0]);
  d.setUTCDate(d.getUTCDate() + 12);
  return fmtDate(d.toISOString());
}

export default function AlertsPage({ summary }: { summary: Summary | null }) {
  const { t, place } = useI18n();
  const [filters, setFilters] = useState<AlertFilters>({});
  const [data, setData] = useState<AlertCollection | null>(null);
  const [error, setError] = useState(false);
  const [sort, setSort] = useState<Sort>("newest");
  const [pos, setPos] = useState<{ lon: number; lat: number } | null>(null);
  const [showMap, setShowMap] = useState(false);
  const [tehsils, setTehsils] = useState<ExposureRow[]>([]);
  useEffect(() => { api.exposure("tehsil").then(setTehsils).catch(() => setTehsils([])); }, []);
  useEffect(() => {
    setData(null); setError(false);
    api.alerts(filters).then(setData).catch(() => setError(true));
  }, [filters]);
  useEffect(() => {
    if (sort !== "nearest" || pos || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((p) => setPos({ lon: p.coords.longitude, lat: p.coords.latitude }),
      () => setSort("newest"), { enableHighAccuracy: true, timeout: 10_000 });
  }, [sort, pos]);

  const rows = useMemo(() => {
    const f = [...(data?.features ?? [])];
    if (sort === "largest") f.sort((a, b) => b.properties.area_ha - a.properties.area_ha);
    if (sort === "nearest" && pos) {
      const d = (x: typeof f[number]) => x.properties.lon == null ? Infinity
        : distanceM(pos.lon, pos.lat, x.properties.lon, x.properties.lat!);
      f.sort((a, b) => d(a) - d(b));
    }
    return f;
  }, [data, sort, pos]);

  const set = (patch: Partial<AlertFilters>) => setFilters({ ...filters, ...patch });
  const filtered = Object.values(filters).some((v) => v);
  return (
    <div className="alerts-page">
      <section className="list-col">
        <div className="filters" role="search">
          <label>{t("status")}
            <select value={filters.status ?? ""} onChange={(e) => set({ status: e.target.value as AlertStatus | "" })}>
              <option value="">{t("any")}</option>
              {STATUSES.map((s) => <option key={s} value={s}>{t(s)}</option>)}
            </select></label>
          <label>{t("tehsil")}
            <select value={filters.tehsil ?? ""} onChange={(e) => set({ tehsil: e.target.value })}>
              <option value="">{t("any")}</option>
              {tehsils.map((r) => <option key={r.unit_id} value={r.name}>{place(r.name)}</option>)}
            </select></label>
          <label>{t("from")}<input type="date" value={filters.since ?? ""} onChange={(e) => set({ since: e.target.value })} /></label>
          <label>{t("minHa")}<input type="number" min={0} step={0.5} inputMode="decimal" value={filters.min_ha ?? ""}
            onChange={(e) => set({ min_ha: e.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={!!filters.flooded}
            onChange={(e) => set({ flooded: e.target.checked })} /> {t("floodedOnly")}</label>
          <label>&nbsp;
            <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="newest">{t("sortNewest")}</option>
              <option value="largest">{t("sortLargest")}</option>
              {"geolocation" in navigator && <option value="nearest">{t("sortNearest")}</option>}
            </select></label>
        </div>
        <div className="list-head">
          <span aria-live="polite">{data ? `${rows.length} ${t("alertsShown")}` : ""}</span>
          <button type="button" className="mobile-only btn" onClick={() => setShowMap(!showMap)}>
            {showMap ? t("alerts") : t("map")}</button>
        </div>
        {error && <p className="error">{t("apiDown")}</p>}
        {!data && !error && <Skeleton h={300} />}
        {data && rows.length === 0 && <p className="muted">{filtered ? t("noAlertsFiltered") : `${t("noAlerts")} ${nextPassHint(summary)}.`}</p>}
        {!showMap && (
          <ul className="alert-list">
            {rows.map((f) => {
              const p = f.properties;
              return (
                <li key={p.alert_id}>
                  <a href={href(`alerts/${p.alert_id}`)} className="alert-row">
                    <StatusBadge status={p.status} />
                    <span><b>{p.alert_id}</b> · {p.area_ha} ha ({p.area_kanal ?? "–"} kanal)
                      {p.flooded_2025 && <span className="chip">{t("flooded2025")}</span>}
                      <span className="muted block">{place(p.mouza, p.mouza_ur) || t("notAvailable")} · {place(p.tehsil)} · {fmtDate(p.first_detected)}
                        {sort === "nearest" && pos && p.lon != null && ` · ${(distanceM(pos.lon, pos.lat, p.lon, p.lat!) / 1000).toFixed(1)} km`}
                      </span></span>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section className={`map-col ${showMap ? "show" : ""}`}>
        <KinaraMap summary={summary} alerts={data} visible={{ ...DEFAULT_VISIBLE, cells: false, flood: false }}
          onAlert={(id) => go(`alerts/${id}`)} className="full" />
      </section>
    </div>
  );
}
