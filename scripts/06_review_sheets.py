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
MIN_PLOTS = 20         # Region 5 practice minimum plots per stratum (reported; the WO standard is the sampling error)
TARGET_SDI_PCT = 35    # leave target at the lower limit of full site occupancy, 35 % of maximum SDI (Long 1985)
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

# ---- stand metrics per unit ----
# Standards and sources (all cited in docs/methods.md):
#   basal area per tree 0.005454 x DBH^2; BAF expansion; SDI in the summation form (Shaw 2000), maximum = basal-area-weighted
#   average of the FVS Western Sierra variant species maxima (table 3.5.1), relative-density zones 35 % (full occupancy) and
#   60 % (competition mortality) after Long (1985); cubic volume by form factor (Avery and Burkhart); Scribner board feet at
#   BF_PER_CF (Keegan et al. 2010, California mills); sampling error at 95 % with Student's t on n-1 df, tested against the
#   FSH 2409.12 ch. 40 sec. 41.1 standards: 40 % per stratum (tree-measurement sale) and exhibit 01 for the sale as a whole.
from scipy import stats
SDI_MAX_SP = {"PP": 365, "WF": 800, "DF": 570, "SP": 561, "IC": 576}     # FVS WS variant table 3.5.1 (2024 overview)
STRATUM_STD = 40.0                                                          # FSH 2409.12 41.1(5)(b), tree-measurement sales
SALE_TIERS = [(10000, 25), (20000, 20), (45000, 18), (70000, 16), (95000, 14), (120000, 12), (float("inf"), 10)]   # 41.1 exhibit 01, tree measurement
ASSUMED_STUMPAGE_PER_MBF = 50.0                                             # demonstration assumption to place the sale in exhibit 01
BF_PER_CF = 5.5; FORM_FACTOR = 0.42; GREEN_LB_PER_CF = 60.0
DBH_CLASS = 4                                                               # stand table class width, in
PRACTICE_MIN_PLOTS = MIN_PLOTS                                              # Region 5 practice, reported but not part of the WO standard


def tree_vol(t, ef):
    h = t["height"] or 0
    return ef * 0.005454 * t["dbh"] ** 2 * h * FORM_FACTOR * (1 - t["defect"] / 100)


def metrics(uid):
    ps = [p for p in plots if p["unit_id"] == uid]; n = len(ps)
    if n == 0:
        return None
    ba_plot = [p["n_trees"] * BAF for p in ps]
    tl = [t for t in trees if t["unit_id"] == uid and 1 <= t["dbh"] <= 80]
    tpa = vol = sumd2 = sdi = 0.0; sp_ba = {}; sp_stat = {}; cls_stat = {}
    saw = dict(n=0, ba=0.0, tpa=0.0, d2=0.0, vol=0.0); bio = dict(n=0, ba=0.0, tpa=0.0, d2=0.0, vol=0.0)
    for t in tl:
        ef = BAF / (0.005454 * t["dbh"] ** 2) / n; v = tree_vol(t, ef)
        tpa += ef; sumd2 += ef * t["dbh"] ** 2; vol += v; sdi += ef * (t["dbh"] / 10.0) ** 1.605
        sp_ba[t["species"]] = sp_ba.get(t["species"], 0) + BAF / n
        g = saw if t["dbh"] >= 10 else bio; g["n"] += 1; g["ba"] += BAF / n; g["tpa"] += ef; g["d2"] += ef * t["dbh"] ** 2; g["vol"] += v
        s = sp_stat.setdefault(t["species"], dict(n=0, tpa=0.0, ba=0.0, d2=0.0, vol=0.0)); s["n"] += 1; s["tpa"] += ef; s["ba"] += BAF / n; s["d2"] += ef * t["dbh"] ** 2; s["vol"] += v
        k = int(t["dbh"] // DBH_CLASS) * DBH_CLASS
        c = cls_stat.setdefault(k, dict(n=0, tpa=0.0, ba=0.0, vol=0.0)); c["n"] += 1; c["tpa"] += ef; c["ba"] += BAF / n; c["vol"] += v
    for g in (saw, bio):
        g["qmd"] = math.sqrt(g["d2"] / g["tpa"]) if g["tpa"] else 0.0
    for s in sp_stat.values():
        s["qmd"] = math.sqrt(s["d2"] / s["tpa"]) if s["tpa"] else 0.0
    ba = float(np.mean(ba_plot)); sd = float(np.std(ba_plot, ddof=1)) if n > 1 else 0.0; se = sd / math.sqrt(n)
    tval = float(stats.t.ppf(0.975, n - 1)) if n > 1 else 2.0
    cv = sd / ba * 100 if ba else 0.0; se95 = tval * se / ba * 100 if ba else 0.0
    n_for_std = int(math.ceil((tval * cv / STRATUM_STD) ** 2)) if cv else 1
    qmd = math.sqrt(sumd2 / tpa) if tpa else 0
    known = {k: v for k, v in sp_ba.items() if k in SDI_MAX_SP}
    sdimax = sum(v * SDI_MAX_SP[k] for k, v in known.items()) / sum(known.values()) if known else float(np.mean(list(SDI_MAX_SP.values())))
    sdi_pct = sdi / sdimax * 100 if sdimax else 0.0
    size_cls = "1" if qmd < 1 else "2" if qmd < 6 else "3" if qmd < 11 else "4" if qmd < 24 else "5"
    cover = float(np.mean([p["cover"] for p in ps]))
    dens_cls = "open" if cover < 10 else "S" if cover < 25 else "P" if cover < 40 else "M" if cover < 60 else "D"   # CWHR: S 10-24, P 25-39, M 40-59, D 60-100
    return dict(plots=n, ba=ba, sd=sd, se_pct=(se / ba * 100 if ba else 0), tval=tval, cv=cv, se95=se95, se_std=STRATUM_STD, n_for_std=n_for_std,
                meets=(se95 <= STRATUM_STD), practice_ok=(n >= PRACTICE_MIN_PLOTS), tpa=tpa, qmd=qmd, cuft=vol, mbf=vol / 1000 * BF_PER_CF,
                species=sorted(sp_ba.items(), key=lambda x: -x[1]), sp_stat=sp_stat, cls_stat=cls_stat, sdi=sdi, sdimax=sdimax, sdi_pct=sdi_pct,
                size_cls=size_cls, dens_cls=dens_cls, cover=cover, saw=saw, bio=bio, target_ba=ba * TARGET_SDI_PCT / max(1e-6, sdi_pct))


M = {u["unit_id"]: metrics(u["unit_id"]) for u, g in units}
# sale as a whole: stratified by unit with area weights (FSH 2409.12 41.1: standards apply at the sale and stratum level)
tot_ac = sum(u["acres"] for u, g in units); sale_ba = sum(u["acres"] / tot_ac * M[u["unit_id"]]["ba"] for u, g in units if M[u["unit_id"]])
sale_var = sum((u["acres"] / tot_ac) ** 2 * M[u["unit_id"]]["sd"] ** 2 / M[u["unit_id"]]["plots"] for u, g in units if M[u["unit_id"]])
sale_se95 = 2 * math.sqrt(sale_var) / sale_ba * 100
sale_mbf = sum(u["acres"] * M[u["unit_id"]]["mbf"] for u, g in units if M[u["unit_id"]]); sale_value = sale_mbf * ASSUMED_STUMPAGE_PER_MBF
sale_std = next(pct for lim, pct in SALE_TIERS if sale_value < lim)
print(f"sale as a whole: BA {sale_ba:.0f} sq ft/ac, SE {sale_se95:.1f} % at 95 %, standard {sale_std} % for an assumed value of ${sale_value:,.0f}")

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

from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
wb = Workbook(); ws = wb.active; ws.title = "Plots"; ws.append(["plot", "unit_id", "x_ft", "y_ft", "trees_in", "BA_sqft_ac", "slope_pct", "cruiser", "date", "qa_flags"])
for p in plots:
    ws.append([p["plot"], p["unit_id"], round(p["x"]), round(p["y"]), p["n_trees"], p["n_trees"] * BAF, p["slope"], p["cruiser"], p["date"], "; ".join(flags.get(p["plot"], []))])
ws2 = wb.create_sheet("Trees"); ws2.append(["plot", "unit_id", "tree", "species", "dbh_in", "height_ft", "status", "defect_pct", "BA_sqft", "expansion_TPA_per_plot"])
for t in trees:
    ws2.append([t["plot"], t["unit_id"], t["tree"], t["species"], t["dbh"], t["height"], t["status"], t["defect"], round(0.005454 * t["dbh"] ** 2, 3) if 1 <= t["dbh"] <= 80 else None, round(BAF / (0.005454 * t["dbh"] ** 2), 2) if 1 <= t["dbh"] <= 80 else None])
ws3 = wb.create_sheet("Unit summary")
ws3.append(["unit_id", "method", "acres", "plots", "BA sq ft/ac", "SD of plot BA", "CV %", "t (95 %, n-1)", "SE % at 95 %", "stratum standard %", "meets standard", "plots for standard", "20-plot practice", "TPA", "QMD in", "cu ft/ac", "MBF/ac Scribner", "SDI", "SDI max (BA-wtd FVS WS)", "SDI % of max", "CWHR size", "CWHR density", "Sawtimber BA", "Biomass BA", "QA flags"])
for u, g in units:
    m = M[u["unit_id"]]
    if m:
        nf = len({(p["plot"], f) for p in plots if p["unit_id"] == u["unit_id"] for f in flags.get(p["plot"], [])})
        ws3.append([u["unit_id"], u["method"], round(u["acres"], 1), m["plots"], round(m["ba"], 1), round(m["sd"], 1), round(m["cv"], 1), round(m["tval"], 3), round(m["se95"], 1), m["se_std"], "yes" if m["meets"] else "no", m["n_for_std"], "yes" if m["practice_ok"] else "no",
                    round(m["tpa"]), round(m["qmd"], 1), round(m["cuft"]), round(m["mbf"], 1), round(m["sdi"]), round(m["sdimax"]), round(m["sdi_pct"]), m["size_cls"], m["dens_cls"], round(m["saw"]["ba"]), round(m["bio"]["ba"]), nf])
ws4 = wb.create_sheet("Stand tables"); ws4.append(["unit_id", "DBH class (in)", "trees tallied", "TPA", "BA sq ft/ac", "cu ft/ac", "MBF/ac"])
for u, g in units:
    m = M[u["unit_id"]]
    for k in sorted(m["cls_stat"]):
        c = m["cls_stat"][k]; ws4.append([u["unit_id"], f"{k}-{k + DBH_CLASS - 0.1:.1f}", c["n"], round(c["tpa"], 1), round(c["ba"], 1), round(c["vol"]), round(c["vol"] / 1000 * BF_PER_CF, 2)])
ws5 = wb.create_sheet("Stock tables"); ws5.append(["unit_id", "species", "trees tallied", "TPA", "BA sq ft/ac", "QMD in", "cu ft/ac", "MBF/ac"])
for u, g in units:
    m = M[u["unit_id"]]
    for k, s in sorted(m["sp_stat"].items(), key=lambda x: -x[1]["ba"]):
        ws5.append([u["unit_id"], k, s["n"], round(s["tpa"], 1), round(s["ba"], 1), round(s["qmd"], 1), round(s["vol"]), round(s["vol"] / 1000 * BF_PER_CF, 2)])
ws6 = wb.create_sheet("Standards and assumptions")
for row in (["item", "value", "source"],
            ["Basal area factor", BAF, "variable-radius (prism) cruise; BA/ac = trees in x BAF"],
            ["Tree basal area", "0.005454 x DBH^2 sq ft", "standard mensuration"],
            ["Expansion factor", "BAF / tree BA, divided by plots", "per-tree trees per acre"],
            ["Sampling error", "t(0.975, n-1) x SE / mean, percent", "FSH 2409.12 ch. 40, 41.1: 95 % confidence (t = 2 for large n)"],
            ["Stratum standard", f"{STRATUM_STD:.0f} %", "FSH 2409.12 ch. 40, 41.1(5)(b): tree-measurement sales"],
            ["Sale-as-a-whole standard", f"{sale_std} % at an assumed value of ${sale_value:,.0f}", "FSH 2409.12 ch. 40, 41.1 exhibit 01 (tree measurement column)"],
            ["Sale-as-a-whole estimate", "stratified by unit, area weights; var = sum(W^2 s^2 / n)", "Cochran; FSH 2409.12 ch. 30"],
            ["Practice minimum plots", PRACTICE_MIN_PLOTS, "Region 5 practice on these projects; reported, not part of the WO standard"],
            ["Plots for standard", "(t x CV / E)^2", "FSH 2409.12 ch. 30 sample size"],
            ["SDI", "sum over trees of TPA x (DBH/10)^1.605", "Reineke 1933; summation form Shaw 2000"],
            ["SDI maximum", "BA-weighted mean of species maxima: " + ", ".join(f"{k} {v}" for k, v in SDI_MAX_SP.items()), "FVS Western Sierra variant overview, table 3.5.1"],
            ["Relative density zones", "35 % of max = lower limit of full site occupancy; 60 % = onset of competition mortality", "Long 1985; Long and Shaw 2012 (Sierra mixed conifer DMD)"],
            ["Leave target", f"{TARGET_SDI_PCT} % of max SDI, expressed as BA", "demonstration target at the full-occupancy threshold"],
            ["Cubic volume", f"BA x total height x form factor {FORM_FACTOR}, net of defect", "form-factor approximation (Avery and Burkhart); regional NVEL equations would replace it in practice"],
            ["Board feet", f"{BF_PER_CF} Scribner bf per cu ft", "Keegan et al. 2010: California mills among the highest BF/CF ratios in the West (about 5.5 to 5.7)"],
            ["Biomass green tons", f"{GREEN_LB_PER_CF:.0f} lb per cu ft green", "conifer green density assumption"],
            ["CWHR size class", "QMD: 1 <1 in, 2 1-6, 3 6-11, 4 11-24, 5 >24", "California Wildlife Habitat Relationships"],
            ["CWHR density class", "canopy cover: S 10-24 %, P 25-39, M 40-59, D 60-100", "California Wildlife Habitat Relationships"],
            ["Data", "simulated cruise with six planted recording errors", "docs/methods.md"]):
    ws6.append(row)
for w in (ws, ws2, ws3, ws4, ws5, ws6):
    for c in w[1]:
        c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="DDE8D0"); c.alignment = Alignment(wrap_text=True, vertical="top")
    w.freeze_panes = "A2"
    for i, col in enumerate(w.columns, 1):
        w.column_dimensions[get_column_letter(i)].width = min(60, max(10, max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:200]) + 2))
wb.save(os.path.join(OUT, "cruise_data.xlsx"))

# ---- review sheets (one per unit) and the merged PDF ----
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import KeepTogether
FONT = "Helvetica"; FONT_B = "Helvetica-Bold"
_fd = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if all(os.path.exists(os.path.join(_fd, f)) for f in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf")):
    for nme, f in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Arial-Italic", "ariali.ttf"), ("Arial-BoldItalic", "arialbi.ttf")):
        pdfmetrics.registerFont(TTFont(nme, os.path.join(_fd, f)))
    addMapping("Arial", 0, 0, "Arial"); addMapping("Arial", 1, 0, "Arial-Bold"); addMapping("Arial", 0, 1, "Arial-Italic"); addMapping("Arial", 1, 1, "Arial-BoldItalic")
    FONT, FONT_B = "Arial", "Arial-Bold"
styles = getSampleStyleSheet(); H = styles["Heading2"]; B = styles["BodyText"]; B.fontSize = 9; B.leading = 11
B.fontName = FONT; H.fontName = FONT_B
from reportlab.lib.styles import ParagraphStyle
TT = ParagraphStyle("tt", parent=B, fontName=FONT_B, fontSize=8.5, leading=10, spaceBefore=6, spaceAfter=2)      # table title, above the table
FN = ParagraphStyle("fn", parent=B, fontName=FONT, fontSize=7, leading=8.5, textColor=colors.HexColor("#444444"), spaceBefore=2)   # footnote, below
GREEN, PALE, GRIDC = colors.HexColor("#dde8d0"), colors.HexColor("#f3f6ee"), colors.HexColor("#999999")


def tstyle(head_rows=(0,), first_col=True, size=8, extra=()):
    st = [("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), size), ("LEADING", (0, 0), (-1, -1), size + 2),
          ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black), ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black), ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.black),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    for r in head_rows:
        st += [("FONTNAME", (0, r), (-1, r), FONT_B), ("BACKGROUND", (0, r), (-1, r), GREEN)]
    return TableStyle(st + list(extra))


merged = SimpleDocTemplate(os.path.join(OUT, "Unit_Reviews.pdf"), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch, title="Field data review sheets", author="William Steinley")
story = []


def build_page(u, g):
    uid = u["unit_id"]; m = M[uid]
    if not m:
        return None
    ps = [p for p in plots if p["unit_id"] == uid]
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    rings = [g.GetGeometryRef(i).GetGeometryRef(0) for i in range(g.GetGeometryCount())] if g.GetGeometryName() == "MULTIPOLYGON" else [g.GetGeometryRef(0)]
    for ring in rings:
        ax.plot([ring.GetPoint_2D(i)[0] for i in range(ring.GetPointCount())], [ring.GetPoint_2D(i)[1] for i in range(ring.GetPointCount())], color="k", lw=1.2)
    for p in ps:
        bad = p["plot"] in flags; ax.plot(p["x"], p["y"], "o", ms=5, color=("#D55E00" if bad else "#0072B2"), mec="k"); ax.annotate(p["plot"].split("-")[1], (p["x"], p["y"]), fontsize=5, xytext=(3, 3), textcoords="offset points")
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(f"Unit {uid}: plots on the {GRID:.0f} ft grid (orange = QA flag)", fontsize=8)
    for sde in ("top", "right", "left", "bottom"):
        ax.spines[sde].set_visible(True)
    mp = os.path.join(WORK, f"_plotmap_{uid}.png"); fig.tight_layout(); fig.savefig(mp, dpi=200); plt.close(fig)
    page = [Paragraph(f"Unit {uid} - Field Data Review", H),
            Paragraph(f"Mohawk Valley West Slope demonstration. Method <b>{u['method']}</b>, {u['acres']:.1f} ac, BAF {BAF:.0f} variable-radius cruise on a {GRID:.0f} ft grid, {m['plots']} plots, {sum(p['n_trees'] for p in ps)} trees tallied. Simulated data with planted recording errors; see docs/methods.md.", B)]
    # Table 1: stand summary
    st = [["STAND DENSITY", "", "STAND INFO", ""],
          ["Basal area", f"{m['ba']:.0f} sq ft/ac  (SE {m['se_pct']:.1f} %)", "Type", "Sierran mixed conifer"],
          ["Trees per acre", f"{m['tpa']:.0f}", "CWHR size / density", f"{m['size_cls']} / {m['dens_cls']}   (cover {m['cover']:.0f} %)"],
          ["QMD", f"{m['qmd']:.1f} in", "SDI", f"{m['sdi']:.0f}  ({m['sdi_pct']:.0f} % of max {m['sdimax']:.0f})"],
          ["SAWTIMBER  (>= 10 in)", "", "BIOMASS  (< 10 in)", ""],
          ["BA | QMD", f"{m['saw']['ba']:.0f} sq ft/ac | {m['saw']['qmd']:.1f} in", "BA | QMD", f"{m['bio']['ba']:.0f} sq ft/ac | {m['bio']['qmd']:.1f} in"],
          ["TPA", f"{m['saw']['tpa']:.0f}", "TPA", f"{m['bio']['tpa']:.0f}"],
          ["Volume", f"{m['saw']['vol'] / 1000 * BF_PER_CF:.1f} MBF/ac  ({m['saw']['vol']:.0f} cu ft)", "Volume", f"{m['bio']['vol'] * GREEN_LB_PER_CF / 2000:.1f} green tons/ac  ({m['bio']['vol']:.0f} cu ft)"],
          ["TREATMENT TARGET", "", "CRUISE DESIGN", ""],
          ["Leave", f"{TARGET_SDI_PCT} % of max SDI  =  ~{m['target_ba']:.0f} sq ft/ac BA", "Sampling error", f"{m['se95']:.1f} % at 95 %  (t = {m['tval']:.2f}, n = {m['plots']})"],
          ["Species (BA)", ", ".join(f"{s} {b:.0f}" for s, b in m["species"][:5]), "Stratum standard", f"{m['se_std']:.0f} %  -  {'MEETS' if m['meets'] else 'FAILS'};  {m['plots']} plots vs 20-plot practice: {'ok' if m['practice_ok'] else 'SHORT by ' + str(PRACTICE_MIN_PLOTS - m['plots'])}"]]
    t1 = Table(st, colWidths=[1.1 * inch, 1.95 * inch, 1.25 * inch, 2.9 * inch])
    t1.setStyle(tstyle(head_rows=(0, 4, 8), extra=[("BACKGROUND", (0, r0), (0, r1), PALE) for r0, r1 in ((1, 3), (5, 7), (9, 10))] + [("BACKGROUND", (2, r0), (2, r1), PALE) for r0, r1 in ((1, 3), (5, 7), (9, 10))]))
    page += [Paragraph("Table 1. Stand summary from the BAF 20 cruise, per acre", TT), t1,
             Paragraph(f"Cubic volume by form factor {FORM_FACTOR} net of defect; Scribner board feet at {BF_PER_CF} bf/cu ft (Keegan et al. 2010); green tons at {GREEN_LB_PER_CF:.0f} lb/cu ft. SDI in the summation form; maximum is the basal-area-weighted FVS Western Sierra species maximum. "
                       f"Sampling error at 95 % confidence with Student's t; stratum standard {STRATUM_STD:.0f} % for tree-measurement sales (FSH 2409.12 ch. 40, 41.1).", FN)]
    # Table 2: stand table by DBH class; Table 3: stock table by species, side by side
    rows2 = [["DBH class, in", "Trees", "TPA", "BA", "cu ft", "MBF"]] + [[f"{k}-{k + DBH_CLASS - 1:.0f}.9", c["n"], f"{c['tpa']:.1f}", f"{c['ba']:.1f}", f"{c['vol']:.0f}", f"{c['vol'] / 1000 * BF_PER_CF:.1f}"] for k, c in sorted(m["cls_stat"].items())]
    rows2.append(["All", sum(c["n"] for c in m["cls_stat"].values()), f"{m['tpa']:.1f}", f"{m['ba']:.1f}", f"{m['cuft']:.0f}", f"{m['mbf']:.1f}"])
    t2 = Table(rows2, colWidths=[0.95 * inch, 0.5 * inch, 0.5 * inch, 0.5 * inch, 0.55 * inch, 0.5 * inch]); t2.setStyle(tstyle(extra=[("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), FONT_B), ("LINEABOVE", (0, -1), (-1, -1), 0.4, colors.black)]))
    rows3 = [["Species", "Trees", "TPA", "BA", "QMD", "cu ft", "MBF"]] + [[k, s["n"], f"{s['tpa']:.1f}", f"{s['ba']:.1f}", f"{s['qmd']:.1f}", f"{s['vol']:.0f}", f"{s['vol'] / 1000 * BF_PER_CF:.1f}"] for k, s in sorted(m["sp_stat"].items(), key=lambda x: -x[1]["ba"])]
    rows3.append(["All", sum(s["n"] for s in m["sp_stat"].values()), f"{m['tpa']:.1f}", f"{m['ba']:.1f}", f"{m['qmd']:.1f}", f"{m['cuft']:.0f}", f"{m['mbf']:.1f}"])
    t3 = Table(rows3, colWidths=[0.7 * inch, 0.5 * inch, 0.5 * inch, 0.5 * inch, 0.5 * inch, 0.55 * inch, 0.5 * inch]); t3.setStyle(tstyle(extra=[("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), FONT_B), ("LINEABOVE", (0, -1), (-1, -1), 0.4, colors.black)]))
    side = Table([[[Paragraph(f"Table 2. Stand table by {DBH_CLASS}-inch DBH class, per acre", TT), t2], [Paragraph("Table 3. Stock table by species, per acre", TT), t3]]], colWidths=[3.6 * inch, 3.7 * inch])
    side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    page += [side, Paragraph("Trees = trees tallied in the cruise; TPA, BA (sq ft/ac), cubic feet and Scribner MBF per acre by BAF expansion. Species: PP ponderosa pine, WF white fir, DF Douglas-fir, SP sugar pine, IC incense-cedar.", FN)]
    page += [Spacer(1, 4), Image(mp, width=4.2 * inch, height=3.2 * inch), Paragraph("Figure 1. Plot locations with QA status.", FN), Spacer(1, 4)]
    fl = list(dict.fromkeys((p["plot"], f) for p in ps for f in flags.get(p["plot"], [])))
    page.append(Paragraph("<b>QA findings</b>: " + (f"{len(fl)} item(s) need crew follow-up" if fl else "no issues found; unit accepted") + ("" if m["meets"] else "; sampling error exceeds the stratum standard") + ("" if m["practice_ok"] else f"; {PRACTICE_MIN_PLOTS - m['plots']} more plots would meet the 20-plot practice"), B))
    if fl:
        ft = Table([["Plot", "Finding"]] + fl, colWidths=[0.9 * inch, 6.3 * inch]); ft.setStyle(tstyle(extra=[("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6e0dc"))])); page.append(ft)
    rows = [["Plot", "Trees in", "BA sq ft/ac", "Slope %", "Status"]] + [[p["plot"], p["n_trees"], f"{p['n_trees'] * BAF:.0f}", p["slope"], "FLAG" if p["plot"] in flags else "ok"] for p in ps]
    pt = Table(rows, colWidths=[0.9 * inch, 0.9 * inch, 1.1 * inch, 0.8 * inch, 0.8 * inch], repeatRows=1); pt.setStyle(tstyle(extra=[("ALIGN", (1, 0), (3, -1), "RIGHT")]))
    page += [Spacer(1, 6), KeepTogether([Paragraph("Table 4. Plot list", TT), pt])]
    return page


for u, g in units:
    page = build_page(u, g)
    if page is None:
        continue
    SimpleDocTemplate(os.path.join(OUT, f"Unit_{u['unit_id']}_Review.pdf"), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch, title=f"Unit {u['unit_id']} field data review", author="William Steinley").build(page)
    story += build_page(u, g) + [PageBreak()]      # fresh flowables: a built table cannot be reused

qa_rows = [["Unit", "Method", "Acres", "Plots", "BA", "CV %", "t", "SE % (95 %)", "Std %", "Design", "20-plot", "QA flags", "Status"]]
for u, g in units:
    m = M[u["unit_id"]]
    if not m:
        continue
    nf = len({(p["plot"], f) for p in plots if p["unit_id"] == u["unit_id"] for f in flags.get(p["plot"], [])})
    qa_rows.append([u["unit_id"], u["method"], f"{u['acres']:.0f}", m["plots"], f"{m['ba']:.0f}", f"{m['cv']:.0f}", f"{m['tval']:.2f}", f"{m['se95']:.1f}", f"{m['se_std']:.0f}", "meets" if m["meets"] else "fails", "ok" if m["practice_ok"] else "short", nf, "accepted" if (nf == 0 and m["meets"]) else "follow-up"])
qt = Table(qa_rows, repeatRows=1); qt.setStyle(tstyle(extra=[("ALIGN", (2, 0), (-2, -1), "RIGHT")] + [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fbe9e2")) for i, r in enumerate(qa_rows) if i and r[-1] == "follow-up"]))
front = [Paragraph("Field Data Review - Sale-level QA summary", H),
         Paragraph(f"Mohawk Valley West Slope demonstration. {len(plots)} plots, {len(trees)} trees, BAF {BAF:.0f} on a {GRID:.0f} ft grid across {len(units)} units ({tot_ac:,.0f} ac). "
                   f"<b>Sale as a whole</b> (stratified by unit, area weights): basal area {sale_ba:.0f} sq ft/ac, sampling error {sale_se95:.1f} % at 95 % confidence against the exhibit 01 standard of {sale_std} % "
                   f"for a tree-measurement sale valued at about ${sale_value:,.0f} ({sale_mbf / 1000:,.0f} MBF at an assumed ${ASSUMED_STUMPAGE_PER_MBF:.0f}/MBF): <b>{'MEETS' if sale_se95 <= sale_std else 'FAILS'}</b>. "
                   f"<b>Strata</b>: each unit is tested against the {STRATUM_STD:.0f} % stratum standard for tree-measurement sales (FSH 2409.12 ch. 40, sec. 41.1); the 20-plot column reports the Region 5 practice minimum. "
                   f"QA flags are plots that failed a record check; {len(found)} flagged, {sum(1 for e in planted if e['plot'] in found)} of {len(planted)} planted errors caught.", B), Spacer(1, 8),
         Paragraph("Table A. Cruise statistics and QA status by unit (stratum)", TT), qt,
         Paragraph("BA in sq ft/ac; CV = coefficient of variation of plot basal area; t = Student's t at 95 % on n-1 df; SE % = t x standard error / mean.", FN), PageBreak()]
merged.build(front + story)
open(os.path.join(OUT, "qa_summary.csv"), "w", newline="").write("\n".join(",".join(str(c) for c in r) for r in qa_rows) + "\n")
print("review sheets written for", len(units), "units")
