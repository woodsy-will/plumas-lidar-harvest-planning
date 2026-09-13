"""04b_cable_figures.py - cable-yarding figures and route tables from the saved corridor analysis.

Reads data/work/cable.gpkg and output/cable/unit_summary.csv (written by 04_cable_analysis.py) and rebuilds the
figure set without re-running the corridor casting:
  Unit_<id>_profiles.png     highest-payload feasible corridor from each selected landing (up to 6 distinct settings),
                             ground, chord, loaded skyline, mid-span deflection, governing point and minimum clearance annotated
  Unit_<id>_routes.png       route table: landing, bearing, span, chord slope, available and loaded deflection, governing
                             distance, clearance, yarding direction, system class, feasibility, payload
  Fig5_equipment_matrix.png  yarding distance vs chord slope for every feasible corridor with system
                             envelopes (small yarder, medium, long-span, intermediate support)
  Fig6_yarding_direction.png uphill / downhill share by unit; downhill capability is a third to a half of
                             uphill per the Forest Service Cable Logging Systems guide
  Unit_<id>_corridor_map.png every corridor cast over the hillshade, feasible in blue, with the selected landings
  Fig1 to Fig4               slope by unit, deflection histogram, equipment class, difficulty
  Fig7_payload.png           allowable load at the governing loaded deflection vs span for every feasible corridor, 7/8 in
                             extra-improved plow-steel skyline at safe working load (rigid-link statics after Lysons and
                             Mann 1967, PNW-39), with loaded-deflection reference curves
Payload uses the LOADED deflection written by 04 (loaded_deflection_pct: PNW-39 chain clearance with 10 ft for carriage
and load, governed anywhere along the profile), not the chord-to-ground height at mid-span. Corridors with loaded
deflection under 3 % get payload 0 and are left out of the best/max figures; the best corridor per unit and per landing
is the one with the largest payload.
Colors follow the Okabe-Ito color-blind-safe palette; figures are written at 300 dpi (corridor maps 200 dpi).
Also appends EYD (external yarding distance) and AYD (average yarding distance, EYD x 0.667 for a
fan-shaped setting) to unit_summary.csv, plus max_payload_lb and payload_at_best_lb from the payload estimate.
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
MIN_LOADED_DEFLECTION = 3.0; CLEAR_LOAD = 10.0     # percent of span below which no payload is credited; ft clearance used by 04 for the loaded line
PAYLOAD_LABEL = f"allowable load at the governing loaded deflection (PNW-39 chain clearance, {CLEAR_LOAD:.0f} ft)"
# Skyline for the payload estimate: 7/8 in extra-improved plow steel, 6x19 IWRC, 1.42 lb/ft, breaking strength 79.6 kips (Lysons and
# Mann 1967, PNW-39, table 1, p. 24; USFS Cable Logging Systems, table 4-3, p. 25); safe working load = breaking strength / 3 (PNW-39, p. 3)
SKYLINE, CABLE_W, BREAK_LB, SAFETY = "7/8 in EIPS", 1.42, 79600.0, 3.0
SWL = BREAK_LB / SAFETY
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


def payload_lb(span, defl_pct, chord_slope):
    """Allowable load (carriage plus logs), lb, for a standing skyline of horizontal span `span` ft, LOADED mid-span deflection
    `defl_pct` percent of span and chord slope `chord_slope` (rise over span; sign ignored, the upper end governs).
    PNW-39 single-span worksheet: upper-end tension due to cable weight is subtracted from the safe working load and the remainder
    is divided by the upper-end tension per pound of load (carriage clamped to the skyline, the higher-tension case). Both tensions
    come from rigid-link statics: two straight links from the supports to the load, each carrying half the cable weight (taken
    along the chord) at its midpoint. Against the handbook: table 4 (load) within about 0.4 % at 2 to 20 % deflection; table 2
    (cable weight) within 1 % only to about 7 % deflection, running about 4 % low at 10 % and about 15 % low at 30 %, which
    barely moves the payload because the cable-weight tension is small against the 26.5 kip working load. `defl_pct` must be
    the loaded deflection from the PNW-39 chain clearance (loaded_deflection_pct written by 04_cable_analysis.py), not the
    chord-to-ground height at mid-span. No catenary, no carriage weight, single span only."""
    d, g = defl_pct / 100.0, abs(chord_slope)
    if d <= 0:
        return 0.0
    wc = CABLE_W * span * math.hypot(1.0, g)                                        # cable weight along the chord, lb
    h_w = wc / (8 * d); t_w = math.hypot(h_w, (g + 2 * d) * h_w + wc / 4)            # upper-end tension from cable weight, lb
    h_p = 1 / (4 * d); t_p = math.hypot(h_p, (g + 2 * d) * h_p)                      # upper-end tension per lb of load
    return max(0.0, (SWL - t_w) / t_p)


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
                                                      ldefl=f["loaded_deflection_pct"], govern_x=f["govern_x_ft"], payload_ok=bool(f["payload_ok"]),
                                                      feasible=bool(f["feasible"]), feasible70=bool(f["feasible_70ft"]), downhill=bool(f["downhill"]), max_slope=f["max_slope_pct"], cls=f["span_class"], x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1]))
print(len(summary), "units;", sum(len(v) for v in corridors.values()), "corridors")
all_c = [c for v in corridors.values() for c in v]                                 # chord slope tower top to anchor, then payload
z_land = elev_at([c["x0"] for c in all_c], [c["y0"] for c in all_c]); z_tail = elev_at([c["x1"] for c in all_c], [c["y1"] for c in all_c])
for c, za, zb in zip(all_c, z_land, z_tail):
    c["chord_slope"] = ((zb + ANCHOR) - (za + TOWER)) / c["span"]
    # payload from the LOADED deflection (PNW-39 chain clearance); below MIN_LOADED_DEFLECTION the corridor is credited with no load
    c["payload"] = (payload_lb(c["span"], c["ldefl"], c["chord_slope"]) if c["payload_ok"] else 0.0) if c["feasible"] else None   # payload_ok from 04, the unrounded 3 % test, so counts match the layer


def by_payload(c):
    """Sort key for the best corridor: largest payload, then largest loaded deflection, then available deflection."""
    return (c["payload"] or 0.0, c["ldefl"], c["defl"])

all_feas = []
for row in summary:
    uid = int(row["unit_id"]); cs = corridors.get(uid, [])
    chosen = [int(v) for v in row["chosen_landings"].split()] if row["chosen_landings"] else []
    feas = [c for c in cs if c["feasible"]]; all_feas += [(c, row["method"]) for c in feas]
    eyd = max((c["span"] for c in feas), default=0.0); row["eyd_ft"] = round(eyd); row["ayd_ft"] = round(eyd * 0.667)
    row["uphill_share_pct"] = round(100 - float(row["downhill_share_pct"]), 1) if feas else 0.0
    loaded = [c for c in feas if c["payload"] > 0]                                  # feasible corridors that carry a load (loaded deflection >= 3 %)
    row["corridors_payload_ok"] = len(loaded)
    row["max_payload_lb"] = round(max(c["payload"] for c in loaded)) if loaded else ""
    best_sel = max((c for c in loaded if c["landing"] in chosen), key=by_payload, default=None)   # best = largest payload, not deflection
    row["payload_at_best_lb"] = round(best_sel["payload"]) if best_sel else ""
    # best corridor per selected landing (then per other landing) for distinct settings
    order = chosen + sorted({c["landing"] for c in feas} - set(chosen))
    picks = []
    for li in order:
        best = max((c for c in feas if c["landing"] == li), key=by_payload, default=None)
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
            if c["feasible"] and c["ldefl"] > 0:                       # loaded skyline: parabola at the governing loaded deflection, clearing the ground by CLEAR_LOAD ft
                u = d / d[-1]; ax.plot(d, chord - 4 * (c["ldefl"] / 100.0) * d[-1] * u * (1 - u), color=BLUE, lw=1.0, ls="--", label=f"loaded skyline, {c['ldefl']:.1f} % loaded deflection")
                ig = int(np.argmin(np.abs(d - c["govern_x"]))); ax.plot(d[ig], z[ig], "^", color=BLUE, ms=6)
                ax.text(d[ig], z[ig] + 4, f"governs at {c['govern_x']:.0f} ft", fontsize=7, ha="center", color=BLUE)
            ax.plot([0, 0], [z[0], z[0] + TOWER], color=BLUE, lw=3); ax.plot([d[-1], d[-1]], [z[-1], z[-1] + ANCHOR], color="#333", lw=3)
            ax.annotate("", (d[mid], z[mid]), (d[mid], chord[mid]), arrowprops=dict(arrowstyle="<->", color=VERMILLION, lw=1.2))
            ax.text(d[mid] + 8, (z[mid] + chord[mid]) / 2, f"{c['defl']:.1f} % available deflection", color=VERMILLION, fontsize=8, va="center")
            imin = int(np.argmin(clr[1:-1])) + 1 if len(clr) > 2 else 0
            ax.plot(d[imin], z[imin], "v", color=VERMILLION, ms=6); ax.text(d[imin], z[imin] - 12, f"min clearance {c['clear']:.0f} ft", fontsize=7.5, ha="center", color=VERMILLION)
            grade = (z[-1] - z[0]) / d[-1] * 100
            ax.set_title(f"Unit {uid}  landing {c['landing']}  bearing {c['bearing']:03d}  span {c['span']:.0f} ft  chord slope {grade:+.0f} %  "
                         f"{'downhill to landing' if c['downhill'] else 'uphill to landing'}  {c['cls']}  {'FEASIBLE' if c['feasible'] else 'not feasible'}", fontsize=9)
            ax.set_ylabel("ft"); ax.grid(alpha=0.3); ax.text(2, z[0] + TOWER + 4, "landing / tower", fontsize=7, color=BLUE); ax.text(d[-1], z[-1] + ANCHOR + 4, "tailhold", fontsize=7, ha="right", color="#333")
            if c["payload"] is not None:
                ptxt = (f"{PAYLOAD_LABEL}: {c['payload']:,.0f} lb, carriage plus logs" if c["payload"] > 0
                        else f"loaded deflection {c['ldefl']:.1f} % is under the {MIN_LOADED_DEFLECTION:.0f} % minimum: no payload credited")
                ax.text(0.01, 0.05, f"{SKYLINE} skyline at SWL {SWL / 1000:.1f} kips: {ptxt}",
                        transform=ax.transAxes, ha="left", va="bottom", fontsize=7.5, color=BLUE, bbox=dict(fc="white", ec="none", alpha=0.8, pad=1.5))
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
        best = max((c for c in feas if c["landing"] == li), key=by_payload, default=None)
        if best:
            rows.append(best)
    for c in sorted(feas, key=by_payload, reverse=True):
        if len(rows) >= 12:
            break
        if all(not (r["landing"] == c["landing"] and min(abs(r["bearing"] - c["bearing"]), 360 - abs(r["bearing"] - c["bearing"])) < 30) for r in rows):
            rows.append(c)
    rows = rows[:12]
    title = f"Unit {uid} ({row['method']}, {float(row['acres']):.0f} ac): best feasible routes  |  EYD {row['eyd_ft']} ft, AYD {row['ayd_ft']} ft  |  coverage {row['coverage_pct']} %  |  {row['equipment']}  |  {row['difficulty']}"
    if rows:
        cells = [[f"L{c['landing']}-{c['bearing']:03d}", f"{c['span']:.0f}", f"{((elev_at([c['x1']],[c['y1']])[0]-elev_at([c['x0']],[c['y0']])[0])/c['span']*100):+.0f} %", f"{c['defl']:.1f} %",
                  f"{c['ldefl']:.1f} %", f"{c['govern_x']:.0f}", f"{c['clear']:.0f}",
                  "downhill" if c["downhill"] else "uphill", c["cls"], "70 ft only" if (c["feasible70"] and not c["feasible"]) else "50 ft",
                  ("none" if c["payload"] == 0 else f"{c['payload']:,.0f}") if c["payload"] is not None else "n/a"] for c in rows]
        fig, ax = plt.subplots(figsize=(12.5, 0.35 * len(cells) + 2.1)); ax.axis("off")
        tb = ax.table(cellText=cells, colLabels=["Route", "Span, ft", "Chord slope", "Avail. deflection", "Loaded deflection", "Governs at, ft", "Min clearance, ft", "Yarding", "System", "Tower", "Payload, lb"], loc="center", cellLoc="center")
        tb.auto_set_font_size(False); tb.set_fontsize(8); tb.scale(1, 1.25)
        for (r, cidx), cell in tb.get_celld().items():
            if r == 0:
                cell.set_facecolor("#2f4a37"); cell.set_text_props(color="white", weight="bold")
            elif cidx == 3:
                v = float(cells[r - 1][3].rstrip(" %")); cell.set_facecolor("#a6d8f0" if v >= 9 else "#f0e442" if v >= 7 else "#f4b183")
            elif cidx == 4:
                v = float(cells[r - 1][4].rstrip(" %")); cell.set_facecolor("#a6d8f0" if v >= 6 else "#f0e442" if v >= MIN_LOADED_DEFLECTION else "#f4b183")
        ax.set_title(title, fontsize=9)
        fig.text(0.5, 0.05, "Route = landing number and bearing. Span is horizontal. Available deflection = chord-to-ground height at mid-span as a percent of horizontal span (shading: blue 9 % and over, yellow 7 to 9 %, orange under 7 %; planning minimum 6 %).\n"
                          f"Loaded deflection = largest mid-span sag of the loaded line (parabola below the chord) that keeps {CLEAR_LOAD:.0f} ft between line and ground everywhere along the profile, PNW-39 chain method; 'Governs at' is the distance from the landing to the point that limits it\n"
                          f"(shading: blue 6 % and over, yellow {MIN_LOADED_DEFLECTION:.0f} to 6 %, orange under {MIN_LOADED_DEFLECTION:.0f} %, no payload credited). Chord slope: negative = tailhold below the landing (uphill yarding).\n"
                          f"Payload: {PAYLOAD_LABEL}, carriage plus logs, for a {SKYLINE} skyline at safe working load {SWL / 1000:.1f} kips (breaking strength {BREAK_LB / 1000:.1f} kips / {SAFETY:.0f}), PNW-39 worksheet with rigid-link statics.\n"
                          "Rows: the highest-payload corridor from each landing, then further routes by payload at least 30 degrees from those listed.", ha="center", va="bottom", fontsize=7.2, color="#333")
        fig.tight_layout(rect=(0, 0.2, 1, 1)); fig.savefig(os.path.join(OUT, f"Unit_{uid}_routes.png"), dpi=DPI); plt.close(fig)
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
# Fig 7: payload vs span for every feasible corridor at its LOADED deflection, with level-chord reference curves at fixed loaded deflections
fig, ax = plt.subplots(figsize=(10, 6))
f7 = [(c, m) for c, m in all_feas if c["payload"] > 0]; n_none = len(all_feas) - len(f7)
ax.scatter([c["span"] for c, m in f7], [c["payload"] for c, m in f7], s=8, c=[BLUE if m == "Cable" else ORANGE for c, m in f7], alpha=0.5)
span7 = np.linspace(200, 3600, 120)
for dpct, ls in ((3, (0, (1, 2))), (6, ":"), (8, "--"), (10, "-")):
    ax.plot(span7, [payload_lb(s, dpct, 0.0) for s in span7], color="k", lw=0.8, ls=ls, label=f"{dpct} % loaded deflection, level chord")
ax.scatter([], [], c=BLUE, s=20, label="cable units"); ax.scatter([], [], c=ORANGE, s=20, label="tractor units checked as if cable")
ax.set_xlim(0, 3600); ax.set_ylim(bottom=0); ax.set_xlabel("feasible corridor span (horizontal), ft"); ax.set_ylabel(f"{PAYLOAD_LABEL}, lb (carriage plus logs)")
ax.set_title(f"Fig 7. Skyline payload estimate for feasible corridors: {SKYLINE} skyline, safe working load {SWL / 1000:.1f} kips (breaking strength {BREAK_LB / 1000:.1f} kips / {SAFETY:.0f})\n"
             f"PNW-39 worksheet with rigid-link statics, cable weight included, at each corridor's LOADED deflection (chain clearance {CLEAR_LOAD:.0f} ft, governed anywhere on the profile),\n"
             f"replacing the earlier chord-to-ground mid-span deflection; {n_none:,} feasible corridors under {MIN_LOADED_DEFLECTION:.0f} % loaded deflection carry no load and are not plotted", fontsize=9.5)
ax.legend(loc="upper right", fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Fig7_payload.png"), dpi=DPI); plt.close(fig)
# Fig 1 to 4: sale-level summaries
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
