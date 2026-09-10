"""04b_cable_figures.py - cable-yarding figures and route tables from the saved corridor analysis.

Reads data/work/cable.gpkg and output/cable/unit_summary.csv (written by 04_cable_analysis.py) and rebuilds the
figure set without re-running the corridor casting:
  Unit_<id>_profiles.png     best feasible corridor from each selected landing (up to 6 distinct settings),
                             ground, chord, mid-span deflection and minimum clearance annotated
  Unit_<id>_routes.png       route table: landing, bearing, span, chord slope, deflection, clearance,
                             yarding direction, system class, feasibility
  Fig5_equipment_matrix.png  yarding distance vs chord slope for every feasible corridor with system
                             envelopes (small yarder, medium, long-span, intermediate support)
  Fig6_yarding_direction.png uphill / downhill share by unit; downhill capability is a third to a half of
                             uphill per the Forest Service Cable Logging Systems guide
  Unit_<id>_corridor_map.png every corridor cast over the hillshade, feasible in blue, with the selected landings
  Fig1 to Fig4               slope by unit, deflection histogram, equipment class, difficulty
Colors follow the Okabe-Ito color-blind-safe palette; figures are written at 300 dpi (corridor maps 200 dpi).
Also appends EYD (external yarding distance) and AYD (average yarding distance, EYD x 0.667 for a
fan-shaped setting) to unit_summary.csv.
Run: python-qgis-ltr.bat scripts/04b_cable_figures.py
"""
import csv
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 9.5, "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8, "axes.grid": True, "grid.alpha": 0.25})
import numpy as np
from osgeo import gdal, ogr
from scipy.ndimage import map_coordinates

gdal.UseExceptions(); ogr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK, OUT = os.path.join(ROOT, "data", "work"), os.path.join(ROOT, "output", "cable")
TOWER, ANCHOR, STEP = 50.0, 10.0, 10.0
SPAN_CLASSES = [(1000, "Small yarder"), (1800, "Medium yarder"), (3000, "Long-span yarder"), (1e9, "Intermediate support needed")]
MIN_DEFLECTION = 6.0; DPI = 300
BLUE, ORANGE, YELLOW, VERMILLION, GREEN, GREY = "#0072B2", "#E69F00", "#F0E442", "#D55E00", "#009E73", "#bbbbbb"
hs_ds = gdal.Open(os.path.join(WORK, "hillshade.tif")); hs = hs_ds.GetRasterBand(1).ReadAsArray(); hgt = hs_ds.GetGeoTransform()
unit_geom = {}
pds = ogr.Open(os.path.join(WORK, "planning.gpkg")); punits = pds.GetLayerByName("units")
for f in punits:
    unit_geom[f["unit_id"]] = f.GetGeometryRef().Clone()

dtm_ds = gdal.Open(os.path.join(WORK, "dtm_3ft.tif")); gt = dtm_ds.GetGeoTransform()
dtm = dtm_ds.GetRasterBand(1).ReadAsArray().astype("float32"); nd = dtm_ds.GetRasterBand(1).GetNoDataValue()
dtm = np.where(dtm == nd, np.nan, dtm); fill = float(np.nanmean(dtm)); dtm_f = np.nan_to_num(dtm, nan=fill)


def elev_at(xs, ys):
    return map_coordinates(dtm_f, [(np.asarray(ys) - gt[3]) / gt[5], (np.asarray(xs) - gt[0]) / gt[1]], order=1, mode="nearest")


def profile(x0, y0, x1, y1, tower=TOWER):
    span = math.hypot(x1 - x0, y1 - y0); n = int(span // STEP) + 1
    xs, ys, d = np.linspace(x0, x1, n), np.linspace(y0, y1, n), np.linspace(0, span, n); z = elev_at(xs, ys)
    chord = (z[0] + tower) + ((z[-1] + ANCHOR) - (z[0] + tower)) * d / span
    return d, z, chord, chord - z


summary = list(csv.DictReader(open(os.path.join(OUT, "unit_summary.csv"))))
ds = ogr.Open(os.path.join(WORK, "cable.gpkg"))
corr_l = ds.GetLayerByName("corridors"); land_l = ds.GetLayerByName("landings")
landings = {}
for f in land_l:
    g = f.GetGeometryRef(); landings[(f["unit_id"], f["landing_id"])] = (g.GetX(), g.GetY(), f["elev"], f["coverage_pct"], f["corridors_ok"])
corridors = {}
for f in corr_l:
    g = f.GetGeometryRef(); p0, p1 = g.GetPoint_2D(0), g.GetPoint_2D(g.GetPointCount() - 1)
    corridors.setdefault(f["unit_id"], []).append(dict(landing=f["landing_id"], bearing=f["bearing"], span=f["span_ft"], defl=f["deflection_pct"], clear=f["min_clear_ft"],
                                                      feasible=bool(f["feasible"]), feasible70=bool(f["feasible_70ft"]), downhill=bool(f["downhill"]), max_slope=f["max_slope_pct"], cls=f["span_class"], x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1]))
print(len(summary), "units;", sum(len(v) for v in corridors.values()), "corridors")

all_feas = []
for row in summary:
    uid = int(row["unit_id"]); cs = corridors.get(uid, [])
    chosen = [int(v) for v in row["chosen_landings"].split()] if row["chosen_landings"] else []
    feas = [c for c in cs if c["feasible"]]; all_feas += [(c, row["method"]) for c in feas]
    eyd = max((c["span"] for c in feas), default=0.0); row["eyd_ft"] = round(eyd); row["ayd_ft"] = round(eyd * 0.667)
    row["uphill_share_pct"] = round(100 - float(row["downhill_share_pct"]), 1) if feas else 0.0
    # best corridor per selected landing (then per other landing) for distinct settings
    order = chosen + sorted({c["landing"] for c in feas} - set(chosen))
    picks = []
    for li in order:
        best = max((c for c in feas if c["landing"] == li), key=lambda c: c["defl"], default=None)
        if best:
            picks.append(best)
        if len(picks) == 6:
            break
    if not picks:
        picks = sorted(cs, key=lambda c: -c["defl"])[:3]
    if picks:
        profs = [profile(c["x0"], c["y0"], c["x1"], c["y1"]) for c in picks]
        heights = [min(4.2, max(1.6, 9.6 * (float(pz[1].max() + TOWER + 30 - pz[1].min()) / max(1.0, pz[0][-1])))) for pz in profs]   # true-scale panel heights
        fig, axes = plt.subplots(len(picks), 1, figsize=(11, sum(heights) + 0.9), squeeze=False, gridspec_kw={"height_ratios": heights})
        for ax, c, (d, z, chord, clr) in zip(axes[:, 0], picks, profs):
            mid = len(d) // 2; ax.set_aspect("equal", adjustable="box")
            ax.fill_between(d, z.min() - 25, z, color="#c8b48c", alpha=0.6); ax.plot(d, z, color="#5a4a2a", lw=1.2, label="ground")
            ax.plot(d, chord, color=BLUE, lw=1.4, label=f"chord, {TOWER:.0f} ft tower, {ANCHOR:.0f} ft anchor")
            ax.plot([0, 0], [z[0], z[0] + TOWER], color=BLUE, lw=3); ax.plot([d[-1], d[-1]], [z[-1], z[-1] + ANCHOR], color="#333", lw=3)
            ax.annotate("", (d[mid], z[mid]), (d[mid], chord[mid]), arrowprops=dict(arrowstyle="<->", color=VERMILLION, lw=1.2))
            ax.text(d[mid] + 8, (z[mid] + chord[mid]) / 2, f"{c['defl']:.1f} % available deflection", color=VERMILLION, fontsize=8, va="center")
            imin = int(np.argmin(clr[1:-1])) + 1 if len(clr) > 2 else 0
            ax.plot(d[imin], z[imin], "v", color=VERMILLION, ms=6); ax.text(d[imin], z[imin] - 12, f"min clearance {c['clear']:.0f} ft", fontsize=7.5, ha="center", color=VERMILLION)
            grade = (z[-1] - z[0]) / d[-1] * 100
            ax.set_title(f"Unit {uid}  landing {c['landing']}  bearing {c['bearing']:03d}  span {c['span']:.0f} ft  chord slope {grade:+.0f} %  "
                         f"{'downhill to landing' if c['downhill'] else 'uphill to landing'}  {c['cls']}  {'FEASIBLE' if c['feasible'] else 'not feasible'}", fontsize=9)
            ax.set_ylabel("ft"); ax.grid(alpha=0.3); ax.text(2, z[0] + TOWER + 4, "landing / tower", fontsize=7, color=BLUE); ax.text(d[-1], z[-1] + ANCHOR + 4, "tailhold", fontsize=7, ha="right", color="#333")
        axes[-1, 0].set_xlabel("horizontal distance from landing, ft"); axes[0, 0].legend(loc="upper right", fontsize=8)
        fig.tight_layout(); fig.canvas.draw()
        for ax in axes[:, 0]:                                     # profiles are drawn at true scale; state it, as profile drawings require
            bb = ax.get_window_extent(); xr = ax.get_xlim(); yr = ax.get_ylim(); ve = ((xr[1] - xr[0]) / bb.width) / ((yr[1] - yr[0]) / bb.height)
            ax.text(0.995, 0.04, f"no vertical exaggeration (V.E. {ve:.2f}x)", transform=ax.transAxes, ha="right", fontsize=7, color="#555")
        fig.savefig(os.path.join(OUT, f"Unit_{uid}_profiles.png"), dpi=DPI); plt.close(fig)
    # route table figure: distinct settings - the best corridor from each landing, then further corridors at least
    # 30 degrees from any already listed for that landing, up to 12 rows
    rows = []
    for li in order:
        best = max((c for c in feas if c["landing"] == li), key=lambda c: c["defl"], default=None)
        if best:
            rows.append(best)
    for c in sorted(feas, key=lambda c: -c["defl"]):
        if len(rows) >= 12:
            break
        if all(not (r["landing"] == c["landing"] and min(abs(r["bearing"] - c["bearing"]), 360 - abs(r["bearing"] - c["bearing"])) < 30) for r in rows):
            rows.append(c)
    rows = rows[:12]
    title = f"Unit {uid} ({row['method']}, {float(row['acres']):.0f} ac): best feasible routes  |  EYD {row['eyd_ft']} ft, AYD {row['ayd_ft']} ft  |  coverage {row['coverage_pct']} %  |  {row['equipment']}  |  {row['difficulty']}"
    if rows:
        cells = [[f"L{c['landing']}-{c['bearing']:03d}", f"{c['span']:.0f}", f"{((elev_at([c['x1']],[c['y1']])[0]-elev_at([c['x0']],[c['y0']])[0])/c['span']*100):+.0f} %", f"{c['defl']:.1f} %", f"{c['clear']:.0f}",
                  "downhill" if c["downhill"] else "uphill", c["cls"], "70 ft only" if (c["feasible70"] and not c["feasible"]) else "50 ft"] for c in rows]
        fig, ax = plt.subplots(figsize=(10, 0.35 * len(cells) + 1.4)); ax.axis("off")
        tb = ax.table(cellText=cells, colLabels=["Route", "Span, ft", "Chord slope", "Avail. deflection", "Min clearance, ft", "Yarding", "System", "Tower"], loc="center", cellLoc="center")
        tb.auto_set_font_size(False); tb.set_fontsize(8); tb.scale(1, 1.25)
        for (r, cidx), cell in tb.get_celld().items():
            if r == 0:
                cell.set_facecolor("#2f4a37"); cell.set_text_props(color="white", weight="bold")
            elif cidx == 3:
                v = float(cells[r - 1][3].rstrip(" %")); cell.set_facecolor("#a6d8f0" if v >= 9 else "#f0e442" if v >= 7 else "#f4b183")
        ax.set_title(title, fontsize=9)
        fig.text(0.5, 0.05, "Route = landing number and bearing. Span is horizontal. Available deflection = chord-to-ground height at mid-span as a percent of horizontal span. Chord slope: negative = tailhold below the landing (uphill yarding).\nDeflection shading: blue 9 % and over, yellow 7 to 9 %, orange under 7 % (planning minimum 6 %).", ha="center", va="bottom", fontsize=7.5, color="#333")
        fig.tight_layout(rect=(0, 0.1, 1, 1)); fig.savefig(os.path.join(OUT, f"Unit_{uid}_routes.png"), dpi=DPI); plt.close(fig)
    else:                                                     # no feasible route: the sheet says so instead of leaving a gap in the figure set
        fig, ax = plt.subplots(figsize=(10, 1.6)); ax.axis("off"); ax.set_title(title, fontsize=9)
        ax.text(0.5, 0.5, f"No feasible skyline corridor: {int(row['corridors_feasible'])} of {int(row['corridors'])} corridors cast from {int(row['landings'])} candidate landings "
                          "met the 10 ft clearance and 6 % deflection tests.", ha="center", va="center", fontsize=8.5, transform=ax.transAxes)
        fig.tight_layout(); fig.savefig(os.path.join(OUT, f"Unit_{uid}_routes.png"), dpi=DPI); plt.close(fig)
    # corridor map: every corridor cast, feasible in blue, over the hillshade
    if cs:
        g = unit_geom[uid]; env = g.GetEnvelope(); pad = 400
        c0, c1 = int((env[0] - pad - hgt[0]) / hgt[1]), int((env[1] + pad - hgt[0]) / hgt[1]); r0, r1 = int((env[3] + pad - hgt[3]) / hgt[5]), int((env[2] - pad - hgt[3]) / hgt[5])
        c0, c1, r0, r1 = max(c0, 0), min(c1, hs.shape[1]), max(r0, 0), min(r1, hs.shape[0])
        fig, ax = plt.subplots(figsize=(9, 9 * (r1 - r0) / max(1, c1 - c0)))
        ax.imshow(hs[r0:r1, c0:c1], cmap="gray", extent=[hgt[0] + c0 * hgt[1], hgt[0] + c1 * hgt[1], hgt[3] + r1 * hgt[5], hgt[3] + r0 * hgt[5]])
        for c in sorted(cs, key=lambda c: c["feasible"]):
            ax.plot([c["x0"], c["x1"]], [c["y0"], c["y1"]], color=(BLUE if c["feasible"] else GREY), lw=0.5 if c["feasible"] else 0.3, alpha=0.8 if c["feasible"] else 0.35)
        rings = [g.GetGeometryRef(i).GetGeometryRef(0) for i in range(g.GetGeometryCount())] if g.GetGeometryName() == "MULTIPOLYGON" else [g.GetGeometryRef(0)]
        for ring in rings:
            ax.plot([ring.GetPoint_2D(i)[0] for i in range(ring.GetPointCount())], [ring.GetPoint_2D(i)[1] for i in range(ring.GetPointCount())], color="k", lw=1.6)
        for (u, li), (x, y, *_r) in landings.items():
            if u == uid:
                ax.plot(x, y, marker="^", color=(YELLOW if li in chosen else "#f2f2f2"), ms=10 if li in chosen else 5, mec="k")
        ax.set_title(f"Unit {uid} ({row['method']}, {float(row['acres']):.0f} ac): blue = feasible skyline corridor, grey = infeasible; yellow triangles = selected landings; coverage {float(row['coverage_pct']):.0f} %", fontsize=9)
        ax.set_xlabel("State Plane II, ft"); ax.ticklabel_format(useOffset=False, style="plain"); ax.tick_params(labelsize=7)
        fig.tight_layout(); fig.savefig(os.path.join(OUT, f"Unit_{uid}_corridor_map.png"), dpi=200); plt.close(fig)

with open(os.path.join(OUT, "unit_summary.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)

# Fig 5: equipment matrix - span vs chord slope, envelopes by system
fig, ax = plt.subplots(figsize=(10, 6))
for lim, lbl, col in ((1000, "Small yarder, to 1,000 ft", "#dfe9f7"), (1800, "Medium yarder, to 1,800 ft", "#fbe9d0"), (3000, "Long-span yarder, to 3,000 ft", "#f9d6d2"), (3600, "Intermediate support needed, over 3,000 ft", "#e6e6e6")):
    ax.add_patch(plt.Rectangle((0, -100), lim, 200, color=col, alpha=0.5, label=lbl))
xs = [c["span"] for c, m in all_feas]; ys = []
for c, m in all_feas:
    ys.append((elev_at([c["x1"]], [c["y1"]])[0] - elev_at([c["x0"]], [c["y0"]])[0]) / c["span"] * 100)
cols = ["#0072B2" if m == "Cable" else "#E69F00" for c, m in all_feas]
ax.scatter(xs, ys, s=8, c=cols, alpha=0.5)
ax.axhline(0, color="k", lw=0.8)
ax.text(1850, 60, "tailhold above landing: DOWNHILL yarding to the landing\nplan for 1/3 to 1/2 of uphill capability (USFS Cable Logging Systems)", fontsize=8, va="center")
ax.text(1850, -60, "tailhold below landing: UPHILL yarding to the landing", fontsize=8, va="center")
ax.set_xlim(0, 3600); ax.set_ylim(-100, 100); ax.set_xlabel("feasible corridor span (horizontal), ft"); ax.set_ylabel("chord slope, % (tailhold minus landing)")
ax.set_title("Fig 5. Equipment selection matrix: feasible corridors by span and chord slope\n(blue = cable units, orange = tractor units checked as if cable)", fontsize=10); ax.legend(loc="upper right", fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig5_equipment_matrix.png"), dpi=DPI); plt.close(fig)
# Fig 6: yarding direction by unit
fig, ax = plt.subplots(figsize=(10, 5))
f6 = [r for r in summary if int(r["corridors_feasible"]) > 0]                        # shares are undefined where nothing is feasible
ids = [r["unit_id"] for r in f6]; up = [float(r["uphill_share_pct"]) for r in f6]; dn = [float(r["downhill_share_pct"]) for r in f6]
ax.bar(ids, up, color="#0072B2", label="uphill to landing"); ax.bar(ids, dn, bottom=up, color="#E69F00", label="downhill to landing")
ax.set_ylabel("% of feasible corridors"); ax.set_xlabel("unit"); ax.tick_params(axis="x", labelsize=7); ax.legend(fontsize=8); ax.set_title("Fig 6. Yarding direction of feasible corridors by unit (downhill yarding is the safety and capability constraint)\n(units with no feasible corridor omitted)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig6_yarding_direction.png"), dpi=DPI); plt.close(fig)
# Fig 1 to 4: sale-level summaries
all_c = [c for v in corridors.values() for c in v]
fig, ax = plt.subplots(figsize=(9, 5))
ids = [str(r["unit_id"]) for r in summary]; ax.bar(ids, [float(r["slope_mean"]) for r in summary], color=[{"Tractor": ORANGE, "Cable": BLUE, "Hand Thinning": GREEN}[r["method"]] for r in summary])
ax.axhline(35, color="k", ls="--", lw=1); ax.text(0.5, 36, "35 % ground-based limit", fontsize=8); ax.set_ylabel("mean planning slope, %"); ax.set_xlabel("unit"); ax.set_title("Fig 1. Mean slope by unit and assigned system (orange tractor, blue cable)"); ax.tick_params(axis="x", labelsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig1_slope_by_unit.png"), dpi=DPI); plt.close(fig)
fig, ax = plt.subplots(figsize=(9, 5))
ax.hist([c["defl"] for c in all_c], bins=40, color=BLUE, alpha=0.85); ax.axvline(MIN_DEFLECTION, color=VERMILLION, ls="--"); ax.text(MIN_DEFLECTION + 0.2, ax.get_ylim()[1] * 0.9, "6 % planning minimum", color=VERMILLION, fontsize=8)
ax.set_xlabel("available mid-span deflection (chord to ground), % of horizontal span"); ax.set_ylabel("corridors"); ax.set_title("Fig 2. Available mid-span deflection across all corridors cast, 50 ft tower, 10 ft tailhold anchor")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig2_deflection.png"), dpi=DPI); plt.close(fig)
fig, ax = plt.subplots(figsize=(9, 5))
cls = [c for _, c in SPAN_CLASSES]; counts = [sum(1 for c in all_c if c["feasible"] and c["cls"] == k) for k in cls]
ax.bar(cls, counts, color=BLUE); ax.set_ylabel("feasible corridors"); ax.set_title("Fig 3. Equipment class implied by feasible span lengths"); ax.tick_params(axis="x", labelsize=8)
for i, n in enumerate(counts):
    ax.text(i, n, f"{n:,}", ha="center", va="bottom", fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig3_equipment.png"), dpi=DPI); plt.close(fig)
fig, ax = plt.subplots(figsize=(9, 5))
ax.scatter([float(r["coverage_pct"]) for r in summary], [float(r["mean_deflection_pct"]) for r in summary], s=[max(20, float(r["acres"]) * 2) for r in summary], c=[{"Standard": BLUE, "Moderate": YELLOW, "High": VERMILLION}[r["difficulty"]] for r in summary], alpha=0.85, edgecolor="k")
for r in summary:
    ax.annotate(str(r["unit_id"]), (float(r["coverage_pct"]), float(r["mean_deflection_pct"])), fontsize=7, ha="center", va="center")
ax.set_xlabel("unit coverage by feasible corridors, %"); ax.set_ylabel("mean available deflection of feasible corridors, %"); ax.set_title("Fig 4. Yarding difficulty (blue standard, yellow moderate, vermillion high; bubble area = acres)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig4_difficulty.png"), dpi=DPI); plt.close(fig)
print("figures rebuilt for", len(summary), "units")
