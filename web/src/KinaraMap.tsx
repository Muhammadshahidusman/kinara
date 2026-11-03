// MapLibre map with the Kinara layers in UIUX.md draw order: basemap, floodplain, flood 2025, building
// cohorts, boundaries, river, alerts, labels. Legend states the floodplain definition and data date.
import { useEffect, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import { api, authHeaders, type AlertCollection, type Summary } from "./api";
import { fmtN } from "./format";
import { useI18n } from "./i18n";

export const LAHORE: [number, number] = [74.3, 31.55];
const BASEMAP = "https://tiles.openfreemap.org/styles/positron";      // free, no key
// EOX Sentinel-2 cloudless 2023, CC BY-NC-SA 4.0 (non-commercial; see TRD.md section 4)
const SATELLITE = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg";
export const COHORT_COLOURS = ["#FDE68A", "#FDBA74", "#F97316", "#C2410C", "#7C2D12"];
export const COHORT_LABELS = ["2016 or before", "2017-18", "2019-20", "2021-22", "2023+"];
const STATUS_COLOURS: Record<string, string> = { new: "#C2410C", visited: "#B7791F", confirmed: "#2F855A",
  false_alarm: "#718096", no_access: "#718096" };
const STATUS_COLOUR_EXPR = ["match", ["get", "status"], ...Object.entries(STATUS_COLOURS).flat(), "#C2410C"] as
  unknown as maplibregl.ExpressionSpecification;

export interface Visible { zone: boolean; flood: boolean; cells: boolean; tehsils: boolean; mouzas: boolean;
  river: boolean; alerts: boolean; satellite: boolean }
export const DEFAULT_VISIBLE: Visible = { zone: true, flood: true, cells: true, tehsils: true, mouzas: false,
  river: true, alerts: true, satellite: false };

export interface Focus { kind: "tehsil" | "mouza" | "alert"; name: string }

interface Props {
  summary: Summary | null;
  alerts: AlertCollection | null;
  visible?: Visible;
  year?: number | null;
  focus?: Focus | null;
  onAlert?: (id: string) => void;
  className?: string;
}

const LAYER_IDS: Record<keyof Visible, string[]> = {
  satellite: ["satellite"], zone: ["zone-fill", "zone-line"], flood: ["flood"], cells: ["cells"],
  tehsils: ["tehsils"], mouzas: ["mouzas", "mouza-labels"], river: ["river"], alerts: ["alert-poly", "alert-pt"],
};

function bboxOf(geom: GeoJSON.Geometry): [number, number, number, number] {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as number[];
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    } else if (Array.isArray(c)) c.forEach(walk);
  };
  walk((geom as { coordinates?: unknown }).coordinates);
  return [x0, y0, x1, y1];
}

export default function KinaraMap({ summary, alerts, visible = DEFAULT_VISIBLE, year = null, focus, onAlert,
  className }: Props) {
  const { t, place } = useI18n();
  const div = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const layers = useRef<Record<string, GeoJSON.FeatureCollection>>({});
  const [ready, setReady] = useState(false);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  useEffect(() => {
    if (!div.current) return;
    const m = new maplibregl.Map({
      container: div.current, style: BASEMAP, center: LAHORE, zoom: 10.3, attributionControl: { compact: true },
      transformRequest: (url) => (url.includes("/api/") ? { url, headers: authHeaders() } : { url }),
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    m.on("load", async () => {
      const firstSymbol = m.getStyle().layers.find((l) => l.type === "symbol")?.id;
      const add = (spec: maplibregl.LayerSpecification) => m.addLayer(spec, firstSymbol);
      m.addSource("satellite", { type: "raster", tiles: [SATELLITE], tileSize: 256,
        attribution: "Sentinel-2 cloudless 2023 by EOX (CC BY-NC-SA 4.0)" });
      add({ id: "satellite", type: "raster", source: "satellite", layout: { visibility: "none" } });
      const names = ["zones", "cells", "tehsils", "mouzas", "river"] as const;
      const got = await Promise.all(names.map((n) => api.layer(n).catch(() => ({ type: "FeatureCollection",
        features: [] }) as GeoJSON.FeatureCollection)));
      names.forEach((n, i) => { layers.current[n] = got[i]; m.addSource(n, { type: "geojson", data: got[i] }); });
      add({ id: "zone-fill", type: "fill", source: "zones", paint: { "fill-color": "#2B6CB0", "fill-opacity": 0.1 } });
      add({ id: "zone-line", type: "line", source: "zones", paint: { "line-color": "#2B6CB0", "line-width": 1.2 } });
      add({ id: "cells", type: "fill", source: "cells", paint: {
        "fill-color": ["match", ["get", "cohort"], 0, COHORT_COLOURS[0], 1, COHORT_COLOURS[1], 2, COHORT_COLOURS[2],
          3, COHORT_COLOURS[3], 4, COHORT_COLOURS[4], "#CBD5E0"],
        "fill-opacity": ["interpolate", ["linear"], ["get", "n"], 1, 0.45, 40, 0.85],
        "fill-outline-color": "rgba(255,255,255,0.6)" } });
      add({ id: "tehsils", type: "line", source: "tehsils",
        paint: { "line-color": "#1A202C", "line-width": 1, "line-dasharray": [3, 2] } });
      add({ id: "mouzas", type: "line", source: "mouzas", layout: { visibility: "none" },
        paint: { "line-color": "#5A6475", "line-width": 0.6 } });
      add({ id: "river", type: "line", source: "river", paint: { "line-color": "#2B6CB0", "line-width": 2.5 } });
      m.addSource("alerts", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addSource("alert-pts", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      add({ id: "alert-poly", type: "line", source: "alerts", minzoom: 13,
        paint: { "line-color": STATUS_COLOUR_EXPR,
          "line-width": 2 } });
      m.addLayer({ id: "alert-pt", type: "circle", source: "alert-pts", paint: {
        "circle-radius": ["match", ["get", "status"], "new", 7, "visited", 7, 5],
        "circle-color": STATUS_COLOUR_EXPR,
        "circle-stroke-color": "#fff", "circle-stroke-width": ["match", ["get", "status"], "new", 2.5, 1.5] } });
      m.addLayer({ id: "mouza-labels", type: "symbol", source: "mouzas", minzoom: 12, layout: { visibility: "none",
        "text-field": ["get", "name"], "text-size": 11 }, paint: { "text-color": "#5A6475",
        "text-halo-color": "#fff", "text-halo-width": 1.2 } });

      m.on("click", "alert-pt", (e) => {
        const id = e.features?.[0]?.properties?.alert_id;
        if (id) onAlertRef.current?.(String(id));
      });
      m.on("click", "cells", (e) => {
        if (m.queryRenderedFeatures(e.point, { layers: ["alert-pt"] }).length) return;
        const p = e.features?.[0]?.properties;
        if (!p) return;
        const cohort = Number(p.cohort);
        new maplibregl.Popup({ closeButton: true }).setLngLat(e.lngLat).setHTML(
          `<b>${fmtN(Number(p.n))}</b> ${t("cellPopup")}<br/>${t("firstYear")}: ` +
          `${cohort >= 0 ? COHORT_LABELS[cohort] : t("cohortUnknown")}<br/>${t("flooded2025")}: ` +
          `${fmtN(Number(p.n_flooded))}${p.mouza ? `<br/>${t("mouza")}: ${String(p.mouza)}` : ""}`).addTo(m);
      });
      for (const id of ["alert-pt", "cells"]) {
        m.on("mouseenter", id, () => { m.getCanvas().style.cursor = "pointer"; });
        m.on("mouseleave", id, () => { m.getCanvas().style.cursor = ""; });
      }
      setReady(true);
    });
    return () => { m.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // flood overlay (needs the summary for its corner coordinates)
  useEffect(() => {
    const m = map.current;
    const ov = summary?.flood_2025?.overlay;
    if (!ready || !m || !ov || m.getSource("flood")) return;
    m.addSource("flood", { type: "image", url: ov.url, coordinates: ov.coordinates as
      [[number, number], [number, number], [number, number], [number, number]] });
    m.addLayer({ id: "flood", type: "raster", source: "flood", paint: { "raster-opacity": 1,
      "raster-resampling": "nearest" } }, "cells");
  }, [ready, summary]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !alerts) return;
    (m.getSource("alerts") as GeoJSONSource).setData(alerts as GeoJSON.FeatureCollection);
    (m.getSource("alert-pts") as GeoJSONSource).setData({ type: "FeatureCollection", features: alerts.features
      .filter((f) => f.properties.lon != null)
      .map((f) => ({ type: "Feature", geometry: { type: "Point", coordinates: [f.properties.lon!, f.properties.lat!] },
        properties: { alert_id: f.properties.alert_id, status: f.properties.status } })) });
  }, [ready, alerts]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    (Object.keys(LAYER_IDS) as (keyof Visible)[]).forEach((k) => LAYER_IDS[k].forEach((id) => {
      if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", visible[k] ? "visible" : "none");
    }));
  }, [ready, visible, summary]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    m.setFilter("cells", year == null ? null : [">", ["get", `c${year}`], 0]);
  }, [ready, year]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !focus) return;
    let geom: GeoJSON.Geometry | undefined;
    if (focus.kind === "alert") geom = alerts?.features.find((f) => f.properties.alert_id === focus.name)?.geometry;
    else {
      const fc = layers.current[focus.kind === "tehsil" ? "tehsils" : "mouzas"];
      geom = fc?.features.find((f) => {
        const p = f.properties ?? {};
        return p.name === focus.name || p.unit_id === focus.name;
      })?.geometry;
    }
    if (geom) m.fitBounds(bboxOf(geom), { padding: 60, maxZoom: focus.kind === "alert" ? 16 : 14, duration: 600 });
  }, [ready, focus, alerts]);

  const fp = summary?.floodplain;
  return (
    <div className={`map-wrap ${className ?? ""}`}>
      <div ref={div} className="map" aria-label={t("map")} role="region" />
      <div className="legend" aria-label="Legend">
        <div><span className="sw zone" />{t("floodplain")}: {fp ? place(fp.label) : t("notAvailable")}</div>
        {visible.flood && <div><span className="sw flood" />{t("flood2025")} ({t("floodOpen")})<br />
          <span className="sw flood-h" />{t("floodBuilt")}{summary?.flood_2025 && !summary.flood_2025.calibrated &&
            <span className="tag-warn small"> {t("uncalibrated")}</span>}</div>}
        {visible.cells && <div className="cohorts">{COHORT_LABELS.map((l, i) => (
          <span key={l}><span className="sw" style={{ background: COHORT_COLOURS[i] }} />{l}</span>))}</div>}
        <div className="muted small">{t("dataTo")}: {summary?.last_successful_run?.slice(0, 10) ?? "–"} ·
          Open Buildings {summary?.data_dates?.buildings ?? ""}</div>
      </div>
    </div>
  );
}
