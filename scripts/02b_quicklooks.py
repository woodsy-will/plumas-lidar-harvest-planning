"""02b_quicklooks.py - color quicklooks of the terrain and canopy products with title, legend, scale bar and north arrow.

Reads the GeoTIFFs in data/work (downsampled 4x for speed), draws each with a color ramp or class legend in the
Okabe-Ito palette, overlays the unit outlines, and writes output/quicklooks/<product>.png at 200 dpi.
Run: python-qgis-ltr.bat scripts/02b_quicklooks.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from osgeo import gdal, ogr

gdal.UseExceptions(); ogr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK, OUT = os.path.join(ROOT, "data", "work"), os.path.join(ROOT, "output", "quicklooks")
os.makedirs(OUT, exist_ok=True)
STEP = 4; DPI = 200
SOURCE = "USGS 3DEP CA_NoCAL_Wildfires_PlumasNF 2018 (QL1), 3 ft cells, CA State Plane Zone 2 US ft. Demonstration from public data; not a Forest Service proposal."


def read(name):
    ds = gdal.Open(os.path.join(WORK, name)); b = ds.GetRasterBand(1); a = b.ReadAsArray()[::STEP, ::STEP].astype("float32"); nd = b.GetNoDataValue()
    gt = ds.GetGeoTransform(); ext = [gt[0], gt[0] + gt[1] * ds.RasterXSize, gt[3] + gt[5] * ds.RasterYSize, gt[3]]
    return np.where(a == nd, np.nan, a) if nd is not None else a, ext


hill, ext = read("hillshade.tif"); hill = np.where(hill == 0, np.nan, hill)
rings = []
pds = ogr.Open(os.path.join(WORK, "planning.gpkg")); punits = pds.GetLayerByName("units")
for f in punits:
    g = f.GetGeometryRef()
    for poly in ([g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryName() == "MULTIPOLYGON" else [g]):
        r = poly.GetGeometryRef(0); rings.append(([r.GetPoint_2D(i)[0] for i in range(r.GetPointCount())], [r.GetPoint_2D(i)[1] for i in range(r.GetPointCount())]))


def frame(title):
    fig, ax = plt.subplots(figsize=(9, 9.6)); ax.set_title(title, fontsize=11, loc="left")
    ax.imshow(hill, cmap="gray", extent=ext, vmin=0, vmax=255)
    return fig, ax


def finish(fig, ax, name, note=""):
    for xs, ys in rings:
        ax.plot(xs, ys, color="k", lw=0.6)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_xticks([]); ax.set_yticks([])
    # scale bar: one mile, and a north arrow
    x0 = ext[0] + (ext[1] - ext[0]) * 0.04; y0 = ext[2] + (ext[3] - ext[2]) * 0.04
    ax.plot([x0, x0 + 5280], [y0, y0], color="k", lw=3); ax.plot([x0, x0 + 2640], [y0, y0], color="w", lw=1.5); ax.text(x0 + 2640, y0 + 250, "1 mile", ha="center", fontsize=9)
    ax.annotate("N", xy=(ext[1] - (ext[1] - ext[0]) * 0.05, ext[3] - (ext[3] - ext[2]) * 0.03), xytext=(ext[1] - (ext[1] - ext[0]) * 0.05, ext[3] - (ext[3] - ext[2]) * 0.11), ha="center", fontsize=12, fontweight="bold", arrowprops=dict(arrowstyle="-|>", lw=2, color="k"))
    import textwrap
    fig.text(0.02, 0.008, "\n".join(textwrap.wrap(SOURCE + (" " + note if note else ""), 150)), fontsize=7, color="#333", va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(os.path.join(OUT, name), dpi=DPI); plt.close(fig); print(" ", name)


for old in ("hillshade.png", "dtm_3ft.png", "chm_3ft.png", "slope_pct.png", "yarding_class.png"):
    if os.path.exists(os.path.join(OUT, old)):
        os.remove(os.path.join(OUT, old))
for aux in [f for f in os.listdir(OUT) if f.endswith(".aux.xml")]:
    os.remove(os.path.join(OUT, aux))

fig, ax = frame("Hillshade from the LiDAR ground model (azimuth 315, altitude 45) with demonstration unit outlines")
finish(fig, ax, "hillshade.png")

dtm, _ = read("dtm_3ft.tif")
fig, ax = frame("Digital terrain model, ft above sea level (NAVD88)")
im = ax.imshow(dtm, cmap="terrain", extent=ext, alpha=0.65); fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01, label="elevation, ft")
finish(fig, ax, "dtm_3ft.png")

chm, _ = read("chm_3ft.tif")
fig, ax = frame("Canopy height model, ft (highest return above ground, 3 ft cells)")
im = ax.imshow(np.clip(chm, 0, 150), cmap="viridis", extent=ext, alpha=0.85, vmin=0, vmax=150); fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01, label="canopy height, ft (clipped at 150)")
finish(fig, ax, "chm_3ft.png")

slope, _ = read("slope_plan_pct.tif")
okabe = ListedColormap(["#009E73", "#F0E442", "#D55E00", "#7a2a00"]); norm = BoundaryNorm([0, 35, 50, 100, 400], okabe.N)
fig, ax = frame("Planning slope, percent (15 ft smoothed DTM, averaged over 99 ft) in the yarding-system classes")
ax.imshow(slope, cmap=okabe, norm=norm, extent=ext, alpha=0.6)
ax.legend(handles=[Patch(color=c, label=l) for c, l in (("#009E73", "0 to 35 %: ground-based"), ("#F0E442", "35 to 50 %: marginal"), ("#D55E00", "50 to 100 %: cable"), ("#7a2a00", "over 100 %: not operable"))], loc="lower right", fontsize=9, framealpha=0.9)
finish(fig, ax, "slope_plan_pct.png", "The raw 3 ft slope under this canopy averages 87 % (interpolation noise) and is not used for planning.")

ycls, _ = read("yarding_class.tif")
fig, ax = frame("Yarding class from planning slope: 1 ground-based (35 % and under), 2 marginal (35 to 50 %), 3 cable (over 50 %)")
ax.imshow(ycls, cmap=ListedColormap(["#009E73", "#F0E442", "#D55E00"]), norm=BoundaryNorm([0.5, 1.5, 2.5, 3.5], 3), extent=ext, alpha=0.6)
ax.legend(handles=[Patch(color=c, label=l) for c, l in (("#009E73", "Ground-based"), ("#F0E442", "Marginal"), ("#D55E00", "Cable"))], loc="lower right", fontsize=9, framealpha=0.9)
finish(fig, ax, "yarding_class.png")

cover, _ = read("canopy_cover_66ft.tif")
fig, ax = frame("Canopy cover, percent of 3 ft cells above 6.5 ft in a 66 ft window")
im = ax.imshow(cover * 100, cmap="Greens", extent=ext, alpha=0.8, vmin=0, vmax=100); fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01, label="canopy cover, %")
finish(fig, ax, "canopy_cover_66ft.png")

dom, _ = read("dom_height_66ft.tif")
fig, ax = frame("Dominant height, ft (95th percentile of the canopy height model in a 66 ft window)")
im = ax.imshow(np.clip(dom, 0, 150), cmap="viridis", extent=ext, alpha=0.85, vmin=0, vmax=150); fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01, label="dominant height, ft")
finish(fig, ax, "dom_height_66ft.png")
print("quicklooks written to", OUT)
