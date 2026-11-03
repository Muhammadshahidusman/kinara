# Kinara: Product Requirements Document

**Product:** Kinara (کنارا, "riverbank"): Ravi Floodplain Watch
**Version:** 0.1 (draft) · **Date:** 3 November 2026 · **Owner:** Muhammad Shahid Usman
**First user:** PDMA Punjab and Lahore district administration
**Target:** v1 in use before the 2027 monsoon (1 June 2027)

---

## 1. Problem

In late August 2025 the Ravi at Shahdara carried about 220,000 cusecs, the highest flow since the 1988 flood (345,000 cusecs). Water entered Theme Park and Park View City on Multan Road, Shafiqabad, Farrukhabad, Talat Park, Afghan Colony and Mohlanwal, among others. Many of the worst-hit areas were new private housing schemes built on low-lying land between the river and the bunds.

Nobody had a current answer to three planning questions before the water arrived:

1. How many buildings now stand inside the Ravi floodplain in Lahore District, and where?
2. How many of them went up in the last few years, after the last flood plans were drawn?
3. Where is new construction happening right now, so next year's exposure doesn't grow unnoticed?

The data to answer these is open and free (Sentinel-1, Sentinel-2, Google Open Buildings). What's missing is a tool that turns it into numbers and maps officials can act on, refreshed automatically, without a remote sensing specialist in the room.

## 2. Product summary

Kinara is a web tool that:

- maps the Ravi floodplain in Lahore District and every building inside it, coloured by the year it appeared (2016 onward);
- shows which areas flooded in August 2025 and how many buildings were affected;
- watches the floodplain every Sentinel-1 pass and raises **candidate alerts** for new construction or land clearing over 0.5 ha;
- gives each alert an evidence card and a field verification workflow;
- produces a pre-monsoon exposure report per tehsil and mouza.

## 3. Users

| Persona | Role | Main question | Where they use Kinara |
|---|---|---|---|
| **Planning officer, PDMA Punjab** (primary) | Monsoon contingency planning at provincial level | "How much is exposed in Lahore's floodplain, and is it growing?" | Office desktop |
| **DDMA / Deputy Commissioner's office, Lahore** (primary) | District preparedness: evacuation routes, relief camps, resource placement | "Which mouzas need attention first this season?" | Office desktop, meetings (projector) |
| **Assistant Commissioner / field officer** (secondary) | Tehsil-level verification and follow-up | "Is this alert real? What did I see on site?" | Mobile phone, in the field |
| **Kinara operator** (internal) | Runs the pipeline, checks data quality | "Did the last run succeed? Are alerts trustworthy?" | Desktop |

Later users (not in v1): Rescue 1122 (read-only), LDA enforcement, Irrigation Department, RUDA.

## 4. Goals and non-goals

### Goals (v1)

- G1. Give PDMA and the district a defensible count of buildings and estimated population inside the floodplain, by tehsil and mouza.
- G2. Show how much of that exposure appeared after 2016.
- G3. Detect new construction in the floodplain within 48 hours of a Sentinel-1 pass, with precision of at least 80% (lower bound of the 95% interval).
- G4. Close the loop: every alert can be verified in the field and the verdict improves the detector.

### Non-goals

- Deciding whether construction is **legal**. Kinara reports candidate new construction; legality is a matter for LDA records and courts.
- Detecting single houses, extra floors or small extensions. At 10 m resolution the tool sees schemes and plots, not homes.
- Flood **forecasting**. That is the Flood Forecasting Division's job. Kinara describes exposure and past extent.
- Household-level decisions (compensation, eligibility). All numbers are area-level planning estimates.

## 5. Features and priority

**P0 = must have for the pilot. P1 = v1 before monsoon. P2 = later.**

| ID | Feature | Priority | Acceptance criteria |
|---|---|---|---|
| F1 | **Floodplain map** with zones, river, tehsil and mouza boundaries | P0 | Zone loads in under 3 s; definition and date shown in the legend |
| F2 | **Exposure overview**: buildings in floodplain, built since 2016, flooded in 2025, open alerts | P0 | Four headline numbers with method notes; tehsil table sortable |
| F3 | **August 2025 flood layer** (open land + built-up) and flooded-building counts | P0 | Validated against at least 30 geolocated news and drone locations |
| F4 | **New-construction alerts** every Sentinel-1 pass, at least 0.5 ha, persistence of 2 passes | P0 | Precision at least 0.80 (lower CI bound) on at least 300 verified alerts before release |
| F5 | **Alert evidence card**: before/after imagery, area (ha and kanal), mouza, distance to river, flooded-2025 flag, scene IDs | P0 | Every field present or explicitly "not available" |
| F6 | **Verification workflow**: New, Visited, Confirmed, False alarm; note; user; full history | P0 | Works on a 6-inch phone over 4G; history is append-only |
| F7 | **Exports**: PDF evidence sheet per alert, CSV and GeoJSON exposure tables | P0 | PDF fits one A4 page and prints legibly in black and white |
| F8 | **Logins and roles**: viewer, field officer, admin | P1 | Field officers can verify; viewers can't change anything |
| F9 | **Population estimate** per tehsil and mouza (WorldPop or GHSL) | P1 | Source and year printed next to every figure |
| F10 | **Pre-monsoon report** (PDF): exposure, growth since 2016, top 20 mouzas, alert summary | P1 | Generated in one click; ready for a DC meeting |
| F11 | **Urdu interface** with right-to-left layout | P1 | Every label translated; place names from the Urdu/Roman lookup |
| F12 | **Event mode**: rapid flood extent during a monsoon flood from each new Sentinel-1 pass | P1 | Map updated within 24 h of the scene appearing in the catalogue |
| F13 | **Building timeline slider** 2016 to 2023 | P1 | Smooth on a mid-range laptop |
| F14 | Weekly digest email | P2 | |
| F15 | Other rivers (Chenab, Sutlej) and districts | P2 | |
| F16 | LDA and Irrigation modules (approved schemes, right-of-way) | P2 | |
| F17 | Offline field mode | P2 | |

## 6. Key user stories

- As a **PDMA planning officer**, I want the number of buildings inside the floodplain per tehsil, so I can put Lahore's figures into the provincial monsoon contingency plan.
- As a **DDMA officer**, I want the 20 mouzas with the most buildings that flooded in 2025, so I can plan evacuation and relief camps.
- As a **DDMA officer**, I want to see new schemes being laid out inside the floodplain this season, so exposure doesn't grow unnoticed before the monsoon.
- As a **field officer**, I want to open an alert on my phone, navigate to it, and mark it confirmed or false alarm with a note, in under 2 minutes.
- As the **Kinara operator**, I want each run's scenes, settings and alert count logged, so I can defend any number in a meeting.

## 7. Success metrics

| Metric | Target |
|---|---|
| Alert precision (verified, lower 95% bound) | at least 0.80 |
| Time from Sentinel-1 acquisition to alert | under 48 h |
| Exposure report delivered to PDMA / DC office | before 1 June 2027 |
| Active pilot users (weekly, during Mar to Jun 2027) | at least 5 |
| Alerts verified within 14 days | at least 60% |
| Map first load on 4G | under 3 s |

## 8. Constraints

- **Open data only**: Sentinel-1, Sentinel-2, Open Buildings, MERIT Hydro, HydroSHEDS, JRC, OpenStreetMap, WorldPop/GHSL. No paid imagery, no data obtained by request.
- **Earth Engine licensing**: free use covers research and prototyping. A tool maintained for government management use needs a commercial licence (Pakistan isn't a UN Least Developed Country). See TRD section 4.
- **Resolution**: 10 m. Minimum alert size 0.5 ha.
- **Budget**: near zero until a department adopts it. Runs on one PC or a small server.

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Too many false alarms | Users stop opening the tool | Persistence rule, 0.5 ha minimum, precision gate before release, verdicts feed recalibration |
| No champion inside PDMA / DC office | Tool unused regardless of quality | Secure 2 or 3 named pilot users in phase 1, before heavy building |
| Earth Engine licence for operational use | Must pay or migrate | Data access behind one module (`kinara.gee`), so a STAC backend (Planetary Computer, Copernicus Data Space) can replace it |
| Floodplain definition disputed | Numbers rejected | Show the definition on every screen; offer bunds-based and HAND-based zones side by side |
| Sentinel-1 gaps during the flood window | Missed peak extent | Report which passes exist (scripts/check_gee.py); combine with cloud-free Sentinel-2 where available |
| Numbers misread as legal findings | Political and legal trouble | Wording rules: "candidate", "estimate"; method notes on every export |

## 10. Release plan

| Phase | Weeks | Dates (approx.) | Output |
|---|---|---|---|
| 1. Signal and user | 1 to 2 | Nov 2026 | Spike results; 2 or 3 named pilot users; this PRD confirmed |
| 2. Data engine | 3 to 6 | Nov to Dec 2026 | Floodplain zone, building cohorts, 2025 flood extent, change detector, precision check |
| 3. Backend | 7 to 10 | Jan 2027 | PostGIS, scheduled runs, API, logins |
| 4. Frontend | 11 to 14 | Feb 2027 | Map, alerts, evidence card, verification, PDF |
| 5. Pilot | 15 to 24 | Mar to May 2027 | Field verification, recalibration, pre-monsoon report |
| v1 | | by 1 Jun 2027 | In use for the 2027 monsoon |

## 11. Open questions

1. Who are the named pilot users at PDMA Punjab and the DC Lahore office?
2. Can we get the official bund alignment, or must we digitise it from OSM and imagery?
3. Which population source will PDMA accept (WorldPop, GHSL, census block counts)?
4. Is an English-only pilot acceptable, with Urdu in v1?
5. Who would fund an Earth Engine commercial licence, or should v1 run on the STAC backend from the start?
6. Where will v1 be hosted once it leaves the development PC?

## Sources

- Dawn, 29 Aug 2025, "1.5m affected as Punjab reels from 'worst flood in decades'": https://www.dawn.com/news/1938038
- Dawn, 29 Aug 2025, "Five Lahore localities flooded by the Ravi": https://www.dawn.com/news/1938079
- Express Tribune, 30 Aug 2025, "New housing societies in Shahdara inundated": https://tribune.com.pk/story/2564010/new-housing-societies-in-shahdara-inundated
- Express Tribune, Aug 2025, "Ravi River at Shahdara swells to highest level since 1988": https://tribune.com.pk/story/2563893/ravi-river-at-shahdara-swells-to-highest-level-since-1988
- Earth Engine for noncommercial and research use: https://earthengine.google.com/noncommercial
