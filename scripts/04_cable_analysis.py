"""04_cable_analysis.py - planning-level skyline feasibility for every harvest unit.

For each unit: candidate landings on NFS roads within 300 ft of the unit, corridors cast every 10 degrees
from each landing to a tailhold 100 ft past the far boundary, DTM profiles every 10 ft, chord geometry for a
50 ft tower (70 ft alternative) and a 10 ft tailhold anchor. Feasible when the ground stays 10 ft or more
below the chord and mid-span deflection is at least 6 % of span. See docs/methods.md.

Outputs
  data/work/cable.gpkg          landings, corridors (all, with feasibility attributes)
  output/cable/unit_summary.csv one row per unit
  output/cable/Unit_<id>_profiles.png     the best corridors' profiles with chord and clearance
  output/cable/Unit_<id>_corridor_map.png corridor map on the hillshade
  output/cable/Fig*.png                   sale-level figures: slope, deflection, equipment, difficulty
Run: python-qgis-ltr.bat scripts\04_cable_analysis.py
"""
import csv
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from osgeo import gdal, ogr, osr
from scipy.ndimage import map_coordinates

gdal.UseExceptions(); osr.UseExceptions(); ogr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, WORK, OUT = (os.path.join(ROOT, p) for p in (os.path.join("data", "raw"), os.path.join("data", "work"), os.path.join("output", "cable")))
os.makedirs(OUT, exist_ok=True)

TOWER = 50.0; TOWER_ALT = 70.0; ANCHOR = 10.0
MIN_CLEAR = 10.0; MIN_DEFLECTION = 0.06
STEP = 10.0; BEARING_STEP = 5; LANDING_SPACING = 200.0; LANDING_REACH = 500.0; TAILHOLD_PAST = 100.0
FALLBACK_REACH = 2000.0      # a unit with no road within LANDING_REACH is served from its nearest road points
LATERAL = 150.0              # lateral yarding each side of a corridor
SPAN_CLASSES = [(1000, "Small yarder"), (1800, "Medium yarder"), (3000, "Long-span yarder"), (1e9, "Intermediate support needed")]

dtm_ds = gdal.Open(os.path.join(WORK, "dtm_3ft.tif")); gt = dtm_ds.GetGeoTransform()
dtm = dtm_ds.GetRasterBand(1).ReadAsArray().astype("float32"); nd = dtm_ds.GetRasterBand(1).GetNoDataValue()
dtm = np.where(dtm == nd, np.nan, dtm)
hs_ds = gdal.Open(os.path.join(WORK, "hillshade.tif")); hs = hs_ds.GetRasterBand(1).ReadAsArray()
sp = osr.SpatialReference(); sp.ImportFromWkt(dtm_ds.GetProjection()); sp.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_sp = osr.CoordinateTransformation(s4326, sp)


def elev_at(xs, ys):
    cols = (np.asarray(xs) - gt[0]) / gt[1]; rows = (np.asarray(ys) - gt[3]) / gt[5]
    return map_coordinates(np.nan_to_num(dtm, nan=np.nanmean(dtm)), [rows, cols], order=1, mode="nearest")


def road_points():
    feats = json.load(open(os.path.join(RAW, "fs_roads.geojson")))["features"]
    tiger = os.path.join(RAW, "tiger_roads.geojson")
    if os.path.exists(tiger):
        feats = feats + json.load(open(tiger))["features"]
    pts = []
    for f in feats:
        g = ogr.CreateGeometryFromJson(json.dumps(f["geometry"])); g.Transform(to_sp)
        lines = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryName() == "MULTILINESTRING" else [g]
        for ln in lines:
            L = ln.Length(); n = max(1, int(L // LANDING_SPACING))
            for k in range(n + 1):
                p = ln.Value(min(L, k * LANDING_SPACING)) if hasattr(ln, "Value") else None
                if p is None:
                    d = k * LANDING_SPACING; acc = 0.0
                    for i in range(ln.GetPointCount() - 1):
                        x0, y0 = ln.GetPoint_2D(i); x1, y1 = ln.GetPoint_2D(i + 1); seg = math.hypot(x1 - x0, y1 - y0)
                        if acc + seg >= d:
                            t = (d - acc) / seg if seg else 0; pts.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0))); break
                        acc += seg
                else:
                    pts.append((p.GetX(), p.GetY()))
    return pts


def analyse_corridor(x0, y0, x1, y1, tower):
    """Profile from landing (x0,y0) to tailhold (x1,y1). Returns dict or None."""
    span = math.hypot(x1 - x0, y1 - y0)
    if span < 150:
        return None
    n = int(span // STEP) + 1
    xs = np.linspace(x0, x1, n); ys = np.linspace(y0, y1, n); d = np.linspace(0, span, n); z = elev_at(xs, ys)
    z_tower = z[0] + tower; z_anchor = z[-1] + ANCHOR
    chord = z_tower + (z_anchor - z_tower) * d / span
    clearance = chord - z
    mid = n // 2
    deflection = clearance[mid] / span
    min_clear = float(clearance[1:-1].min()) if n > 2 else float(clearance.min())
    feasible = bool(min_clear >= MIN_CLEAR and deflection >= MIN_DEFLECTION)
    grade = (z[-1] - z[0]) / span * 100          # positive = tailhold above landing = uphill yarding to the landing? no: logs travel to landing
    seg_slope = np.abs(np.diff(z)) / STEP * 100
    span_class = next(lbl for lim, lbl in SPAN_CLASSES if span <= lim)
    return dict(span=span, deflection=float(deflection), min_clear=min_clear, feasible=feasible, grade=float(grade),
                downhill=bool(z[-1] > z[0]),    # tailhold higher than landing: logs come downhill to the landing
                max_slope=float(seg_slope.max()), mean_slope=float(seg_slope.mean()), span_class=span_class,
                d=d, z=z, chord=chord, clearance=clearance, x=xs, y=ys)


def unit_geoms():
    ds = ogr.Open(os.path.join(WORK, "planning.gpkg")); lyr = ds.GetLayerByName("units"); out = []
    for f in lyr:
        out.append((dict((k, f.GetField(k)) for k in ("unit_id", "method", "acres", "slope_mean")), f.GetGeometryRef().Clone()))
    return out


def cast_tailhold(g, x0, y0, bearing):
    """Walk from the landing along a bearing; return the point 100 ft beyond the last boundary crossing inside the unit."""
    dx, dy = math.sin(math.radians(bearing)), math.cos(math.radians(bearing))
    far = ogr.Geometry(ogr.wkbLineString); far.AddPoint(x0, y0); far.AddPoint(x0 + dx * 4000, y0 + dy * 4000)
    inter = g.Intersection(far)
    if inter is None or inter.IsEmpty():
        return None
    pts = []
    parts = [inter.GetGeometryRef(i) for i in range(inter.GetGeometryCount())] if inter.GetGeometryCount() else [inter]
    for p in parts:
        for i in range(p.GetPointCount()):
            pts.append(p.GetPoint_2D(i))
    if not pts:
        return None
    dmax = max(math.hypot(px - x0, py - y0) for px, py in pts)
    if dmax < 100:
        return None
    reach = dmax + TAILHOLD_PAST
    return x0 + dx * reach, y0 + dy * reach, dmax


rp = road_points(); print(f"{len(rp)} candidate road points")
gp = os.path.join(WORK, "cable.gpkg"); drv = ogr.GetDriverByName("GPKG")
if os.path.exists(gp):
    drv.DeleteDataSource(gp)
cds = drv.CreateDataSource(gp)
L = cds.CreateLayer("landings", sp, ogr.wkbPoint)
for n, t in (("unit_id", ogr.OFTInteger), ("landing_id", ogr.OFTInteger), ("elev", ogr.OFTReal), ("corridors_ok", ogr.OFTInteger), ("coverage_pct", ogr.OFTReal)):
    L.CreateField(ogr.FieldDefn(n, t))
C = cds.CreateLayer("corridors", sp, ogr.wkbLineString)
for n, t in (("unit_id", ogr.OFTInteger), ("landing_id", ogr.OFTInteger), ("bearing", ogr.OFTInteger), ("span_ft", ogr.OFTReal), ("deflection_pct", ogr.OFTReal), ("min_clear_ft", ogr.OFTReal), ("feasible", ogr.OFTInteger), ("feasible_70ft", ogr.OFTInteger), ("downhill", ogr.OFTInteger), ("max_slope_pct", ogr.OFTReal), ("span_class", ogr.OFTString)):
    C.CreateField(ogr.FieldDefn(n, t))

summary = []
all_corr = []
for attrs, g in unit_geoms():
    uid = attrs["unit_id"]; env = g.GetEnvelope(); ub = g.Buffer(LANDING_REACH)
    lands = [(x, y) for x, y in rp if env[0] - LANDING_REACH <= x <= env[1] + LANDING_REACH and env[2] - LANDING_REACH <= y <= env[3] + LANDING_REACH]
    lands = [(x, y) for x, y in lands if ub.Contains(ogr.CreateGeometryFromWkt(f"POINT ({x} {y})"))]
    if not lands:                                   # no road within reach: use the nearest road points up to FALLBACK_REACH
        cands = sorted(((g.Distance(ogr.CreateGeometryFromWkt(f"POINT ({x} {y})")), (x, y)) for x, y in rp if env[0] - FALLBACK_REACH <= x <= env[1] + FALLBACK_REACH and env[2] - FALLBACK_REACH <= y <= env[3] + FALLBACK_REACH))
        lands = [p for d, p in cands if d <= FALLBACK_REACH][:6]
    corr = []; per_landing = {}
    step = BEARING_STEP if attrs["method"] == "Cable" else BEARING_STEP * 2      # tractor units are a coarser check
    if attrs["method"] != "Cable" and len(lands) > 12:                         # cap landings on big road-side tractor units
        lands = lands[:: int(np.ceil(len(lands) / 12))]
    for li, (x0, y0) in enumerate(lands, 1):
        ok = 0; cov = []
        for b in range(0, 360, step):
            th = cast_tailhold(g, x0, y0, b)
            if not th:
                continue
            x1, y1, inside = th
            r = analyse_corridor(x0, y0, x1, y1, TOWER)
            if not r:
                continue
            r70 = analyse_corridor(x0, y0, x1, y1, TOWER_ALT)
            r.update(unit_id=uid, landing_id=li, bearing=b, x0=x0, y0=y0, x1=x1, y1=y1, feasible_70=bool(r70 and r70["feasible"]))
            corr.append(r); ok += r["feasible"]
            f = ogr.Feature(C.GetLayerDefn()); ln = ogr.Geometry(ogr.wkbLineString); ln.AddPoint_2D(x0, y0); ln.AddPoint_2D(x1, y1); f.SetGeometry(ln)
            for k, v in (("unit_id", uid), ("landing_id", li), ("bearing", b), ("span_ft", round(r["span"])), ("deflection_pct", round(r["deflection"] * 100, 1)), ("min_clear_ft", round(r["min_clear"], 1)), ("feasible", int(r["feasible"])), ("feasible_70ft", int(r["feasible_70"])), ("downhill", int(r["downhill"])), ("max_slope_pct", round(r["max_slope"], 1)), ("span_class", r["span_class"])):
                f.SetField(k, v)
            C.CreateFeature(f)
        # coverage from this landing
        covg = None
        for r in corr:
            if r["landing_id"] == li and r["feasible"]:
                ln = ogr.Geometry(ogr.wkbLineString); ln.AddPoint_2D(r["x0"], r["y0"]); ln.AddPoint_2D(r["x1"], r["y1"]); bf = ln.Buffer(LATERAL)
                covg = bf if covg is None else covg.Union(bf)
        cpct = (covg.Intersection(g).GetArea() / g.GetArea() * 100) if covg is not None else 0.0
        per_landing[li] = (ok, cpct, covg)
        f = ogr.Feature(L.GetLayerDefn()); f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({x0} {y0})"))
        for k, v in (("unit_id", uid), ("landing_id", li), ("elev", round(float(elev_at([x0], [y0])[0]), 1)), ("corridors_ok", ok), ("coverage_pct", round(cpct, 1))):
            f.SetField(k, v)
        L.CreateFeature(f)
    all_corr += corr
    feas = [r for r in corr if r["feasible"]]
    # greedy landing selection for total coverage
    chosen = []; union = None; remaining = dict(per_landing)
    for _ in range(4):
        best = None
        for li, (ok, cpct, covg) in remaining.items():
            if covg is None:
                continue
            gain = (covg if union is None else covg.Union(union)).Intersection(g).GetArea()
            if best is None or gain > best[1]:
                best = (li, gain, covg)
        if not best or (union is not None and best[1] - union.Intersection(g).GetArea() < g.GetArea() * 0.03):
            break
        chosen.append(best[0]); union = best[2] if union is None else union.Union(best[2]); remaining.pop(best[0])
    coverage = (union.Intersection(g).GetArea() / g.GetArea() * 100) if union is not None else 0.0
    mean_defl = float(np.mean([r["deflection"] for r in feas]) * 100) if feas else 0.0
    downhill_share = float(np.mean([r["downhill"] for r in feas]) * 100) if feas else 0.0
    max_span = max((r["span"] for r in feas), default=0.0)
    span_class = next(lbl for lim, lbl in SPAN_CLASSES if max_span <= lim) if feas else "No feasible corridor"
    score = 0
    score += 0 if coverage >= 85 else (1 if coverage >= 60 else 2)
    score += 0 if mean_defl >= 9 else (1 if mean_defl >= 7 else 2)
    score += 0 if attrs["slope_mean"] <= 50 else (1 if attrs["slope_mean"] <= 65 else 2)
    score += 1 if downhill_share > 50 else 0
    difficulty = ["Standard", "Standard", "Moderate", "Moderate", "High", "High", "High", "High"][min(score, 7)]
    row = dict(unit_id=uid, method=attrs["method"], acres=round(attrs["acres"], 1), slope_mean=round(attrs["slope_mean"], 1), landings=len(lands), landings_used=len(chosen),
               corridors=len(corr), corridors_feasible=len(feas), corridors_feasible_70ft=sum(r["feasible_70"] for r in corr), coverage_pct=round(coverage, 1),
               mean_deflection_pct=round(mean_defl, 1), downhill_share_pct=round(downhill_share, 1), max_feasible_span_ft=round(max_span), equipment=span_class,
               difficulty=difficulty, chosen_landings=" ".join(map(str, chosen)))
    summary.append(row); print(f"unit {uid} {attrs['method']:13s} {attrs['acres']:6.1f} ac | landings {len(lands):2d} | corridors {len(corr):4d} feasible {len(feas):4d} | coverage {coverage:5.1f} % | {span_class} | {difficulty}", flush=True)

    # profiles, route tables, corridor maps and the sale-level figures are drawn by 04b_cable_figures.py from cable.gpkg
cds = None

with open(os.path.join(OUT, "unit_summary.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)

print("done:", len(summary), "units,", len(all_corr), "corridors")
