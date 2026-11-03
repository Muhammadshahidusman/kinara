// UIUX.md 4.1: four headline numbers with method notes, sortable tehsil table, latest alerts.
import { useEffect, useState } from "react";
import { api, type AlertCollection, type ExposureRow, type Summary } from "../api";
import { Info, Kpi, Skeleton, StatusBadge } from "../components";
import { fmtDate, fmtN, fmtPct } from "../format";
import { useI18n } from "../i18n";
import { go, href } from "../router";

type Key = "name" | "bld_n" | "bld_post2016_n" | "bld_flooded_2025" | "pop_est";

export function SortableUnits({ rows, onPick, showTehsil }: { rows: ExposureRow[]; onPick?: (r: ExposureRow) => void;
  showTehsil?: boolean }) {
  const { t, place } = useI18n();
  const [key, setKey] = useState<Key>("bld_n");
  const [asc, setAsc] = useState(false);
  const sorted = [...rows].sort((a, b) => {
    const va = key === "name" ? place(a.name, a.name_ur) : (a[key] ?? -1);
    const vb = key === "name" ? place(b.name, b.name_ur) : (b[key] ?? -1);
    return (va < vb ? -1 : va > vb ? 1 : 0) * (asc ? 1 : -1);
  });
  const th = (k: Key, label: string, num = true) => (
    <th className={num ? "num" : ""} aria-sort={key === k ? (asc ? "ascending" : "descending") : "none"}>
      <button type="button" className="th-btn" onClick={() => { if (key === k) setAsc(!asc); else { setKey(k); setAsc(k === "name"); } }}>
        {label}{key === k ? (asc ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  return (
    <div className="table-scroll">
      <table className="data">
        <thead><tr>{th("name", showTehsil ? t("mouza") : t("tehsil"), false)}
          {showTehsil && <th>{t("tehsil")}</th>}{th("bld_n", t("buildings"))}{th("bld_post2016_n", t("newSince"))}
          {th("bld_flooded_2025", t("flooded2025"))}{th("pop_est", t("population"))}</tr></thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.unit_id} className={onPick ? "clickable" : ""} tabIndex={onPick ? 0 : undefined}
              onClick={() => onPick?.(r)} onKeyDown={(e) => { if (e.key === "Enter") onPick?.(r); }}>
              <td>{place(r.name, r.name_ur)}{(r.n_tehsils ?? 1) > 1 && <span title={`crosses ${r.n_tehsils} tehsil boundaries`}> *</span>}</td>
              {showTehsil && <td>{place(r.tehsil)}</td>}
              <td className="num">{fmtN(r.bld_n)}</td>
              <td className="num">{fmtN(r.bld_post2016_n)} <span className="muted">({fmtPct(r.bld_post2016_n, r.bld_n)})</span></td>
              <td className="num">{fmtN(r.bld_flooded_2025)}</td>
              <td className="num">{r.pop_est != null ? fmtN(r.pop_est) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Overview({ summary }: { summary: Summary | null }) {
  const { t, place } = useI18n();
  const [tehsils, setTehsils] = useState<ExposureRow[] | null>(null);
  const [latest, setLatest] = useState<AlertCollection | null>(null);
  useEffect(() => {
    api.exposure("tehsil").then(setTehsils).catch(() => setTehsils([]));
    api.alerts().then(setLatest).catch(() => setLatest(null));
  }, []);
  const b = summary?.buildings;
  const fl = summary?.flood_2025;
  return (
    <div className="page">
      <p className="context">
        {t("district")} · {t("floodplain")}: {summary?.floodplain ? place(summary.floodplain.label) : "–"} ·{" "}
        {t("dataTo")} {fmtDate(summary?.last_successful_run ?? summary?.built_utc)}{" "}
        <Info label={t("method")}>{t("definitionNote")}</Info>
      </p>
      {!summary ? <div className="kpis">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={110} />)}</div> : (
        <div className="kpis">
          <Kpi value={fmtN(b?.n)} label={t("bldInFp")}
            sub={summary.population?.n ? `${t("population")}: ~${fmtN(summary.population.n)}` : undefined}
            info={<>{b?.source}. {t("floodplain")}: {summary.floodplain?.area_km2} {t("km2")}.
              {summary.population?.source ? ` ${t("population")}: ${summary.population.source}.` : ""}</>} />
          <Kpi value={`${fmtN(b?.post2016_n)} (${fmtPct(b?.post2016_n, b?.n)})`} label={t("builtSince")}
            info={<>Open Buildings 2.5D Temporal, 2017-2023. {fmtN(b?.year_unknown_n)} footprints have no year.</>} />
          <Kpi value={fmtN(b?.flooded_2025_n)} label={t("floodedAug")}
            tag={fl && !fl.calibrated ? t("uncalibrated") : undefined}
            info={<>Sentinel-1 orbit {fl?.orbit}, {fl?.scenes_event?.map((s) => fmtDate(`${s.slice(17, 21)}-${s.slice(21, 23)}-${s.slice(23, 25)}`)).join(", ")}.
              Open land {fmtN(fl?.open_ha)} ha, built-up {fmtN(fl?.urban_ha)} ha.</>} />
          <Kpi value={fmtN(summary.alerts.open)} label={t("openAlerts")}
            sub={`${fmtN(summary.alerts.new_this_week)} ${t("newThisWeek")}`}
            info={<>{t("caveat")}</>} />
        </div>
      )}
      <div className="two-col">
        <section>
          <h2>{t("tehsils")}</h2>
          {tehsils == null ? <Skeleton h={300} /> :
            <SortableUnits rows={tehsils} onPick={(r) => go(`map?tehsil=${encodeURIComponent(r.name)}`)} />}
        </section>
        <section>
          <h2>{t("latestAlerts")}</h2>
          {latest == null ? <Skeleton h={200} /> : latest.features.length === 0 ? <p className="muted">{t("noAlertsFiltered")}</p> : (
            <ul className="alert-list">
              {latest.features.slice(0, 5).map((f) => (
                <li key={f.properties.alert_id}>
                  <a href={href(`alerts/${f.properties.alert_id}`)} className="alert-row">
                    <StatusBadge status={f.properties.status} />
                    <span><b>{f.properties.alert_id}</b> · {f.properties.area_ha} ha
                      <span className="muted block">{place(f.properties.mouza, f.properties.mouza_ur) || t("notAvailable")} · {fmtDate(f.properties.first_detected)}</span></span>
                  </a>
                </li>
              ))}
            </ul>
          )}
          <a href={href("alerts")}>{t("allAlerts")} →</a>
        </section>
      </div>
    </div>
  );
}
