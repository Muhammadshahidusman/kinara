// UIUX.md 4.2: layers panel, timeline slider 2016-2023, click alert -> side drawer.
import { useEffect, useMemo, useState } from "react";
import { api, type AlertCollection, type Summary } from "../api";
import { StatusBadge } from "../components";
import { fmtDate } from "../format";
import { useI18n } from "../i18n";
import KinaraMap, { DEFAULT_VISIBLE, type Focus, type Visible } from "../KinaraMap";
import { href, type Route } from "../router";

const YEARS = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023];

export default function MapPage({ summary, route }: { summary: Summary | null; route: Route }) {
  const { t, place } = useI18n();
  const [alerts, setAlerts] = useState<AlertCollection | null>(null);
  const [vis, setVis] = useState<Visible>(DEFAULT_VISIBLE);
  const [panel, setPanel] = useState(window.innerWidth >= 760);
  const [year, setYear] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => { api.alerts().then(setAlerts).catch(() => setAlerts(null)); }, []);

  const focus = useMemo<Focus | null>(() => {
    const q = route.query;
    if (q.get("tehsil")) return { kind: "tehsil", name: q.get("tehsil")! };
    if (q.get("mouza")) return { kind: "mouza", name: q.get("mouza")! };
    if (q.get("alert")) return { kind: "alert", name: q.get("alert")! };
    return null;
  }, [route.query]);
  useEffect(() => { if (focus?.kind === "mouza") setVis((v) => ({ ...v, mouzas: true })); }, [focus]);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setYear((y) => {
      const next = y == null ? YEARS[0] : y + 1;
      if (next > YEARS[YEARS.length - 1]) { setPlaying(false); return YEARS[YEARS.length - 1]; }
      return next;
    }), 900);
    return () => window.clearInterval(id);
  }, [playing]);

  const sel = alerts?.features.find((f) => f.properties.alert_id === selected)?.properties;
  const toggle = (k: keyof Visible, label: string) => (
    <label className="check"><input type="checkbox" checked={vis[k]} onChange={() => setVis({ ...vis, [k]: !vis[k] })} /> {label}</label>
  );
  return (
    <div className="map-page">
      <KinaraMap summary={summary} alerts={alerts} visible={vis} year={year} focus={focus} onAlert={setSelected}
        className="full" />
      <button type="button" className="panel-toggle" aria-expanded={panel} onClick={() => setPanel(!panel)}>
        {t("layers")}
      </button>
      {panel && (
        <aside className="layers-panel" aria-label={t("layers")}>
          <h3>{t("layers")}</h3>
          {toggle("zone", t("fpZone"))}
          {toggle("flood", t("flood2025"))}
          {toggle("cells", t("bldYear"))}
          {toggle("alerts", t("alerts"))}
          {toggle("tehsils", t("tehsils"))}
          {toggle("mouzas", t("mouzas"))}
          {toggle("river", t("river"))}
          {toggle("satellite", t("satellite"))}
        </aside>
      )}
      {vis.cells && (
        <div className="timeline" aria-label={t("timeline")}>
          <button type="button" onClick={() => { if (!playing && (year == null || year === 2023)) setYear(2016); setPlaying(!playing); }}>
            {playing ? t("pause") : t("play")}
          </button>
          <input type="range" min={2015} max={2023} step={1} value={year ?? 2023}
            aria-valuetext={year == null ? "all" : String(year)}
            onChange={(e) => { setPlaying(false); const v = Number(e.target.value); setYear(v === 2015 || v === 2023 ? null : v); }} />
          <span className="tl-year">{year ?? "2016-2023"}</span>
        </div>
      )}
      {sel && (
        <aside className="drawer" aria-label={sel.alert_id}>
          <button type="button" className="close" aria-label={t("close")} onClick={() => setSelected(null)}>×</button>
          <h3>{sel.alert_id}</h3>
          <p className="muted">{t("candidate")}</p>
          <StatusBadge status={sel.status} />
          <dl className="facts">
            <dt>{t("area")}</dt><dd>{sel.area_ha} ha ({sel.area_kanal ?? "–"} kanal)</dd>
            <dt>{t("mouza")}</dt><dd>{place(sel.mouza, sel.mouza_ur) || t("notAvailable")}</dd>
            <dt>{t("firstDetected")}</dt><dd>{fmtDate(sel.first_detected)}</dd>
          </dl>
          <a className="btn primary" href={href(`alerts/${sel.alert_id}`)}>{t("openEvidence")}</a>
        </aside>
      )}
    </div>
  );
}
