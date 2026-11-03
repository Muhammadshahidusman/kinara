"""PDF outputs (PRD F7, F10): one-page alert evidence sheet and the pre-monsoon exposure report.

Both are A4 and must print legibly in black and white: greys and black only, patterns not colour,
no information carried by colour alone. Wording follows UIUX.md section 6 ("candidate",
"estimated", never "illegal").
"""

from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import shapely
import shapely.geometry
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Line, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from kinara.geo.utm import utm43n
from kinara.validate.metrics import precision_report

PKT = dt.timezone(dt.timedelta(hours=5))
CAVEAT = ("Candidate from 10 m satellite data. Verify on site before any action. Kinara reports candidate "
          "new construction; it does not judge legality or individual households.")
STATUS_LABEL = {"new": "New", "visited": "Visited", "confirmed": "Confirmed", "false_alarm": "False alarm",
                "no_access": "Couldn't access"}
GREY = colors.Color(0.35, 0.35, 0.35)
LIGHT = colors.Color(0.88, 0.88, 0.88)

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontSize=16, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontSize=9.5, leading=12.5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10, textColor=GREY)
BOX = ParagraphStyle("box", parent=BODY, borderColor=colors.black, borderWidth=0.8, borderPadding=5,
                     spaceBefore=6, spaceAfter=6)


def fmt_date(s: str | None) -> str:
    """'2026-10-26' -> '26 Oct 2026' (UIUX.md); '' -> 'not available'."""
    if not s:
        return "not available"
    try:
        return dt.date.fromisoformat(str(s)[:10]).strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return str(s)


def fmt_n(v: float | int | None) -> str:
    """Thousands separators; None -> 'not available'."""
    return "not available" if v is None else f"{v:,.0f}"


def fmt_pop(v: float | int | None, step: int = 100) -> str:
    """Population estimates rounded to `step` so they don't suggest a head count."""
    return "not available" if v is None else f"{round(v / step) * step:,.0f}"


def scene_date(scene_id: str) -> str:
    """'S1A_IW_GRDH_1SDV_20250828T010809_...' -> '28 Aug 2025'."""
    d = scene_id.split("_")[4][:8] if scene_id.count("_") >= 4 else ""
    return fmt_date(f"{d[:4]}-{d[4:6]}-{d[6:]}") if len(d) == 8 else scene_id


def na(v: object, unit: str = "") -> str:
    """Value with unit, or 'not available' (PRD F5: every field present or explicitly not available)."""
    return "not available" if v is None or v == "" else f"{v}{unit}"


def _table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 2),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style += [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black)]
    t.setStyle(TableStyle(style))
    return t


def _footer(text: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(15 * mm, 9 * mm, text)
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"page {doc.page}")
        canvas.restoreState()
    return draw


def _sparkline(points: list[dict], width: float = 80 * mm, height: float = 28 * mm) -> Drawing | None:
    vals = [(i, p["vv_db"]) for i, p in enumerate(points) if p.get("vv_db") is not None]
    if len(vals) < 2:
        return None
    d = Drawing(width, height)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 28, 14, width - 34, height - 20
    lp.data = [vals]
    lp.lines[0].strokeColor = colors.black
    lp.lines[0].strokeWidth = 1.2
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = 0, len(points) - 1
    lp.xValueAxis.valueSteps = [0, len(points) - 1]
    lp.xValueAxis.labelTextFormat = lambda i: fmt_date(points[int(i)]["day"])
    lp.xValueAxis.labels.fontSize = lp.yValueAxis.labels.fontSize = 6.5
    lp.yValueAxis.labelTextFormat = "%.0f dB"
    d.add(lp)
    return d


def _chip(path: Path, info: dict | None, label: str, width: float) -> list:
    if info and info.get("available") and path.exists():
        cap = f"<b>{label}</b> {fmt_date(info.get('date'))} · Sentinel-2 · cloud {info.get('cloud_pct', '?')}%"
        return [Image(str(path), width=width, height=width), Paragraph(cap, SMALL)]
    reason = (info or {}).get("reason", "image not generated")
    box = Table([[Paragraph(f"<b>{label}</b><br/>No clear Sentinel-2 image.<br/>{reason}", SMALL)]],
                colWidths=[width], rowHeights=[width])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, GREY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [box]


def evidence_pdf(alert: dict, evidence_dir: Path, summary: dict | None) -> bytes:
    """One A4 page per alert: imagery, measurements, radar change, scenes, caveat and history."""
    p = alert["properties"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm,
                            bottomMargin=15 * mm, title=f"Kinara evidence {p['alert_id']}")
    w = (A4[0] - 30 * mm - 6 * mm) / 2
    story: list = [Paragraph(f"{p['alert_id']} · New construction (candidate)", H1),
                   Paragraph("Kinara · Ravi Floodplain Watch · Lahore District", SMALL), Spacer(1, 4)]
    chips = Table([[_chip(evidence_dir / f"{p['alert_id']}_before.png", p.get("s2_before"), "BEFORE", w),
                    _chip(evidence_dir / f"{p['alert_id']}_after.png", p.get("s2_after"), "AFTER", w)]],
                  colWidths=[w + 3 * mm, w + 3 * mm])
    chips.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [chips, Spacer(1, 4)]
    fp = (summary or {}).get("floodplain", {}).get("label", "Floodplain")
    rise = p.get("rise_db")
    flooded = p.get("flooded_2025")
    fields = [
        ["Area", f"{na(p.get('area_ha'), ' ha')} (about {na(p.get('area_kanal'), ' kanal')})",
         "First detected", fmt_date(p.get("first_detected"))],
        ["Mouza / Tehsil", f"{na(p.get('mouza'))} / {na(p.get('tehsil'))}",
         "Last seen", fmt_date(p.get("last_seen"))],
        ["Distance to river", na(p.get("distance_river_m"), " m"), "Status", STATUS_LABEL.get(p.get("status"), "New")],
        ["Flooded Aug 2025", "not available" if flooded is None else ("Yes" if flooded else "No")
         + (f" ({p['flooded_share']:.0%} of area)" if p.get("flooded_share") is not None else ""),
         "Location", f"{p.get('lat')}, {p.get('lon')}"],
        ["Radar change", f"+{rise:.1f} dB on every pass" if rise is not None else "not available",
         "Orbit", na(p.get("orbit"))],
        ["Zone", fp, "Detections", na(p.get("n_detections"))],
    ]
    ft = _table(fields, [30 * mm, 60 * mm, 28 * mm, 62 * mm], header=False)
    ft.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold")]))
    story.append(ft)
    spark = _sparkline(p.get("sparkline") or [])
    if spark:
        story += [Paragraph("Radar backscatter (VV) inside the alert, same orbit", SMALL), spark]
    scenes = p.get("scenes_after")
    if isinstance(scenes, str):
        scenes = json.loads(scenes)
    story.append(Paragraph(f"<b>Sentinel-1 scenes:</b> {', '.join(scenes or []) or 'not available'}<br/>"
                           f"<b>Baseline:</b> {na(p.get('baseline_window'))} "
                           f"({na(p.get('n_baseline_scenes'))} scenes)", SMALL))
    story.append(Paragraph(f"<b>Caution.</b> {CAVEAT}", BOX))
    hist = [["When (PKT)", "Status", "By", "Note"]]
    hist.append([fmt_date(p.get("first_detected")), "Created", "system", ""])
    for h in p.get("history", []):
        hist.append([_pkt(h.get("at")), STATUS_LABEL.get(h.get("status"), h.get("status")), h.get("user", ""),
                     Paragraph(h.get("note") or "", SMALL)])
    story += [Paragraph("History", H2), _table(hist, [32 * mm, 26 * mm, 30 * mm, 92 * mm])]
    doc.build(story, onFirstPage=_footer(f"Generated {dt.datetime.now(PKT):%d %b %Y %H:%M} PKT · open data: "
                                         "Copernicus Sentinel-1/-2, Google Open Buildings"))
    return buf.getvalue()


def _pkt(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(str(iso))
        return t.astimezone(PKT).strftime("%d %b %Y %H:%M").lstrip("0")
    except ValueError:
        return str(iso)


def _rings(geom: dict) -> list[list]:
    """Outer rings of a (Multi)Polygon or the parts of a (Multi)LineString."""
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return list(c)
    if t == "GeometryCollection":
        return [r for g in geom["geometries"] for r in _rings(g)]
    return []


def map_drawing(layers: dict, width: float, height: float) -> Drawing:
    """Black-and-white map: floodplain (grey fill), tehsils (lines), river (thick), alerts (triangles).

    Coordinates are projected to UTM 43N so distances on paper are true; includes a scale bar and a
    north arrow (UIUX.md: every exported map).
    """
    def proj(lon, lat):
        return utm43n(lon, lat)

    feats = [f for k in ("tehsils", "zones") for f in (layers.get(k) or {}).get("features", [])]
    xs, ys = [], []
    for f in feats:
        for ring in _rings(f["geometry"]):
            for lon, lat in ring:
                x, y = proj(lon, lat)
                xs.append(x)
                ys.append(y)
    d = Drawing(width, height)
    if not xs:
        d.add(String(10, height / 2, "Map layers not available", fontSize=10))
        return d
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = min((width - 20) / (x1 - x0), (height - 30) / (y1 - y0))
    lons = [c[0] for f in feats for r in _rings(f["geometry"]) for c in r]
    lats = [c[1] for f in feats for r in _rings(f["geometry"]) for c in r]
    frame = (min(lons), min(lats), max(lons), max(lats))

    def pt(lon, lat):
        x, y = proj(lon, lat)
        return 10 + (x - x0) * s, 25 + (y - y0) * s

    def flat(ring):
        out = []
        for lon, lat in ring:
            out.extend(pt(lon, lat))
        return out

    for f in (layers.get("zones") or {}).get("features", []):
        for ring in _rings(f["geometry"]):
            d.add(Polygon(flat(ring), fillColor=LIGHT, strokeColor=GREY, strokeWidth=0.3))
    for f in (layers.get("tehsils") or {}).get("features", []):
        for ring in _rings(f["geometry"]):
            d.add(PolyLine(flat(ring), strokeColor=colors.black, strokeWidth=0.5, strokeDashArray=[2, 1.5]))
    for f in (layers.get("river") or {}).get("features", []):
        # the river runs past the district: clip it to the map frame so it never crosses the page
        clipped = shapely.clip_by_rect(shapely.geometry.shape(f["geometry"]), *frame)
        if clipped.is_empty:
            continue
        for part in _rings(shapely.geometry.mapping(clipped)):
            if len(part) > 1:
                d.add(PolyLine(flat(part), strokeColor=colors.black, strokeWidth=1.6))
    for f in (layers.get("alerts") or {}).get("features", []):
        p = f["properties"]
        if p.get("lon") is None:
            continue
        cx, cy = pt(p["lon"], p["lat"])
        d.add(Polygon([cx, cy + 3.5, cx - 3, cy - 2, cx + 3, cy - 2], fillColor=colors.black,
                      strokeColor=colors.white, strokeWidth=0.4))
    # scale bar: 5 km
    bar_m = 5000
    d.add(Rect(10, 8, bar_m * s, 3, fillColor=colors.black, strokeColor=None))
    d.add(String(10, 13, "5 km", fontSize=7))
    # north arrow (UTM grid north; differs from true north by under 0.5 degrees here)
    nx, ny = width - 18, height - 28
    d.add(Polygon([nx, ny + 16, nx - 5, ny, nx + 5, ny], fillColor=colors.black, strokeColor=None))
    d.add(String(nx - 3, ny + 19, "N", fontSize=8))
    d.add(Line(10, height - 2, width - 10, height - 2, strokeColor=colors.white))
    return d


def premonsoon_pdf(summary: dict, exposure: list[dict], layers: dict, alerts: dict) -> bytes:
    """Pre-monsoon exposure report for a DC / PDMA meeting (PRD F10)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title="Kinara pre-monsoon exposure report")
    today = dt.datetime.now(PKT)
    b, fp, fl = summary.get("buildings", {}), summary.get("floodplain", {}), summary.get("flood_2025", {})
    pop = summary.get("population", {})
    feats = alerts.get("features", [])
    open_n = sum(1 for f in feats if f["properties"].get("status") in ("new", "visited"))
    calibrated = fl.get("calibrated")
    story: list = [
        Paragraph("Ravi floodplain, Lahore District: pre-monsoon exposure report", H1),
        Paragraph(f"Kinara · Ravi Floodplain Watch · prepared {today:%d %b %Y}".replace(" 0", " "), SMALL),
        Paragraph(f"Floodplain definition: <b>{fp.get('label', 'not available')}</b> "
                  f"({fp.get('area_km2', '?')} km²; land within {fmt_n(fp.get('river_buffer_m'))} m of the Ravi and "
                  f"under {fp.get('hand_max_m', '?')} m above the nearest drainage). Not derived from the 2025 flood.",
                  BODY), Spacer(1, 6)]
    kpi = [["Estimated buildings in the floodplain", fmt_n(b.get("n"))],
           ["First seen after 2016 (2017-2023)", f"{fmt_n(b.get('post2016_n'))}"
            + (f" ({b['post2016_n'] / b['n']:.0%})" if b.get("n") and b.get("post2016_n") is not None else "")],
           ["In the Aug 2025 flood extent (satellite)", fmt_n(b.get("flooded_2025_n"))
            + ("" if calibrated else "  (thresholds not yet calibrated)")],
           ["Estimated population in the floodplain", f"about {fmt_pop(pop.get('n'), 1000)}" if pop.get("n") else
            "not available"],
           ["Open candidate alerts (new + visited)", fmt_n(open_n)]]
    kt = _table(kpi, [110 * mm, 70 * mm], header=False)
    kt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 11), ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [kt, Paragraph(f"Buildings: {b.get('source', '')}. Population: {pop.get('source') or 'not available'}. "
                            f"Flood: Sentinel-1 orbit {fl.get('orbit', '?')}, "
                            f"{', '.join(scene_date(s) for s in fl.get('scenes_event', [])) or 'scene not recorded'}.",
                            SMALL)]
    story += [Paragraph("Map", H2), map_drawing({**layers, "alerts": alerts}, A4[0] - 30 * mm, 120 * mm),
              Paragraph("Grey: floodplain zone. Dashed: tehsil boundaries. Thick line: Ravi. Triangles: candidate "
                        "alerts.", SMALL), PageBreak()]

    teh = sorted([r for r in exposure if r.get("unit_type") == "tehsil"], key=lambda r: -(r.get("bld_n") or 0))
    rows = [["Tehsil (part in floodplain)", "km²", "Buildings", "After 2016", "Flooded 2025", "Population"]]
    rows += [[r["name"], r.get("area_km2"), fmt_n(r.get("bld_n")), fmt_n(r.get("bld_post2016_n")),
              fmt_n(r.get("bld_flooded_2025")), fmt_pop(r.get("pop_est"))] for r in teh]
    story += [Paragraph("Tehsils", H2), _table(rows, [55 * mm, 18 * mm, 27 * mm, 27 * mm, 27 * mm, 26 * mm])]
    mou = sorted([r for r in exposure if r.get("unit_type") == "mouza"], key=lambda r: -(r.get("bld_n") or 0))[:20]
    if mou:
        rows = [["#", "Mouza", "Tehsil", "Buildings", "After 2016", "Flooded 2025", "Population"]]
        rows += [[i, r["name"] + (" *" if (r.get("n_tehsils") or 1) > 1 else ""), r.get("tehsil") or "",
                  fmt_n(r.get("bld_n")), fmt_n(r.get("bld_post2016_n")), fmt_n(r.get("bld_flooded_2025")),
                  fmt_pop(r.get("pop_est"))] for i, r in enumerate(mou, 1)]
        story += [Paragraph("Top 20 mouzas by estimated buildings in the floodplain", H2),
                  _table(rows, [8 * mm, 42 * mm, 30 * mm, 24 * mm, 24 * mm, 26 * mm, 26 * mm])]
        if any((r.get("n_tehsils") or 1) > 1 for r in mou):
            story.append(Paragraph("* The mouza polygon crosses more than one official tehsil boundary (the two "
                                   "boundary layers disagree); its tehsil is the one it overlaps most. Population "
                                   "rounded to the nearest 100.", SMALL))
    else:
        story += [Paragraph("Mouza table not available (mouza boundaries not loaded).", BODY)]

    story.append(PageBreak())
    by_status: dict[str, int] = {}
    by_teh: dict[str, int] = {}
    for f in feats:
        p = f["properties"]
        by_status[p.get("status", "new")] = by_status.get(p.get("status", "new"), 0) + 1
        by_teh[p.get("tehsil") or "not available"] = by_teh.get(p.get("tehsil") or "not available", 0) + 1
    story += [Paragraph("Candidate new-construction alerts", H2),
              Paragraph(f"{len(feats)} alerts in total. " + "; ".join(
                  f"{STATUS_LABEL.get(k, k)}: {v}" for k, v in sorted(by_status.items())) if feats else
                  "No alerts have been raised yet.", BODY)]
    if by_teh:
        story.append(_table([["Tehsil", "Alerts"]] + [[k, v] for k, v in sorted(by_teh.items(), key=lambda x: -x[1])],
                            [80 * mm, 30 * mm]))
    pr = precision_report([f["properties"].get("status") for f in feats])
    story.append(Paragraph(
        "Verified precision: " + ("no verified alerts yet." if not pr["n"] else
                                  f"{pr['precision']:.0%} of {pr['n']} verified alerts confirmed "
                                  f"(95% interval {pr['ci_low']:.0%} to {pr['ci_high']:.0%}). The release gate needs "
                                  f"the lower bound at or above 80% on at least 300 verified alerts."), BODY))
    story += [Paragraph("Method and caveats", H2)] + [Paragraph(t, BODY) for t in (
        "<b>Buildings.</b> Google Open Buildings v3 footprints (confidence at least 0.75) inside the floodplain. "
        "A footprint is a roof seen from space; counts are estimated buildings, not households.",
        "<b>Year first seen.</b> Open Buildings 2.5D Temporal, building presence at least 0.5 per year 2016-2023. "
        "2016 means on or before 2016. About 4% of footprints have no year (not seen by the temporal model).",
        "<b>Flood 2025.</b> Sentinel-1 radar before (Jul to mid-Aug) and during (26 Aug to 5 Sep 2025) the flood, "
        "same orbit. Open land: darker than -18 dB and 3 dB darker than before. Built-up: 3 dB brighter (water "
        "against walls). " + ("Thresholds calibrated on geolocated reference points." if calibrated else
                              "<b>Thresholds are not yet calibrated against field or news locations; the flooded "
                              "building count is provisional and probably low.</b>"),
        "<b>Alerts.</b> Radar backscatter at least 3 dB above a 90-day baseline on two consecutive passes of the same "
        "orbit, inside the floodplain, on land not already built in 2023, patches of at least 0.5 ha. Alerts are "
        "candidates and must be verified on site.",
        "<b>Population.</b> WorldPop gridded estimate summed over the floodplain part of each unit; an area-level "
        "planning estimate only.",
        "<b>Resolution.</b> 10 m pixels: single houses, extra floors and small extensions are not visible.",
        CAVEAT)]
    doc.build(story, onFirstPage=_footer("Kinara · open data: Copernicus Sentinel-1/-2, Google Open Buildings, "
                                         "MERIT Hydro, HydroSHEDS, WorldPop"),
              onLaterPages=_footer("Kinara pre-monsoon exposure report"))
    return buf.getvalue()


__all__ = ["evidence_pdf", "fmt_date", "map_drawing", "premonsoon_pdf"]
