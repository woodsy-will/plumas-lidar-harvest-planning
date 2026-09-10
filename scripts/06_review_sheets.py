"""06_review_sheets.py - simulated cruise, QA checks and one review sheet per unit.

A BAF 20 variable-radius cruise on a 300 ft grid is simulated inside each unit from the canopy products
(dominant height and cover drive the tree list). Six recording errors are planted on purpose and listed in
data/work/qc_planted.json. The QA pass flags plots that fail checks; the review sheet for each unit carries
stand metrics, the flagged plots and a plot map, in the form a crew lead hands back to the field.

Outputs data/work/cruise_plots.gpkg, output/review/Unit_<id>_Review.pdf, output/review/Unit_Reviews.pdf,
        output/review/cruise_data.xlsx
Run: python-qgis-ltr.bat scripts\06_review_sheets.py
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from osgeo import gdal, ogr, osr
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
from scipy.ndimage import map_coordinates

gdal.UseExceptions(); ogr.UseExceptions(); osr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, WORK, OUT = (os.path.join(ROOT, p) for p in (os.path.join("data", "raw"), os.path.join("data", "work"), os.path.join("output", "review")))
os.makedirs(OUT, exist_ok=True)
BAF = 20.0; GRID = 300.0
SDI_MAX = 750          # FVS Western Sierra variant maximum SDI for Sierran mixed conifer (basal-area weighted default)
SE_STD_SAW = 18.0      # FSH 2409.12 R5 ch. 40 sampling-error standard (95 % confidence) for a small sawtimber sale; biomass sales 25 %
SE_STD_BIO = 25.0
MIN_PLOTS = 20         # R5 minimum plots per sampling unit (stratum)
T95 = 2.0              # t for a 95 % confidence interval, large-sample approximation
TARGET_SDI_PCT = 30    # demonstration planning target: leave the stand at 30 % of maximum SDI (a common thinning objective on these projects)
SPECIES = {"PP": ("Ponderosa pine", 0.30), "WF": ("White fir", 0.30), "DF": ("Douglas-fir", 0.15), "SP": ("Sugar pine", 0.10), "IC": ("Incense-cedar", 0.15)}
rng = np.random.default_rng(20260910)


def raster(name):
    d = gdal.Open(os.path.join(WORK, name)); b = d.GetRasterBand(1); a = b.ReadAsArray().astype("float32"); nd = b.GetNoDataValue()
    return np.where(a == nd, np.nan, a), d.GetGeoTransform()


dom, gt = raster("dom_height_66ft.tif"); cover, _ = raster("canopy_cover_66ft.tif"); slope, _ = raster("slope_pct.tif")


def sample(arr, x, y):
    return float(map_coordinates(np.nan_to_num(arr), [[(y - gt[3]) / gt[5]], [(x - gt[0]) / gt[1]]], order=1, mode="nearest")[0])


uds = ogr.Open(os.path.join(WORK, "planning.gpkg")); ul = uds.GetLayerByName("units"); sp = ul.GetSpatialRef()
units = [(dict((k, f.GetField(k)) for k in ("unit_id", "method", "acres")), f.GetGeometryRef().Clone()) for f in ul]

# ---- simulate plots and trees ----
plots, trees = [], []
for u, g in units:
    e = g.GetEnvelope(); x0 = math.floor(e[0] / GRID) * GRID; y0 = math.floor(e[2] / GRID) * GRID; n = 0
    for x in np.arange(x0, e[1] + GRID, GRID):
        for y in np.arange(y0, e[3] + GRID, GRID):
            if not g.Contains(ogr.CreateGeometryFromWkt(f"POINT ({x} {y})")):
                continue
            n += 1; pid = f"{u['unit_id']}-{n:02d}"
            dh = max(30.0, sample(dom, x, y)); cv = min(0.95, max(0.05, sample(cover, x, y)))
            ba_target = 60 + 180 * cv + rng.normal(0, 25)          # sq ft/ac, cover-driven
            ntrees = max(0, int(round(ba_target / BAF)))
            plots.append(dict(plot=pid, unit_id=u["unit_id"], x=float(x), y=float(y), n_trees=ntrees, slope=round(sample(slope, x, y)), cruiser="WS", date="2026-09-10", dom_ht=round(dh), cover=cv * 100))
            for t in range(ntrees):
                sp_code = rng.choice(list(SPECIES), p=[v[1] for v in SPECIES.values()])
                dbh = float(np.clip(rng.lognormal(math.log(0.28 * dh), 0.35), 5, 60))
                ht = float(np.clip(4.5 + (dh - 4.5) * (dbh / (0.28 * dh)) ** 0.45 + rng.normal(0, 8), 10, 220))
                trees.append(dict(plot=pid, unit_id=u["unit_id"], tree=t + 1, species=sp_code, dbh=round(dbh, 1), height=round(ht), status="L", defect=int(rng.choice([0, 0, 0, 5, 10, 20], p=[0.6, 0.15, 0.1, 0.05, 0.05, 0.05]))))
print(f"{len(plots)} plots, {len(trees)} trees across {len(units)} units")

# ---- plant recording errors ----
planted = []
def plant(kind, **kw):
    planted.append(dict(kind=kind, **kw))
cand = [p for p in plots if p["n_trees"] >= 3]
p1 = cand[3]; t1 = next(t for t in trees if t["plot"] == p1["plot"]); t1["species"] = "PPP"; plant("species_code", plot=p1["plot"], tree=t1["tree"])
p2 = cand[11]; t2 = next(t for t in trees if t["plot"] == p2["plot"]); t2["dbh"] = 999.0; plant("dbh_out_of_range", plot=p2["plot"], tree=t2["tree"])
p3 = cand[19]; g3 = next(g for u, g in units if u["unit_id"] == p3["unit_id"]); p3["x"] += 900; plant("plot_outside_unit", plot=p3["plot"])
p4 = cand[27]; p4["plot"] = cand[26]["plot"]; plant("duplicate_plot_id", plot=p4["plot"])
p5 = cand[35]; t5 = [t for t in trees if t["plot"] == p5["plot"]][1]; t5["height"] = None; plant("missing_height", plot=p5["plot"], tree=t5["tree"])
p6 = cand[43]; t6 = [t for t in trees if t["plot"] == p6["plot"]][0]; t6["height"] = 15; t6["dbh"] = 34.0; plant("height_dbh_mismatch", plot=p6["plot"], tree=t6["tree"])
json.dump(planted, open(os.path.join(WORK, "qc_planted.json"), "w"), indent=1)

# ---- QA checks ----
ugeom = {u["unit_id"]: g for u, g in units}
flags = {}
def flag(pid, msg):
    flags.setdefault(pid, []).append(msg)
seen = {}
for p in plots:
    seen.setdefault(p["plot"], 0); seen[p["plot"]] += 1
for pid, c in seen.items():
    if c > 1:
        flag(pid, f"duplicate plot id recorded {c} times")
for p in plots:
    if not ugeom[p["unit_id"]].Contains(ogr.CreateGeometryFromWkt(f"POINT ({p['x']} {p['y']})")):
        flag(p["plot"], "plot location falls outside its unit boundary (GPS or unit number error)")
for t in trees:
    if t["species"] not in SPECIES:
        flag(t["plot"], f"tree {t['tree']}: unknown species code '{t['species']}'")
    if t["dbh"] < 1 or t["dbh"] > 80:
        flag(t["plot"], f"tree {t['tree']}: DBH {t['dbh']} out of range")
    if t["height"] is None:
        flag(t["plot"], f"tree {t['tree']}: height missing")
    elif t["dbh"] >= 20 and t["height"] < 40:
        flag(t["plot"], f"tree {t['tree']}: height {t['height']} ft implausible for DBH {t['dbh']}")
found = set(flags)
print(f"QA flagged {len(found)} plots; planted errors caught: {sum(1 for e in planted if e['plot'] in found)} of {len(planted)}")

# ---- stand metrics per unit (BAF expansion; volume by a documented form-factor approximation) ----
def metrics(uid):
    ps = [p for p in plots if p["unit_id"] == uid]; n = len(ps)
    if n == 0:
        return None
    ba_plot = [p["n_trees"] * BAF for p in ps]
    tpa = 0.0; vol = 0.0; sumd2 = 0.0; sp_ba = {}
    for t in trees:
        if t["unit_id"] != uid or t["dbh"] > 80:
            continue
        ef = BAF / (0.005454 * t["dbh"] ** 2) / n; tpa += ef; sumd2 += ef * t["dbh"] ** 2
        h = t["height"] or 0; vol += ef * 0.005454 * t["dbh"] ** 2 * h * 0.42 * (1 - t["defect"] / 100)   # cu ft, form factor 0.42
        sp_ba[t["species"]] = sp_ba.get(t["species"], 0) + BAF / n
    ba = float(np.mean(ba_plot)); sd = float(np.std(ba_plot, ddof=1)) if n > 1 else 0.0; se = sd / math.sqrt(n)
    cv = sd / ba * 100 if ba else 0.0; se95 = T95 * se / ba * 100 if ba else 0.0
    std = SE_STD_SAW if sum(1 for t in trees if t["unit_id"] == uid and t["dbh"] >= 10) >= 0.5 * sum(1 for t in trees if t["unit_id"] == uid) else SE_STD_BIO
    n_needed = max(MIN_PLOTS, int(math.ceil((T95 * cv / std) ** 2))) if cv else MIN_PLOTS
    qmd = math.sqrt(sumd2 / tpa) if tpa else 0
    # Reineke stand density index (summation form) against the FVS Western Sierra maximum for mixed conifer;
    # CWHR size class from QMD and density class from canopy cover; sawtimber (>= 10 in) vs biomass split
    sdi = 0.0; saw = dict(ba=0.0, tpa=0.0, d2=0.0, vol=0.0); bio = dict(ba=0.0, tpa=0.0, d2=0.0, vol=0.0)
    for t in trees:
        if t["unit_id"] != uid or t["dbh"] > 80:
            continue
        ef = BAF / (0.005454 * t["dbh"] ** 2) / n; sdi += ef * (t["dbh"] / 10.0) ** 1.605
        h = t["height"] or 0; v = ef * 0.005454 * t["dbh"] ** 2 * h * 0.42 * (1 - t["defect"] / 100)
        g = saw if t["dbh"] >= 10 else bio; g["ba"] += BAF / n; g["tpa"] += ef; g["d2"] += ef * t["dbh"] ** 2; g["vol"] += v
    for g in (saw, bio):
        g["qmd"] = math.sqrt(g["d2"] / g["tpa"]) if g["tpa"] else 0.0
    size_cls = "1" if qmd < 1 else "2" if qmd < 6 else "3" if qmd < 11 else "4" if qmd < 24 else "5"
    cover = float(np.mean([p["cover"] for p in ps]))
    dens_cls = "S" if cover < 25 else "P" if cover < 40 else "M" if cover < 60 else "D"
    return dict(plots=n, ba=ba, se_pct=(se / ba * 100 if ba else 0), cv=cv, se95=se95, se_std=std, n_needed=n_needed, meets=(se95 <= std and n >= MIN_PLOTS), tpa=tpa, qmd=qmd, cuft=vol, mbf=vol / 1000 * 5.5, species=sorted(sp_ba.items(), key=lambda x: -x[1]),
                sdi=sdi, sdi_pct=sdi / SDI_MAX * 100, size_cls=size_cls, dens_cls=dens_cls, cover=cover, saw=saw, bio=bio, target_ba=ba * TARGET_SDI_PCT / max(1e-6, sdi / SDI_MAX * 100))

# ---- outputs: gpkg, xlsx ----
drv = ogr.GetDriverByName("GPKG"); gp = os.path.join(WORK, "cruise_plots.gpkg")
if os.path.exists(gp):
    drv.DeleteDataSource(gp)
ds = drv.CreateDataSource(gp); pl = ds.CreateLayer("plots", sp, ogr.wkbPoint)
for n, t in (("plot", ogr.OFTString), ("unit_id", ogr.OFTInteger), ("n_trees", ogr.OFTInteger), ("slope", ogr.OFTInteger), ("flags", ogr.OFTString)):
    pl.CreateField(ogr.FieldDefn(n, t))
for p in plots:
    f = ogr.Feature(pl.GetLayerDefn()); f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({p['x']} {p['y']})"))
    f.SetField("plot", p["plot"]); f.SetField("unit_id", p["unit_id"]); f.SetField("n_trees", p["n_trees"]); f.SetField("slope", p["slope"]); f.SetField("flags", "; ".join(flags.get(p["plot"], []))); pl.CreateFeature(f)
ds = None
wb = Workbook(); ws = wb.active; ws.title = "Plots"; ws.append(["plot", "unit_id", "x", "y", "n_trees", "slope_pct", "cruiser", "date", "qa_flags"])
for p in plots:
    ws.append([p["plot"], p["unit_id"], round(p["x"]), round(p["y"]), p["n_trees"], p["slope"], p["cruiser"], p["date"], "; ".join(flags.get(p["plot"], []))])
ws2 = wb.create_sheet("Trees"); ws2.append(["plot", "unit_id", "tree", "species", "dbh_in", "height_ft", "status", "defect_pct"])
for t in trees:
    ws2.append([t["plot"], t["unit_id"], t["tree"], t["species"], t["dbh"], t["height"], t["status"], t["defect"]])
ws3 = wb.create_sheet("Unit summary"); ws3.append(["unit_id", "method", "acres", "plots", "BA sqft/ac", "SE %", "TPA", "QMD in", "cu ft/ac", "MBF/ac (approx)", "SDI", "SDI % of max", "CWHR", "Sawtimber BA", "Biomass BA", "CV %", "SE % (95 %)", "SE standard %", "Plots needed", "Meets standard", "QA flags"])
for u, g in units:
    m = metrics(u["unit_id"])
    if m:
        ws3.append([u["unit_id"], u["method"], round(u["acres"], 1), m["plots"], round(m["ba"]), round(m["se_pct"], 1), round(m["tpa"]), round(m["qmd"], 1), round(m["cuft"]), round(m["mbf"], 1), round(m["sdi"]), round(m["sdi_pct"]), m["size_cls"] + m["dens_cls"], round(m["saw"]["ba"]), round(m["bio"]["ba"]), round(m["cv"]), round(m["se95"], 1), m["se_std"], m["n_needed"], "yes" if m["meets"] else "no", len({(p["plot"], f) for p in plots if p["unit_id"] == u["unit_id"] for f in flags.get(p["plot"], [])})])
for w in (ws, ws2, ws3):
    for c in w[1]:
        c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="DDE8D0")
wb.save(os.path.join(OUT, "cruise_data.xlsx"))

# ---- review sheets ----
# embed a TrueType face so the PDFs print identically anywhere (the base-14 Helvetica is never embedded)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
FONT = "Helvetica"; FONT_B = "Helvetica-Bold"
_fd = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if all(os.path.exists(os.path.join(_fd, f)) for f in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf")):
    for n, f in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Arial-Italic", "ariali.ttf"), ("Arial-BoldItalic", "arialbi.ttf")):
        pdfmetrics.registerFont(TTFont(n, os.path.join(_fd, f)))
    addMapping("Arial", 0, 0, "Arial"); addMapping("Arial", 1, 0, "Arial-Bold"); addMapping("Arial", 0, 1, "Arial-Italic"); addMapping("Arial", 1, 1, "Arial-BoldItalic")
    FONT, FONT_B = "Arial", "Arial-Bold"
styles = getSampleStyleSheet(); H = styles["Heading2"]; B = styles["BodyText"]; B.fontSize = 9; B.leading = 11
B.fontName = FONT; H.fontName = FONT_B; styles["Heading4"].fontName = FONT_B
merged = SimpleDocTemplate(os.path.join(OUT, "Unit_Reviews.pdf"), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
story = []
def build_page(u, g):
    uid = u["unit_id"]; m = metrics(uid)
    if not m:
        return None
    ps = [p for p in plots if p["unit_id"] == uid]
    # plot map
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    ring = g.GetGeometryRef(0).GetGeometryRef(0) if g.GetGeometryName() == "MULTIPOLYGON" else g.GetGeometryRef(0)
    ax.plot([ring.GetPoint_2D(i)[0] for i in range(ring.GetPointCount())], [ring.GetPoint_2D(i)[1] for i in range(ring.GetPointCount())], color="k", lw=1.2)
    for p in ps:
        bad = p["plot"] in flags; ax.plot(p["x"], p["y"], "o", ms=5, color=("#D55E00" if bad else "#0072B2"), mec="k"); ax.annotate(p["plot"].split("-")[1], (p["x"], p["y"]), fontsize=5, xytext=(3, 3), textcoords="offset points")
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(f"Unit {uid}: plots (orange = QA flag)", fontsize=8)
    mp = os.path.join(WORK, f"_plotmap_{uid}.png"); fig.tight_layout(); fig.savefig(mp, dpi=150); plt.close(fig)
    page = [Paragraph(f"Unit {uid} - Field Data Review", H),
            Paragraph(f"Mohawk Valley West Slope demonstration. Method <b>{u['method']}</b>, {u['acres']:.1f} ac, BAF {BAF:.0f} variable-radius cruise on a {GRID:.0f} ft grid, {m['plots']} plots. Simulated data with planted recording errors; see docs/methods.md.", B), Spacer(1, 6)]
    st = [["STAND DENSITY", "", "STAND INFO", ""],
          ["Basal area", f"{m['ba']:.0f} sq ft/ac  (1 SE = {m['se_pct']:.1f} %)", "Type", "Sierran mixed conifer"],
          ["Trees per acre", f"{m['tpa']:.0f}", "CWHR size / density", f"{m['size_cls']} / {m['dens_cls']}   (cover {m['cover']:.0f} %)"],
          ["QMD", f"{m['qmd']:.1f} in", "SDI", f"{m['sdi']:.0f}  ({m['sdi_pct']:.0f} % of max {SDI_MAX})"],
          ["SAWTIMBER  (>= 10 in)", "", "BIOMASS  (< 10 in)", ""],
          ["BA | QMD", f"{m['saw']['ba']:.0f} sq ft/ac | {m['saw']['qmd']:.1f} in", "BA | QMD", f"{m['bio']['ba']:.0f} sq ft/ac | {m['bio']['qmd']:.1f} in"],
          ["TPA", f"{m['saw']['tpa']:.0f}", "TPA", f"{m['bio']['tpa']:.0f}"],
          ["Volume", f"{m['saw']['vol']/1000*5.5:.1f} MBF/ac  ({m['saw']['vol']:.0f} cu ft)", "Volume", f"{m['bio']['vol']*0.03:.1f} green tons/ac approx. (60 lb per cu ft)"],
          ["TREATMENT TARGET", "", "CRUISE DESIGN", ""],
          ["Leave", f"{TARGET_SDI_PCT} % of max SDI  =  ~{m['target_ba']:.0f} sq ft/ac BA", "Sampling error", f"{m['se95']:.1f} % at 95 %  (standard {m['se_std']:.0f} %, R5 FSH 2409.12)"],
          ["Species (BA)", ", ".join(f"{s} {b:.0f}" for s, b in m["species"][:5]), "Plots", f"{m['plots']} taken, {m['n_needed']} needed (CV {m['cv']:.0f} %)  -  {'MEETS' if m['meets'] else 'SHORT'}"]]
    tbl = Table(st, colWidths=[1.1 * inch, 1.95 * inch, 1.25 * inch, 2.9 * inch])
    tbl.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde8d0")), ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#dde8d0")), ("BACKGROUND", (0, 8), (-1, 8), colors.HexColor("#dde8d0")), ("BACKGROUND", (0, 9), (0, 10), colors.HexColor("#f3f6ee")), ("BACKGROUND", (2, 9), (2, 10), colors.HexColor("#f3f6ee")),
                             ("FONTNAME", (0, 0), (-1, 0), FONT_B), ("FONTNAME", (0, 4), (-1, 4), FONT_B), ("FONTNAME", (0, 8), (-1, 8), FONT_B),
                             ("BACKGROUND", (0, 1), (0, 3), colors.HexColor("#f3f6ee")), ("BACKGROUND", (2, 1), (2, 3), colors.HexColor("#f3f6ee")), ("BACKGROUND", (0, 5), (0, 7), colors.HexColor("#f3f6ee")), ("BACKGROUND", (2, 5), (2, 7), colors.HexColor("#f3f6ee"))]))
    page += [tbl, Spacer(1, 8), Image(mp, width=4.2 * inch, height=3.2 * inch), Spacer(1, 6)]
    fl = list(dict.fromkeys((p["plot"], f) for p in ps for f in flags.get(p["plot"], [])))   # a duplicated plot id carries its flag twice; list it once
    page.append(Paragraph("<b>QA findings</b>: " + (f"{len(fl)} item(s) need crew follow-up" if fl else "no issues found; unit accepted") + ("" if m["meets"] else f"; cruise below the sampling-error standard, add {max(0, m['n_needed'] - m['plots'])} plots"), B))
    if fl:
        ft = Table([["Plot", "Finding"]] + fl, colWidths=[0.9 * inch, 5.5 * inch]); ft.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6e0dc")), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)])); page.append(ft)
    page += [Spacer(1, 8), Paragraph("Plot list", styles["Heading4"])]
    rows = [["Plot", "Trees in", "BA sq ft/ac", "Slope %", "Status"]] + [[p["plot"], p["n_trees"], p["n_trees"] * BAF, p["slope"], "FLAG" if p["plot"] in flags else "ok"] for p in ps]
    pt = Table(rows, colWidths=[0.9 * inch, 0.9 * inch, 1.1 * inch, 0.8 * inch, 0.8 * inch], repeatRows=1); pt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde8d0")), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
    page.append(pt)
    return page


for u, g in units:
    page = build_page(u, g)
    if page is None:
        continue
    SimpleDocTemplate(os.path.join(OUT, f"Unit_{u['unit_id']}_Review.pdf"), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch).build(page)
    story += build_page(u, g) + [PageBreak()]      # fresh flowables: a built table cannot be reused
qa_rows = [["Unit", "Method", "Acres", "Plots", "BA", "SE % (95 %)", "Std %", "Needed", "Design", "QA flags", "Status"]]
for u, g in units:
    m = metrics(u["unit_id"])
    if not m:
        continue
    nf = len({(p["plot"], f) for p in plots if p["unit_id"] == u["unit_id"] for f in flags.get(p["plot"], [])})
    qa_rows.append([u["unit_id"], u["method"], f"{u['acres']:.0f}", m["plots"], f"{m['ba']:.0f}", f"{m['se95']:.1f}", f"{m['se_std']:.0f}", m["n_needed"], "meets" if m["meets"] else "short", nf, "accepted" if (nf == 0 and m["meets"]) else "follow-up"])
qt = Table(qa_rows, repeatRows=1); qt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde8d0")), ("FONTNAME", (0, 0), (-1, 0), FONT_B)]
                          + [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fbe9e2")) for i, r in enumerate(qa_rows) if i and r[-1] == "follow-up"]))
front = [Paragraph("Field Data Review - Sale-level QA summary", H),
         Paragraph(f"Mohawk Valley West Slope demonstration. {len(plots)} plots, {len(trees)} trees, BAF {BAF:.0f} on a {GRID:.0f} ft grid. Sampling error is reported at 95 % confidence against the Region 5 cruising standard "
                   f"(FSH 2409.12 ch. 40: {SE_STD_SAW:.0f} % for a small sawtimber sale, {SE_STD_BIO:.0f} % for biomass, minimum {MIN_PLOTS} plots per stratum); plots needed = (t x CV / E)^2. "
                   f"QA flags are plots that failed a record check; {len(found)} flagged, {sum(1 for e in planted if e['plot'] in found)} of {len(planted)} planted errors caught.", B), Spacer(1, 8), qt, PageBreak()]
merged.build(front + story)
open(os.path.join(OUT, "qa_summary.csv"), "w", newline="").write("\n".join(",".join(str(c) for c in r) for r in qa_rows) + "\n")
print("review sheets written for", len(units), "units")
