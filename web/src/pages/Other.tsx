// Exposure (4.6), Reports (4.7), Admin (4.8), Profile (mobile tab) and Login.
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, login, openFile, type ExposureRow, type Precision, type Role, type Run, type Summary,
  type User } from "../api";
import { Bars, Skeleton } from "../components";
import { fmtDate, fmtN, fmtPkt } from "../format";
import { useI18n } from "../i18n";
import { go } from "../router";
import { SortableUnits } from "./Overview";

const today = () => new Date().toISOString().slice(0, 10).replace(/-/g, "");

export function ExposurePage() {
  const { t, place } = useI18n();
  const [kind, setKind] = useState<"tehsil" | "mouza">("tehsil");
  const [rows, setRows] = useState<ExposureRow[] | null>(null);
  useEffect(() => { setRows(null); api.exposure(kind).then(setRows).catch(() => setRows([])); }, [kind]);
  const top = (rows ?? []).filter((r) => r.unit_type === "mouza").sort((a, b) => b.bld_n - a.bld_n).slice(0, 20);
  return (
    <div className="page">
      <h1>{t("exposureTitle")}</h1>
      <div className="tabs" role="tablist">
        {(["tehsil", "mouza"] as const).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={kind === k} className={kind === k ? "on" : ""}
            onClick={() => setKind(k)}>{k === "tehsil" ? t("tehsils") : t("mouzas")}</button>))}
        <button type="button" className="btn" onClick={() => openFile("/api/export/exposure.zip", `kinara_exposure_${today()}.zip`)}>{t("exportCsv")}</button>
      </div>
      {rows == null ? <Skeleton h={300} /> : rows.length === 0 ? <p className="muted">{t("notAvailable")}</p> : (
        <>
          {kind === "mouza" && top.length > 0 && (
            <section><h2>{t("top20")}</h2>
              <Bars rows={top.map((r) => ({ label: place(r.name, r.name_ur), value: r.bld_n, sub: place(r.tehsil) }))} />
            </section>
          )}
          <SortableUnits rows={rows} showTehsil={kind === "mouza"}
            onPick={(r) => go(`map?${kind}=${encodeURIComponent(kind === "mouza" ? r.unit_id : r.name)}`)} />
          {rows[0]?.pop_source && <p className="muted small">{t("population")}: {rows[0].pop_source}</p>}
        </>
      )}
    </div>
  );
}

export function ReportsPage() {
  const { t } = useI18n();
  const [prec, setPrec] = useState<Precision | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api.precision().then(setPrec).catch(() => setPrec(null)); }, []);
  const dl = async (key: string, path: string, name?: string) => {
    setBusy(key); setErr(false);
    try { await openFile(path, name); } catch { setErr(true); } finally { setBusy(null); }
  };
  return (
    <div className="page">
      <h1>{t("reports")}</h1>
      {err && <p className="error">{t("apiDown")}</p>}
      <div className="cards">
        <div className="card"><h2>{t("premonsoon")}</h2><p className="muted">{t("premonsoonDesc")}</p>
          <button type="button" className="btn primary" disabled={busy === "pm"} onClick={() => dl("pm", "/api/report/pre-monsoon.pdf")}>{busy === "pm" ? t("loading") : t("download")}</button></div>
        <div className="card"><h2>{t("exposureExport")}</h2>
          <button type="button" className="btn" disabled={busy === "ex"} onClick={() => dl("ex", "/api/export/exposure.zip", `kinara_exposure_${today()}.zip`)}>{t("download")}</button></div>
        <div className="card"><h2>{t("alertsExport")}</h2>
          <button type="button" className="btn" disabled={busy === "al"} onClick={() => dl("al", "/api/export/alerts.zip", `kinara_alerts_${today()}.zip`)}>{t("download")}</button></div>
        <div className="card"><h2>{t("precision")}</h2>
          {!prec || !prec.n ? <p>{t("precisionNone")}</p> : (
            <p><b>{Math.round((prec.precision ?? 0) * 100)}%</b> of {prec.n} ({Math.round((prec.ci_low ?? 0) * 100)}–{Math.round((prec.ci_high ?? 0) * 100)}%, 95%)
              <br /><span className={prec.release_ready ? "ok-text" : "warn-text"}>{prec.release_ready ? "✓ MET" : "✗ NOT MET"}</span></p>
          )}
          <p className="muted small">{t("gateRule")}</p></div>
      </div>
    </div>
  );
}

export function AdminPage({ summary }: { summary: Summary | null }) {
  const { t } = useI18n();
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [users, setUsers] = useState<(User & { active: boolean })[]>([]);
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "field_officer" as Role, full_name: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const reload = () => { api.runs().then(setRuns).catch(() => setRuns([])); api.users().then(setUsers).catch(() => setUsers([])); };
  useEffect(() => { reload(); api.settings().then(setSettings).catch(() => setSettings(null)); }, []);
  const add = async (e: FormEvent) => {
    e.preventDefault(); setMsg(null);
    try { await api.addUser(form); setForm({ ...form, username: "", password: "", full_name: "" }); reload(); setMsg(t("saved")); }
    catch (er) { setMsg(er instanceof ApiError ? er.message : t("submitFailed")); }
  };
  const fl = summary?.flood_2025;
  return (
    <div className="page">
      <h1>{t("admin")}</h1>
      <section><h2>{t("runs")}</h2>
        {runs == null ? <Skeleton /> : (
          <div className="table-scroll"><table className="data">
            <thead><tr><th>#</th><th>{t("started")}</th><th>{t("status")}</th><th className="num">{t("newAlerts")}</th>
              <th className="num">{t("repeats")}</th><th className="num">{t("scenes")}</th><th>{t("orbit")}</th></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.run_id}><td>{r.run_id}</td><td>{fmtPkt(r.started_at)}</td>
                <td className={r.ok ? "ok-text" : "warn-text"} title={r.error ?? ""}>{r.ok ? t("ok") : `${t("failed")}: ${r.error ?? ""}`}</td>
                <td className="num">{r.n_alerts}</td><td className="num">{r.n_repeats}</td><td className="num">{Object.keys(r.scenes ?? {}).length}</td>
                <td className="small">{Object.entries(r.orbits ?? {}).map(([o, v]) => `${o}: ${v.skipped ?? `${v.patches ?? 0} patches, ${fmtDate(v.newest_pass)}`}`).join(" · ")}</td></tr>))}
            </tbody></table></div>)}
      </section>
      <section><h2>{t("dataSources")}</h2>
        <ul className="small">
          <li>{summary?.buildings?.source} · exposure built {fmtPkt(summary?.built_utc)}</li>
          <li>Flood 2025: Sentinel-1 orbit {fl?.orbit}, {fl?.scenes_event?.join(", ")} · {fl?.calibrated ? "calibrated" : t("uncalibrated")}</li>
          <li>{t("population")}: {summary?.population?.source ?? t("notAvailable")}</li>
          <li>{t("floodplain")}: {summary?.floodplain?.label} ({summary?.floodplain?.area_km2} {t("km2")})</li>
        </ul>
      </section>
      <section><h2>{t("users")}</h2>
        <table className="data"><thead><tr><th>{t("username")}</th><th>{t("fullName")}</th><th>{t("role")}</th><th>{t("active")}</th></tr></thead>
          <tbody>{users.map((u) => <tr key={u.username}><td>{u.username}</td><td>{u.full_name}</td><td>{u.role}</td><td>{u.active ? "✓" : "–"}</td></tr>)}</tbody></table>
        <form className="inline-form" onSubmit={add}>
          <h3>{t("addUser")}</h3>
          <input placeholder={t("username")} value={form.username} required pattern="[A-Za-z0-9_.\-]+" onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <input placeholder={t("fullName")} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <input placeholder={t("password")} type="password" minLength={8} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            <option value="viewer">viewer</option><option value="field_officer">field_officer</option><option value="admin">admin</option></select>
          <button type="submit" className="btn primary">{t("save")}</button>
          {msg && <span role="status">{msg}</span>}
        </form>
      </section>
      <section><h2>{t("settings")}</h2>
        <pre className="settings">{settings ? JSON.stringify(settings, null, 1) : t("loading")}</pre></section>
    </div>
  );
}

export function ProfilePage({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const { t, lang, setLang } = useI18n();
  return (
    <div className="page narrow">
      <h1>{t("profile")}</h1>
      <p>{t("signedInAs")} <b>{user.full_name || user.username}</b> ({user.role})</p>
      <p>{t("language")}: <button type="button" className={`btn ${lang === "en" ? "primary" : ""}`} onClick={() => setLang("en")}>English</button>{" "}
        <button type="button" className={`btn ${lang === "ur" ? "primary" : ""}`} onClick={() => setLang("ur")}>اردو</button></p>
      <button type="button" className="btn" onClick={onSignOut}>{t("signOut")}</button>
    </div>
  );
}

export function LoginPage({ onLogin }: { onLogin: (u: User) => void }) {
  const { t, lang, setLang } = useI18n();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { onLogin(await login(u, p)); }
    catch (er) { setErr(er instanceof ApiError && er.status === 401 ? t("signInFailed") : t("apiDown")); }
    finally { setBusy(false); }
  };
  return (
    <main className="login">
      <form onSubmit={submit} className="card">
        <h1>{t("appName")} <span className="muted">{t("tagline")}</span></h1>
        <label className="block">{t("username")}<input autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></label>
        <label className="block">{t("password")}<input type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required /></label>
        {err && <p className="error" role="alert">{err}</p>}
        <button type="submit" className="btn primary wide" disabled={busy}>{busy ? t("loading") : t("signIn")}</button>
        <button type="button" className="link" onClick={() => setLang(lang === "en" ? "ur" : "en")}>{lang === "en" ? "اردو" : "English"}</button>
        <p className="muted small">{t("caveat")}</p>
      </form>
    </main>
  );
}
