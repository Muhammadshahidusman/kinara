# Kinara: UI / UX Specification

**Version:** 0.1 (draft) · **Date:** 3 November 2026 · **Stack:** React 18 + MapLibre GL 4 + Vite

---

## 1. Design principles

1. **Answer first.** Every screen opens with the number or map that answers the user's question. Method notes sit one click away, never in the way.
2. **Evidence over decoration.** An alert is only as good as its before/after imagery. No 3D globes, no gradients, no animations that don't explain something.
3. **Honest uncertainty.** Say "candidate alert", "estimated", "about". Show the floodplain definition and data date on every map. Never present a 10 m detection as a house.
4. **Built for the meeting room and the field.** Desktop screens must read on a projector at the back of a DC's meeting room. The verification screen must work one-handed on a 6-inch phone in sunlight over 4G.
5. **Bilingual from the start.** English and Urdu (P1). Layout supports right-to-left without redesign.

## 2. Users and their screens

| Persona | Primary screens | Device |
|---|---|---|
| PDMA planning officer | Overview, Map, Reports | Desktop |
| DDMA / DC office | Overview, Map, Mouza ranking, Reports | Desktop, projector |
| Field officer | Alerts (mobile), Alert detail, Verify | Phone |
| Kinara operator | Runs, Settings, all of the above | Desktop |

## 3. Information architecture

```
Kinara
├── Overview            headline numbers, tehsil table, latest alerts
├── Map                 layers, timeline, click-to-inspect
├── Alerts              list + filters  ──▶  Alert detail  ──▶  Verify
├── Exposure            tehsil / mouza ranking tables
├── Reports             pre-monsoon PDF, CSV / GeoJSON exports
└── Admin (admin only)  runs, data sources, users, settings
```

Desktop: left navigation rail (icons + labels), top bar with search (mouza or alert ID) and language switch.
Mobile: bottom tab bar with 3 tabs: **Alerts, Map, Profile**. Field officers land on Alerts.

## 4. Screens

### 4.1 Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Kinara  Ravi Floodplain Watch                  [Search mouza / alert]  EN|اردو │
├──────┬───────────────────────────────────────────────────────────────────────┤
│ ▣    │  Lahore District · Floodplain: HAND proxy · Data to 28 Oct 2026  (i)  │
│ Over │ ┌───────────────┐┌───────────────┐┌───────────────┐┌───────────────┐   │
│ view │ │ 48,210        ││ 17,930 (37%)  ││ 9,410         ││ 23            │   │
│ ◫ Map│ │ buildings in  ││ built since   ││ flooded in    ││ open alerts   │   │
│ ⚑    │ │ the floodplain││ 2016          ││ Aug 2025      ││ 6 new this wk │   │
│ Alert│ └───────────────┘└───────────────┘└───────────────┘└───────────────┘   │
│ ▤ Exp│  Tehsils                                   Latest alerts              │
│ ⎙ Rep│  ┌───────────────┬───────┬──────┬───────┐  ┌──────────────────────┐   │
│      │  │ Tehsil        │ Bldgs │ New  │ Flood │  │ ● K-2026-0042  2.1 ha│   │
│      │  │ Ravi          │ 12,400│ 41%  │ 3,100 │  │   Mohlanwal · 26 Oct │   │
│      │  │ Sadar         │ ...   │      │       │  │ ● K-2026-0041 ...    │   │
│      │  └───────────────┴───────┴──────┴───────┘  └──────────────────────┘   │
└──────┴───────────────────────────────────────────────────────────────────────┘
```
(Numbers above are placeholders for layout only.)

- Four KPI cards, each with an (i) popover: definition, source, date, caveat.
- Tehsil table sortable by any column; clicking a row opens the Map zoomed to that tehsil.
- Latest alerts: 5 newest, status dot, link to the full list.

### 4.2 Map

- **Layers panel** (left, collapsible): Floodplain zone · Aug 2025 flood (open / built-up) · Buildings by first year · Alerts · Tehsils · Mouzas · Satellite basemap toggle.
- **Timeline slider** (bottom, P1): 2016 to 2023, plays building growth year by year.
- **Click a building cell** → popup: first-built year, flooded 2025 yes/no, mouza.
- **Click an alert** → side drawer with the alert summary and "Open evidence".
- Legend always visible and states the floodplain definition and data date.

### 4.3 Alerts list

Filters: status (New, Visited, Confirmed, False alarm), tehsil, date range, size (ha), flooded-2025 only. Sort: newest, largest, nearest (mobile, uses GPS).
Each row: status badge, alert ID, area in ha and kanal, mouza, first detected date. Desktop shows map and list side by side; mobile shows the list with a "Map" toggle.

### 4.4 Alert detail (evidence card)

```
┌─ K-2026-0042 · New construction (candidate) ─────────── [Verify] [PDF] ─┐
│  BEFORE  12 Aug 2026            │  AFTER  24 Oct 2026                    │
│  [Sentinel-2 true colour]   ◀ swipe ▶  [Sentinel-2 true colour]          │
├──────────────────────────────────────────────────────────────────────────┤
│ Area          2.1 ha (about 41.5 kanal)    First detected   26 Oct 2026  │
│ Mouza / Tehsil  Mohlanwal / Ravi           Distance to river  640 m       │
│ Flooded Aug 2025  Yes                      Status           New           │
│ Radar change  ▁▁▁▂▂▇▇█  (+5.8 dB, 2 passes)                               │
│ Scenes: S1A_IW_GRDH_..._20261012, ..._20261024                            │
│ ⚠ Candidate from 10 m satellite data. Verify on site before any action.   │
├──────────────────────────────────────────────────────────────────────────┤
│ History: 26 Oct created by system                                         │
└──────────────────────────────────────────────────────────────────────────┘
```
- Before/after swipe uses the clearest Sentinel-2 scene in each window; if clouds block it, say so and show the radar chart larger.
- "Open in Google Maps" button for navigation.

### 4.5 Verify (mobile first)

- Three large buttons (min 56 px tall): **Confirmed**, **False alarm**, **Couldn't access**. "Visited" is set automatically when the form opens within 300 m of the alert (GPS, with permission).
- Optional note (voice-to-text friendly), optional photo (P1).
- Submit works with one thumb; confirmation toast; offline submissions queue (P2).
- Target: open alert to submitted verdict in under 2 minutes.

### 4.6 Exposure

Tables by tehsil and mouza: buildings, built since 2016 (count and %), flooded 2025, population estimate (P1), open alerts. Export CSV. Bar chart of the top 20 mouzas.

### 4.7 Reports

- **Pre-monsoon report** (P1): one click, A4 PDF, English (Urdu P1): headline numbers, map, tehsil table, top 20 mouzas, alert summary, method and caveats page.
- **Evidence sheet**: one alert per A4 page, prints legibly in black and white.
- Data exports: CSV and GeoJSON, each with a README of fields, source and date.

### 4.8 Admin

Runs (date, scenes, alerts created, success), data sources and their dates, users and roles, current settings (read-only view of `config/settings.yaml`).

## 5. Visual design

### Colour tokens

| Token | Hex | Use |
|---|---|---|
| `--ink` | #1A202C | Text |
| `--muted` | #5A6475 | Secondary text |
| `--canvas` | #F4F6F8 | App background |
| `--surface` | #FFFFFF | Panels, cards |
| `--line` | #DDE2E8 | Borders |
| `--river` | #2B6CB0 | Floodplain zone, river, flood (built-up hatched) |
| `--alert` | #C2410C | New alerts |
| `--warn` | #B7791F | Visited |
| `--ok` | #2F855A | Confirmed |
| `--neutral` | #718096 | False alarm, inactive |

- **Building cohorts**: sequential, colour-blind safe, light (old) to dark (new): #FDE68A, #FDBA74, #F97316, #C2410C, #7C2D12 for "2016 or before", 2017-18, 2019-20, 2021-22, 2023+.
- **Flood 2025**: open-land flood solid `--river` at 45% opacity; built-up flood same colour with diagonal hatch, so the two remain distinguishable in black-and-white prints.
- **Never colour alone**: status badges carry text; flood types differ by pattern; alerts use shape plus colour.
- Contrast: all text meets WCAG 2.1 AA (4.5:1).

### Typography

- Latin: Inter (400, 600). Urdu: Noto Nastaliq Urdu, line-height 1.9 (Nastaliq needs extra room).
- Sizes: 13 px secondary, 15 px body, 20 px section titles, 32 px KPI numbers. Projector mode (P1) scales all by 1.25.
- Numbers: Western digits with thousands separators (48,210) in both languages.

### Map cartography

- Basemap: light, low-contrast (OpenFreeMap Positron) so data layers stand out; satellite basemap on demand.
- Draw order: basemap, floodplain fill, flood 2025, building cohorts, boundaries, alerts, labels.
- Scale bar and north arrow on every exported map.

## 6. Language and wording

| Say | Don't say |
|---|---|
| Candidate new construction | Illegal construction |
| Estimated buildings | Houses |
| Flooded in Aug 2025 (satellite) | Damaged |
| Floodplain (HAND proxy) | Danger zone |
| False alarm | Wrong |

- Areas: hectares first, kanal second. Use the revenue kanal (20 marla of 272.25 sq ft = 505.86 m²) by default; the marla size is a setting because LDA schemes use a 225 sq ft marla.
- Dates: 26 Oct 2026. Times in PKT.
- Place names: English from the official boundary attributes, Urdu from `data/reference/place_names_roman.tsv`.

## 7. States

| State | Behaviour |
|---|---|
| Loading | Skeleton cards and a map placeholder; no spinners longer than 1 s without text |
| Empty | "No alerts yet. The next satellite pass is expected around <date>." |
| API down | Banner: "Kinara can't reach its server. Data shown may be out of date." Keep cached data visible |
| Stale data | If the last successful run is over 14 days old, amber banner with the date |
| Error on submit | Keep the user's input; offer Retry |

## 8. Responsive behaviour

| Breakpoint | Layout |
|---|---|
| >= 1280 px | Nav rail + list/panel (360 px) + map |
| 760 to 1279 px | Collapsible nav; panel overlays the map |
| < 760 px | Bottom tabs; full-screen list or map; evidence card scrolls vertically |

## 9. Accessibility

- Keyboard reachable: every control, including map layer toggles and alert list rows.
- Map features have list equivalents (every alert on the map is in the list).
- `aria-live` region announces filter results ("23 alerts shown").
- RTL: use CSS logical properties (`margin-inline-start`), mirror the nav and panels, never mirror the map.

## 10. Implementation status (v0.2, 3 Nov 2026)

Built in `web/` (React 18, MapLibre 4, no other UI libraries):

- Sign-in screen; roles decide what shows (Verify for field officers and admins, Admin for admins). Field officers land on Alerts.
- Shell: nav rail + top bar (search by mouza or alert ID, EN | اردو switch) on desktop; bottom tabs Alerts / Map / Profile under 760 px.
- Overview (4.1): four KPI cards with (i) popovers, sortable tehsil table (row opens the map on that tehsil), latest 5 alerts. The flooded count carries a "provisional" tag until thresholds are calibrated.
- Map (4.2): all listed layers including the satellite toggle, timeline slider with play (2016-2023, from cumulative per-cell counts), building-cell popups, alert drawer, legend with definition and data date, scale bar.
- Alerts (4.3): every filter and sort (nearest uses GPS), list and map side by side, mobile list/map toggle, `aria-live` count, empty state with the next expected pass.
- Alert detail (4.4): before/after swipe, all fields with "not available" fallbacks, radar sparkline, scenes, caveat, history, PDF, Google Maps.
- Verify (4.5): three 56 px buttons, automatic "Visited" within 300 m (GPS), note, toast, input kept and Retry on error. Photo upload (P1) and offline queue (P2) are not built.
- Exposure (4.6), Reports (4.7), Admin (4.8) as specified; settings shown read-only.
- States (7): skeletons, empty, API-down banner with cached data, stale-data banner, submit errors.
- Urdu (F11): every interface label has a first-draft translation, RTL via logical CSS properties, Noto Nastaliq Urdu, mouza and tehsil names in Urdu. **Have a native speaker in the pilot office review the wording.**

Not built yet: projector mode (1.25× scale), photo on verify, offline queue, weekly digest.
