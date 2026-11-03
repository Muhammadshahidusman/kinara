// English and Urdu strings (PRD F11). Urdu is a first draft: have a PDMA / DC office colleague review it.
// Wording rules (UIUX.md 6): "candidate", "estimated"; never "illegal", "houses", "danger zone".
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "en" | "ur";

const en = {
  appName: "Kinara", tagline: "Ravi Floodplain Watch",
  overview: "Overview", map: "Map", alerts: "Alerts", exposure: "Exposure", reports: "Reports", admin: "Admin",
  profile: "Profile", signIn: "Sign in", signOut: "Sign out", username: "Username", password: "Password",
  signInFailed: "Wrong username or password.", search: "Search mouza or alert ID",
  district: "Lahore District", floodplain: "Floodplain", dataTo: "Data to", lastRun: "Last detection run",
  bldInFp: "estimated buildings in the floodplain", builtSince: "first seen after 2016",
  floodedAug: "in the Aug 2025 flood extent", openAlerts: "open alerts", newThisWeek: "new this week",
  uncalibrated: "provisional: thresholds not yet calibrated", population: "estimated population",
  tehsils: "Tehsils", mouzas: "Mouzas", latestAlerts: "Latest alerts", allAlerts: "All alerts",
  tehsil: "Tehsil", mouza: "Mouza", buildings: "Buildings", newSince: "After 2016", flooded2025: "Flooded 2025",
  area: "Area", km2: "km²",
  status: "Status", new: "New", visited: "Visited", confirmed: "Confirmed", false_alarm: "False alarm",
  no_access: "Couldn't access", any: "Any", from: "From", minHa: "Min. ha", floodedOnly: "Flooded 2025 only",
  sortNewest: "Newest", sortLargest: "Largest", sortNearest: "Nearest",
  alertsShown: "alerts shown", candidate: "New construction (candidate)",
  noAlerts: "No alerts yet. The next satellite pass is expected around",
  noAlertsFiltered: "No alerts match these filters.",
  before: "Before", after: "After", noImage: "No clear Sentinel-2 image", firstDetected: "First detected",
  lastSeen: "Last seen", distRiver: "Distance to river", radarChange: "Radar change", scenes: "Scenes",
  history: "History", createdBySystem: "created by system", verify: "Verify", pdf: "PDF",
  openGoogleMaps: "Open in Google Maps", caveat: "Candidate from 10 m satellite data. Verify on site before any action.",
  notAvailable: "not available", yes: "Yes", no: "No", passes: "passes", orbit: "Orbit",
  note: "Note (optional)", submit: "Submit", retry: "Retry", saved: "Verdict saved", submitFailed:
    "Could not save. Your note is kept; try again.", gpsVisited: "Marked visited: you are within",
  gpsFar: "GPS: you are", gpsFromAlert: "from the alert", gpsOff: "GPS not shared",
  layers: "Layers", fpZone: "Floodplain zone", flood2025: "Aug 2025 flood", floodOpen: "open land",
  floodBuilt: "built-up (hatched)", bldYear: "Buildings by first year", boundaries: "Boundaries",
  river: "River Ravi", satellite: "Satellite basemap", timeline: "Timeline", play: "Play", pause: "Pause",
  openEvidence: "Open evidence", cohortUnknown: "year unknown",
  cellPopup: "estimated buildings in this cell", firstYear: "Typical first year",
  apiDown: "Kinara can't reach its server. Data shown may be out of date.",
  stale: "The last successful detection run is older than", days: "days",
  noRunYet: "No successful detection run yet.",
  exposureTitle: "Exposure inside the floodplain", exportCsv: "Export CSV", top20: "Top 20 mouzas by estimated buildings",
  premonsoon: "Pre-monsoon report (PDF)", premonsoonDesc: "Headline numbers, map, tehsil table, top 20 mouzas, alert summary, method and caveats.",
  exposureExport: "Exposure table (CSV + README)", alertsExport: "Alerts (GeoJSON + README)", download: "Download",
  precision: "Alert precision (release gate)", precisionNone: "No verified alerts yet.",
  gateRule: "Release needs the lower 95% bound at or above 80% on at least 300 verified alerts.",
  runs: "Runs", users: "Users", settings: "Settings", dataSources: "Data sources", started: "Started",
  ok: "OK", failed: "Failed", newAlerts: "New", repeats: "Repeats", addUser: "Add user", role: "Role",
  fullName: "Full name", active: "Active", save: "Save", language: "Language", signedInAs: "Signed in as",
  definitionNote: "Land within 4 km of the Ravi and under 5 m above the nearest drainage (MERIT Hydro HAND). Not drawn from the 2025 flood.",
  loading: "Loading…", close: "Close", method: "Method",
};
type Dict = typeof en;

const ur: Dict = {
  appName: "کنارا", tagline: "راوی سیلابی میدان کی نگرانی",
  overview: "خلاصہ", map: "نقشہ", alerts: "انتباہات", exposure: "خطرے کی زد", reports: "رپورٹس", admin: "انتظام",
  profile: "پروفائل", signIn: "سائن اِن", signOut: "سائن آؤٹ", username: "صارف نام", password: "پاس ورڈ",
  signInFailed: "صارف نام یا پاس ورڈ غلط ہے۔", search: "موضع یا انتباہ نمبر تلاش کریں",
  district: "ضلع لاہور", floodplain: "سیلابی میدان", dataTo: "ڈیٹا تا", lastRun: "آخری جانچ",
  bldInFp: "سیلابی میدان میں تخمینی عمارتیں", builtSince: "2016 کے بعد پہلی بار نظر آئیں",
  floodedAug: "اگست 2025 کے سیلاب کی حد میں", openAlerts: "کھلے انتباہات", newThisWeek: "اس ہفتے نئے",
  uncalibrated: "عارضی: حدیں ابھی جانچی نہیں گئیں", population: "تخمینی آبادی",
  tehsils: "تحصیلیں", mouzas: "مواضع", latestAlerts: "تازہ انتباہات", allAlerts: "تمام انتباہات",
  tehsil: "تحصیل", mouza: "موضع", buildings: "عمارتیں", newSince: "2016 کے بعد", flooded2025: "سیلاب 2025",
  area: "رقبہ", km2: "مربع کلومیٹر",
  status: "حیثیت", new: "نیا", visited: "موقع دیکھا گیا", confirmed: "تصدیق شدہ", false_alarm: "غلط نشاندہی",
  no_access: "رسائی ممکن نہیں", any: "سب", from: "سے", minHa: "کم از کم ہیکٹر", floodedOnly: "صرف سیلاب 2025",
  sortNewest: "تازہ ترین", sortLargest: "سب سے بڑے", sortNearest: "قریب ترین",
  alertsShown: "انتباہات دکھائے گئے", candidate: "نئی تعمیر (ممکنہ)",
  noAlerts: "ابھی کوئی انتباہ نہیں۔ اگلا سیٹلائٹ گزر متوقع ہے تقریباً",
  noAlertsFiltered: "ان فلٹرز سے کوئی انتباہ نہیں ملا۔",
  before: "پہلے", after: "بعد", noImage: "Sentinel-2 کی صاف تصویر دستیاب نہیں", firstDetected: "پہلی نشاندہی",
  lastSeen: "آخری بار دیکھا گیا", distRiver: "دریا سے فاصلہ", radarChange: "ریڈار تبدیلی", scenes: "سینز",
  history: "تاریخچہ", createdBySystem: "نظام نے بنایا", verify: "تصدیق کریں", pdf: "PDF",
  openGoogleMaps: "گوگل میپس میں کھولیں", caveat: "10 میٹر سیٹلائٹ ڈیٹا سے ممکنہ نشاندہی۔ کسی بھی کارروائی سے پہلے موقع پر تصدیق کریں۔",
  notAvailable: "دستیاب نہیں", yes: "ہاں", no: "نہیں", passes: "گزر", orbit: "مدار",
  note: "نوٹ (اختیاری)", submit: "جمع کریں", retry: "دوبارہ کوشش کریں", saved: "فیصلہ محفوظ ہو گیا",
  submitFailed: "محفوظ نہیں ہو سکا۔ آپ کا نوٹ محفوظ ہے؛ دوبارہ کوشش کریں۔", gpsVisited: "موقع دیکھا گیا درج: آپ فاصلے پر ہیں",
  gpsFar: "GPS: آپ", gpsFromAlert: "انتباہ سے دور ہیں", gpsOff: "GPS شیئر نہیں کیا گیا",
  layers: "پرتیں", fpZone: "سیلابی میدان", flood2025: "سیلاب اگست 2025", floodOpen: "کھلی زمین",
  floodBuilt: "تعمیر شدہ (دھاری دار)", bldYear: "عمارتیں پہلے سال کے لحاظ سے", boundaries: "حدود",
  river: "دریائے راوی", satellite: "سیٹلائٹ نقشہ", timeline: "ٹائم لائن", play: "چلائیں", pause: "روکیں",
  openEvidence: "ثبوت کھولیں", cohortUnknown: "سال نامعلوم",
  cellPopup: "اس خانے میں تخمینی عمارتیں", firstYear: "عام پہلا سال",
  apiDown: "کنارا اپنے سرور تک نہیں پہنچ پا رہا۔ دکھایا گیا ڈیٹا پرانا ہو سکتا ہے۔",
  stale: "آخری کامیاب جانچ اس سے پرانی ہے:", days: "دن",
  noRunYet: "ابھی تک کوئی کامیاب جانچ نہیں ہوئی۔",
  exposureTitle: "سیلابی میدان کے اندر خطرے کی زد", exportCsv: "CSV برآمد کریں", top20: "تخمینی عمارتوں کے لحاظ سے سرِفہرست 20 مواضع",
  premonsoon: "مون سون سے پہلے کی رپورٹ (PDF)", premonsoonDesc: "اہم اعداد، نقشہ، تحصیل جدول، سرِفہرست 20 مواضع، انتباہات کا خلاصہ، طریقہ کار اور احتیاطیں۔",
  exposureExport: "خطرے کی زد کا جدول (CSV + README)", alertsExport: "انتباہات (GeoJSON + README)", download: "ڈاؤن لوڈ",
  precision: "انتباہات کی درستگی (اجراء کی شرط)", precisionNone: "ابھی کوئی تصدیق شدہ انتباہ نہیں۔",
  gateRule: "اجراء کے لیے کم از کم 300 تصدیق شدہ انتباہات پر 95% کی نچلی حد 80% یا زیادہ ہونی چاہیے۔",
  runs: "جانچیں", users: "صارفین", settings: "ترتیبات", dataSources: "ڈیٹا کے ذرائع", started: "آغاز",
  ok: "کامیاب", failed: "ناکام", newAlerts: "نئے", repeats: "دہرائے گئے", addUser: "صارف شامل کریں", role: "کردار",
  fullName: "پورا نام", active: "فعال", save: "محفوظ کریں", language: "زبان", signedInAs: "بطور",
  definitionNote: "دریائے راوی سے 4 کلومیٹر کے اندر اور قریبی نکاسی سے 5 میٹر سے کم بلند زمین (MERIT Hydro HAND)۔ 2025 کے سیلاب سے اخذ نہیں کیا گیا۔",
  loading: "لوڈ ہو رہا ہے…", close: "بند کریں", method: "طریقہ",
};

const DICTS: Record<Lang, Dict> = { en, ur };
// Tehsil names from the official boundary file, with Urdu equivalents.
const TEHSIL_UR: Record<string, string> = {
  "Allama Iqbal": "علامہ اقبال", "Lahore Cantt": "لاہور کینٹ", "Lahore City": "لاہور سٹی",
  "Lahore Model Town": "ماڈل ٹاؤن", "Lahore Raiwand": "رائے ونڈ", "Lahore Shalamar": "شالامار",
  Nishter: "نشتر", Ravi: "راوی", Sadar: "صدر", Wahga: "واہگہ",
};

export type T = (k: keyof Dict) => string;
interface Ctx { lang: Lang; setLang: (l: Lang) => void; t: T; place: (en?: string | null, ur?: string | null) => string }
const I18n = createContext<Ctx>({ lang: "en", setLang: () => {}, t: (k) => en[k], place: (e) => e ?? "" });

function storedLang(): Lang {
  try { return localStorage.getItem("kinara.lang") === "ur" ? "ur" : "en"; } catch { return "en"; }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(storedLang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ur" ? "rtl" : "ltr";
  }, [lang]);
  const setLang = (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("kinara.lang", l); } catch { /* private mode: language just isn't remembered */ }
  };
  const t: T = (k) => DICTS[lang][k];
  const place = (e?: string | null, u?: string | null) =>
    lang === "ur" ? (u || (e ? TEHSIL_UR[e] : "") || e || "") : (e ?? "");
  return <I18n.Provider value={{ lang, setLang, t, place }}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);
