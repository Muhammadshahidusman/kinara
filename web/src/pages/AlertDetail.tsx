// UIUX.md 4.4 evidence card and 4.5 verify (mobile first: three 56 px buttons, GPS "visited", keep input on error).
import { useEffect, useRef, useState } from "react";
import { api, ApiError, openFile, type AlertFeature, type AlertStatus, type Chip, type User } from "../api";
import { AuthImage, Skeleton, Sparkline, StatusBadge } from "../components";
import { distanceM, fmtDate, fmtPkt, googleMapsUrl } from "../format";
import { useI18n } from "../i18n";
import { href } from "../router";

const VISITED_RADIUS_M = 300;     // settings api.visited_radius_m

function ChipView({ id, side, chip }: { id: string; side: "before" | "after"; chip?: Chip }) {
  const { t } = useI18n();
  if (!chip?.available) {
    return <div className="chip-empty">{t("noImage")}{chip?.reason ? `: ${chip.reason}` : ""}</div>;
  }
  return <AuthImage path={`/api/alerts/${id}/image/${side}.png`} alt={`${t(side)} ${fmtDate(chip.date)}`} className="chip-img" />;
}

/** Before/after swipe: the after image is clipped by a slider over the before image. */
function Swipe({ a }: { a: AlertFeature }) {
  const { t } = useI18n();
  const p = a.properties;
  const [pct, setPct] = useState(50);
  const both = p.s2_before?.available && p.s2_after?.available;
  return (
    <div>
      <div className="swipe-head">
        <span><b>{t("before").toUpperCase()}</b> {fmtDate(p.s2_before?.date)}{p.s2_before?.cloud_pct != null && ` · ${p.s2_before.cloud_pct}% cloud`}</span>
        <span><b>{t("after").toUpperCase()}</b> {fmtDate(p.s2_after?.date)}{p.s2_after?.cloud_pct != null && ` · ${p.s2_after.cloud_pct}% cloud`}</span>
      </div>
      {both ? (
        <div className="swipe">
          <ChipView id={p.alert_id} side="before" chip={p.s2_before} />
          <div className="swipe-after" style={{ clipPath: `inset(0 0 0 ${pct}%)` }}>
            <ChipView id={p.alert_id} side="after" chip={p.s2_after} />
          </div>
          <div className="swipe-line" style={{ left: `${pct}%` }} />
          <input type="range" min={0} max={100} value={pct} onChange={(e) => setPct(Number(e.target.value))}
            aria-label={`${t("before")} / ${t("after")}`} className="swipe-range" />
        </div>
      ) : (
        <div className="chips-side">
          <ChipView id={p.alert_id} side="before" chip={p.s2_before} />
          <ChipView id={p.alert_id} side="after" chip={p.s2_after} />
        </div>
      )}
    </div>
  );
}

function Verify({ a, onDone }: { a: AlertFeature; onDone: () => void }) {
  const { t } = useI18n();
  const p = a.properties;
  const [note, setNote] = useState("");
  const [pos, setPos] = useState<{ lon: number; lat: number; d: number } | null>(null);
  const [gps, setGps] = useState<"asking" | "off" | "ok">("asking");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [last, setLast] = useState<AlertStatus | null>(null);
  const autoSent = useRef(false);

  useEffect(() => {
    if (!navigator.geolocation || p.lon == null) { setGps("off"); return; }
    navigator.geolocation.getCurrentPosition((g) => {
      const d = distanceM(g.coords.longitude, g.coords.latitude, p.lon!, p.lat!);
      setPos({ lon: g.coords.longitude, lat: g.coords.latitude, d });
      setGps("ok");
      if (d <= VISITED_RADIUS_M && p.status === "new" && !autoSent.current) {
        autoSent.current = true;
        api.verify(p.alert_id, { status: "visited", lon: g.coords.longitude, lat: g.coords.latitude })
          .then(onDone).catch(() => { autoSent.current = false; });
      }
    }, () => setGps("off"), { enableHighAccuracy: true, timeout: 15_000 });
  }, [p.alert_id]);   // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (status: AlertStatus) => {
    setBusy(true); setMsg(null); setLast(status);
    try {
      await api.verify(p.alert_id, { status, note, ...(pos ? { lon: pos.lon, lat: pos.lat } : {}) });
      setMsg({ ok: true, text: t("saved") });
      setNote("");
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError && e.status === 403 ? e.message : t("submitFailed") });
    } finally { setBusy(false); }
  };
  return (
    <section className="verify" id="verify" aria-label={t("verify")}>
      <h2>{t("verify")}</h2>
      <p className="muted">{gps === "ok" && pos ? (pos.d <= VISITED_RADIUS_M ? `${t("gpsVisited")} ${Math.round(pos.d)} m`
        : `${t("gpsFar")} ${(pos.d / 1000).toFixed(1)} km ${t("gpsFromAlert")}`) : gps === "off" ? t("gpsOff") : t("loading")}</p>
      <div className="verdicts">
        <button type="button" className="verdict confirmed" disabled={busy} onClick={() => send("confirmed")}>{t("confirmed")}</button>
        <button type="button" className="verdict false_alarm" disabled={busy} onClick={() => send("false_alarm")}>{t("false_alarm")}</button>
        <button type="button" className="verdict no_access" disabled={busy} onClick={() => send("no_access")}>{t("no_access")}</button>
      </div>
      <label className="block">{t("note")}
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} />
      </label>
      {msg && <div className={msg.ok ? "toast" : "error"} role={msg.ok ? "status" : "alert"}>{msg.text}
        {!msg.ok && last && <button type="button" className="btn" onClick={() => send(last)}>{t("retry")}</button>}</div>}
    </section>
  );
}

export default function AlertDetail({ id, user }: { id: string; user: User }) {
  const { t, place } = useI18n();
  const [a, setA] = useState<AlertFeature | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.alert(id).then(setA).catch((e) => setError(e instanceof ApiError && e.status === 404 ? `No alert ${id}` : t("apiDown")));
  useEffect(() => { load(); }, [id]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <div className="page"><p className="error">{error}</p><a href={href("alerts")}>← {t("alerts")}</a></div>;
  if (!a) return <div className="page"><Skeleton h={400} /></div>;
  const p = a.properties;
  const na = t("notAvailable");
  const scenes: string[] = (() => { try { return JSON.parse(p.scenes_after ?? "[]"); } catch { return []; } })();
  const canVerify = user.role !== "viewer";
  return (
    <div className="page evidence">
      <a href={href("alerts")} className="back">← {t("alerts")}</a>
      <header className="ev-head">
        <h1>{p.alert_id} · {t("candidate")}</h1>
        <div className="ev-actions">
          {canVerify && <a className="btn primary" href="#verify">{t("verify")}</a>}
          <button type="button" className="btn" onClick={() => openFile(`/api/alerts/${p.alert_id}/evidence.pdf`)}>{t("pdf")}</button>
          {p.lat != null && <a className="btn" href={googleMapsUrl(p.lat, p.lon!)} target="_blank" rel="noopener noreferrer">{t("openGoogleMaps")}</a>}
        </div>
      </header>
      <Swipe a={a} />
      <dl className="facts grid2">
        <dt>{t("area")}</dt><dd>{p.area_ha} ha (about {p.area_kanal ?? "–"} kanal)</dd>
        <dt>{t("firstDetected")}</dt><dd>{fmtDate(p.first_detected)}</dd>
        <dt>{t("mouza")} / {t("tehsil")}</dt><dd>{place(p.mouza, p.mouza_ur) || na} / {place(p.tehsil) || na}</dd>
        <dt>{t("distRiver")}</dt><dd>{p.distance_river_m != null ? `${p.distance_river_m} m` : na}</dd>
        <dt>{t("flooded2025")}</dt><dd>{p.flooded_2025 == null ? na : p.flooded_2025 ? `${t("yes")} (${Math.round((p.flooded_share ?? 0) * 100)}%)` : t("no")}</dd>
        <dt>{t("status")}</dt><dd><StatusBadge status={p.status} /></dd>
        <dt>{t("radarChange")}</dt><dd>{p.rise_db != null ? `+${p.rise_db.toFixed(1)} dB, 2 ${t("passes")}` : na} · {t("orbit")} {p.orbit ?? na}</dd>
        <dt>{t("lastSeen")}</dt><dd>{fmtDate(p.last_seen)}{p.n_detections && p.n_detections > 1 ? ` (${p.n_detections}×)` : ""}</dd>
      </dl>
      {p.sparkline && <Sparkline points={p.sparkline} />}
      <p className="muted small scenes">{t("scenes")}: {scenes.join(", ") || na}</p>
      <p className="caveat">⚠ {t("caveat")}</p>
      {canVerify && <Verify a={a} onDone={load} />}
      <section>
        <h2>{t("history")}</h2>
        <ul className="history">
          <li>{fmtDate(p.first_detected)}: {t("createdBySystem")}</li>
          {(p.history ?? []).map((h, i) => (
            <li key={i}>{fmtPkt(h.at)} PKT: <StatusBadge status={h.status} /> {h.user}
              {h.distance_m != null && <span className="muted"> ({h.distance_m} m)</span>}{h.note && <> · “{h.note}”</>}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
