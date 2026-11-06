// Kinara app shell (UIUX.md 3): nav rail + top bar on desktop, bottom tabs (Alerts, Map, Profile) on phones.
import { useEffect, useState, type FormEvent } from "react";
import { api, DEMO, onApiState, session, type ExposureRow, type Summary, type User } from "./api";
import { Banner } from "./components";
import { fmtDate } from "./format";
import { useI18n } from "./i18n";
import AlertDetail from "./pages/AlertDetail";
import AlertsPage from "./pages/AlertsPage";
import MapPage from "./pages/MapPage";
import { AdminPage, ExposurePage, LoginPage, ProfilePage, ReportsPage } from "./pages/Other";
import Overview from "./pages/Overview";
import { go, href, useRoute } from "./router";

const NAV = [
  { key: "overview", icon: "▣" }, { key: "map", icon: "◫" }, { key: "alerts", icon: "⚑" },
  { key: "exposure", icon: "▤" }, { key: "reports", icon: "⎙" },
] as const;

function Search() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [mouzas, setMouzas] = useState<ExposureRow[]>([]);
  useEffect(() => { api.exposure("mouza").then(setMouzas).catch(() => setMouzas([])); }, []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const s = q.trim();
    if (/^K-\d{4}-\d+$/i.test(s)) { go(`alerts/${s.toUpperCase()}`); return; }
    const m = mouzas.find((r) => r.name.toLowerCase() === s.toLowerCase() || r.name_ur === s)
      ?? mouzas.find((r) => r.name.toLowerCase().includes(s.toLowerCase()));
    if (m) go(`map?mouza=${encodeURIComponent(m.unit_id)}`);
  };
  return (
    <form className="search" role="search" onSubmit={submit}>
      <input list="mouza-names" placeholder={t("search")} aria-label={t("search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <datalist id="mouza-names">{mouzas.map((m) => <option key={m.unit_id} value={m.name} />)}</datalist>
    </form>
  );
}

export default function App() {
  const { t, lang, setLang } = useI18n();
  const route = useRoute();
  const [user, setUser] = useState<User | null>(session.user());
  const [summary, setSummary] = useState<Summary | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => onApiState(({ down: d, unauthorised }) => {
    setDown(d);
    if (unauthorised) setUser(null);
  }), []);
  useEffect(() => { if (user) api.summary().then(setSummary).catch(() => setSummary(null)); }, [user]);

  if (!user) return <LoginPage onLogin={(u) => { setUser(u); if (!route.parts.length) go(u.role === "field_officer" ? "alerts" : "overview"); }} />;

  const signOut = () => { if (DEMO) { go("overview"); return; } session.clear(); setUser(null); go(""); };
  const page = route.parts[0] ?? (user.role === "field_officer" ? "alerts" : "overview");
  let body;
  if (page === "map") body = <MapPage summary={summary} route={route} />;
  else if (page === "alerts" && route.parts[1]) body = <AlertDetail id={route.parts[1]} user={user} />;
  else if (page === "alerts") body = <AlertsPage summary={summary} />;
  else if (page === "exposure") body = <ExposurePage />;
  else if (page === "reports") body = <ReportsPage />;
  else if (page === "admin" && user.role === "admin") body = <AdminPage summary={summary} />;
  else if (page === "profile") body = <ProfilePage user={user} onSignOut={signOut} />;
  else body = <Overview summary={summary} />;

  const nav = [...NAV, ...(user.role === "admin" ? [{ key: "admin", icon: "⚙" } as const] : [])];
  return (
    <div className={`shell ${page === "map" ? "is-map" : ""}`}>
      <header className="topbar">
        <a href={href("overview")} className="brand"><strong>{t("appName")}</strong><span className="muted">{t("tagline")}</span></a>
        <Search />
        <button type="button" className="lang" onClick={() => setLang(lang === "en" ? "ur" : "en")}
          aria-label={t("language")}>{lang === "en" ? "EN | اردو" : "اردو | EN"}</button>
        <a href={href("profile")} className="user desktop-only" title={t("profile")}>{user.full_name || user.username}</a>
      </header>
      <nav className="rail" aria-label="Main">
        {nav.map((n) => (
          <a key={n.key} href={href(n.key)} className={page === n.key ? "on" : ""} aria-current={page === n.key ? "page" : undefined}>
            <span aria-hidden="true">{n.icon}</span>{t(n.key)}</a>
        ))}
      </nav>
      <main className="content">
        {DEMO && (
          <Banner kind="warn">{t("demo")} {summary?.built_utc ? fmtDate(summary.built_utc) : "…"}. {t("demoOff")}{" "}
            <a href="https://github.com/Muhammadshahidusman/kinara" target="_blank" rel="noopener">{t("demoCode")} ↗</a></Banner>)}
        {down && <Banner kind="error">{t("apiDown")}</Banner>}
        {summary && summary.stale && !down && (
          <Banner kind="warn">{summary.last_successful_run
            ? `${t("stale")} ${summary.stale_after_days} ${t("days")} (${fmtDate(summary.last_successful_run)}).`
            : t("noRunYet")}</Banner>)}
        {body}
      </main>
      <nav className="tabs-bottom" aria-label="Main">
        {(["alerts", "map", "profile"] as const).map((k) => (
          <a key={k} href={href(k)} className={page === k ? "on" : ""}>{t(k)}</a>))}
      </nav>
    </div>
  );
}
