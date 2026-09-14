"""02_build_terrain.py - LiDAR terrain and canopy products for the AOI.

Per batch of Entwine node files (PDAL, streaming): reproject EPSG:3857 (the coordinate system of the USGS Entwine
copy the run used; the staged USGS LAZ tiles are EPSG:5070 and take the same path) -> EPSG:2226 (California State
Plane Zone 2, US survey feet, the coordinate system used on Plumas timber sale maps), convert Z from meters to feet,
crop to the AOI, then write
  dtm   ground returns (class 2), IDW, 3 ft cells
  dsm   first returns, max, 3 ft cells
  chm   height above ground of all non-noise returns (hag_dem against the DTM), max, 3 ft cells, capped at 300 ft
Tiles are mosaicked with GDAL, then derived:
  slope_pct, aspect_deg, hillshade, canopy_cover_66ft (share of CHM > 6.5 ft in a 66 ft window),
  dom_height_66ft (95th percentile CHM in a 66 ft window), yarding_class (1 ground-based <= 35 %,
  2 marginal 35-50 %, 3 cable > 50 %, from slope smoothed over a 99 ft window).
Run: python-qgis-ltr.bat scripts/02_build_terrain.py [--max-batches N] [--derivatives-only]
  --derivatives-only skips the PDAL batch stage (about 2 h) and rebuilds the mosaics and every derived product
  from the per-batch rasters already in data/work.
"""
import glob, json, os, subprocess, sys, time
import numpy as np
from osgeo import gdal, ogr, osr
from scipy import ndimage
gdal.UseExceptions(); osr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, WORK = (os.path.join(ROOT, "data", d) for d in ("raw", "work"))
os.makedirs(WORK, exist_ok=True)
PDAL = r"C:\Program Files\QGIS 3.44.12\bin\pdal.exe"
CRS = "EPSG:2226"; CELL = 3.0; M_TO_FT = 3.28083333333

# AOI polygon in the working CRS
aoi = json.load(open(os.path.join(RAW, "aoi.geojson")))
s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
sp = osr.SpatialReference(); sp.ImportFromEPSG(2226); sp.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
aoi_g = ogr.CreateGeometryFromJson(json.dumps([f for f in aoi["features"] if f["properties"]["role"] == "aoi"][0]["geometry"]))
aoi_g.Transform(osr.CoordinateTransformation(s4326, sp)); wkt = aoi_g.ExportToWkt()
e = aoi_g.GetEnvelope(); bounds = ([e[0], e[1]], [e[2], e[3]])
print("AOI extent (ft):", [round(v) for v in e])

def run_pipeline(stages, tag):
    p = os.path.join(WORK, f"_pipe_{tag}.json"); json.dump({"pipeline": stages}, open(p, "w"))
    r = subprocess.run([PDAL, "pipeline", p, "--stream"], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-1500:])

def writer(name, dim="Z", out="max", bounds=None):
    # bounds are mandatory in streaming mode: without them PDAL sizes the raster from the reader's header
    # extent, and an Entwine root node spans the whole 170 km survey.
    w = {"type": "writers.gdal", "filename": name, "resolution": CELL, "output_type": out, "dimension": dim,
         "window_size": 8, "gdaldriver": "GTiff", "gdalopts": "COMPRESS=DEFLATE,PREDICTOR=3,TILED=YES", "nodata": -9999, "data_type": "float32"}
    if bounds:
        w["bounds"] = f"([{bounds[0]},{bounds[1]}],[{bounds[2]},{bounds[3]}])"
    return w


# per-batch raster bounds: the batch cube (EPSG:3857) reprojected to the working CRS, clipped to the AOI, padded, snapped to the grid
s3857 = osr.SpatialReference(); s3857.ImportFromEPSG(3857); s3857.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
merc_to_sp = osr.CoordinateTransformation(s3857, sp)
ept_meta = None
ept_meta_p = os.path.join(WORK, "ept_CA_NoCAL_Wildfires_PlumasNF_B2_2018.json")   # ept.json saved by ept_fetch.py
if os.path.exists(ept_meta_p):
    ept_meta = json.load(open(ept_meta_p))
nodes_list = os.path.join(WORK, "ept_nodes.txt")   # machine-specific absolute paths; kept out of git
if os.path.exists(nodes_list) and ept_meta is None:
    # without the octree bounds every batch would fall back to an AOI-sized raster (slow, and the batch rasters
    # would overlap); fail loudly instead
    raise SystemExit(f"{ept_meta_p} is missing but {nodes_list} exists: re-run scripts/ept_fetch.py (it saves ept.json there) "
                     "or download https://s3-us-west-2.amazonaws.com/usgs-lidar-public/CA_NoCAL_Wildfires_PlumasNF_B2_2018/ept.json to that path")


def batch_bounds(tag):
    if ept_meta is None or tag.startswith("top-"):
        x0, x1, y0, y1 = e[0], e[1], e[2], e[3]
    else:
        d, x, y, z = map(int, tag.split("-")); B = ept_meta["bounds"]; size = (B[3] - B[0]) / (2 ** d)
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for cx, cy in ((B[0] + x * size, B[1] + y * size), (B[0] + (x + 1) * size, B[1] + y * size), (B[0] + (x + 1) * size, B[1] + (y + 1) * size), (B[0] + x * size, B[1] + (y + 1) * size), (B[0] + x * size, B[1] + y * size)):
            ring.AddPoint(cx, cy)
        cube = ogr.Geometry(ogr.wkbPolygon); cube.AddGeometry(ring); cube.Transform(merc_to_sp); ce = cube.GetEnvelope()
        x0, x1, y0, y1 = max(ce[0], e[0]) - 30, min(ce[1], e[1]) + 30, max(ce[2], e[2]) - 30, min(ce[3], e[3]) + 30
    snap = lambda v, up: (np.ceil(v / CELL) if up else np.floor(v / CELL)) * CELL
    return snap(x0, False), snap(x1, True), snap(y0, False), snap(y1, True)

# Inputs: either USGS LAZ tiles in data/raw/laz, or Entwine node files listed in data/work/ept_nodes.txt
# (see ept_fetch.py). Node files are grouped into spatial batches by their depth-8 ancestor so each PDAL run
# covers roughly a 340 m square; PDAL merges multiple readers automatically.
def ancestor(key, depth=8):
    d, x, y, z = map(int, os.path.basename(key)[:-4].split("-"))
    s = 2 ** (d - depth) if d >= depth else 1
    return f"{depth}-{x // s}-{y // s}-{z // s}" if d >= depth else f"top-{os.path.basename(key)[:-4]}"

if os.path.exists(nodes_list):
    batches = {}
    for p in open(nodes_list).read().split("\n"):
        if p.strip(): batches.setdefault(ancestor(p.strip()), []).append(p.strip())
    # Nodes above depth 8 (the coarse octree levels) hold about 0.5 % of the AOI's points spread across the whole
    # area; each would need an AOI-sized raster. They are omitted, which is immaterial at 3 ft cells.
    jobs = sorted((k, v) for k, v in batches.items() if not k.startswith("top-"))
    in_srs = {"type": "readers.las", "override_srs": "EPSG:3857"}     # EPT nodes carry EPSG:3857 in the EPT metadata
    def readers(paths): return [dict(in_srs, filename=p) for p in paths]
else:
    jobs = [(os.path.basename(p)[-14:-4], [p]) for p in sorted(glob.glob(os.path.join(RAW, "laz", "*.laz")))]
    def readers(paths): return list(paths)
print(f"{len(jobs)} batches"); t0 = time.time()
max_batches = int(sys.argv[sys.argv.index("--max-batches") + 1]) if "--max-batches" in sys.argv else None
done_now = 0
if "--derivatives-only" in sys.argv:
    jobs = []; print("--derivatives-only: PDAL batch stage skipped, using the batch rasters in data/work")
for i, (tag, paths) in enumerate(jobs, 1):
    dtm, dsm, chm = (os.path.join(WORK, f"tile_{k}_{tag}.tif") for k in ("dtm", "dsm", "chm"))
    if os.path.exists(chm): continue
    if max_batches is not None and done_now >= max_batches: print("stopping after", done_now, "batches (--max-batches)"); sys.exit(0)
    done_now += 1
    def head(paths=paths):
        return readers(paths) + [{"type": "filters.reprojection", "out_srs": CRS},
                                 {"type": "filters.assign", "value": [f"Z = Z * {M_TO_FT}"]},
                                 {"type": "filters.crop", "polygon": wkt}]
    bb = batch_bounds(tag)
    if bb[1] - bb[0] < CELL * 4 or bb[3] - bb[2] < CELL * 4: continue
    try:
        run_pipeline(head() + [{"type": "filters.range", "limits": "Classification[2:2]"}, writer(dtm, out="idw", bounds=bb)], tag)
    except RuntimeError as ex:
        if "no points" in ex.args[0].lower() or "empty" in ex.args[0].lower(): print(f"  [{i}] {tag}: no points in AOI"); continue
        raise
    if not os.path.exists(dtm): print(f"  [{i}] {tag}: outside AOI"); continue
    run_pipeline(head() + [{"type": "filters.expression", "expression": "Classification != 7 && Classification != 18 && ReturnNumber == 1"}, writer(dsm, bounds=bb)], tag)
    run_pipeline(head() + [{"type": "filters.expression", "expression": "Classification != 7 && Classification != 18"},
                           {"type": "filters.hag_dem", "raster": dtm, "zero_ground": True},
                           {"type": "filters.range", "limits": "HeightAboveGround[-3:300]"},
                           {"type": "filters.assign", "value": ["HeightAboveGround = 0 WHERE HeightAboveGround < 0"]},
                           writer(chm, dim="HeightAboveGround", bounds=bb)], tag)
    if i % 10 == 0 or i == len(jobs): print(f"  [{i}/{len(jobs)}] {tag}  {time.time()-t0:.0f}s", flush=True)

def mosaic(kind):
    files = sorted(glob.glob(os.path.join(WORK, f"tile_{kind}_*.tif")))
    vrt = gdal.BuildVRT(os.path.join(WORK, f"_{kind}.vrt"), files, srcNodata=-9999, VRTNodata=-9999, resolution="user", xRes=CELL, yRes=CELL, outputBounds=(e[0], e[2], e[1], e[3]))
    out = os.path.join(WORK, f"{kind}_3ft.tif")
    gdal.Translate(out, vrt, creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES", "BIGTIFF=IF_SAFER"]); vrt = None
    return out
dtm_p, dsm_p, chm_p = mosaic("dtm"), mosaic("dsm"), mosaic("chm")
print("mosaics written")

# fill small DTM holes (water, dense canopy) and derive terrain products
ds = gdal.Open(dtm_p, gdal.GA_Update); gdal.FillNodata(ds.GetRasterBand(1), None, maxSearchDist=50, smoothingIterations=1); ds = None
def derive(name, proc, **kw):
    out = os.path.join(WORK, name); gdal.DEMProcessing(out, dtm_p, proc, format="GTiff", creationOptions=["COMPRESS=DEFLATE", "TILED=YES"], computeEdges=True, **kw); return out
slope_p = derive("slope_pct.tif", "slope", slopeFormat="percent")
aspect_p = derive("aspect_deg.tif", "aspect", zeroForFlat=True)
derive("hillshade.tif", "hillshade", multiDirectional=True, zFactor=1.0)
print("slope, aspect, hillshade written")

def read(p):
    d = gdal.Open(p); a = d.GetRasterBand(1).ReadAsArray().astype("float32"); nd = d.GetRasterBand(1).GetNoDataValue()
    return np.where(a == nd, np.nan, a), d
def write_like(name, arr, like, nodata=-9999.0, dtype=gdal.GDT_Float32):
    out = gdal.GetDriverByName("GTiff").Create(os.path.join(WORK, name), like.RasterXSize, like.RasterYSize, 1, dtype, ["COMPRESS=DEFLATE", "TILED=YES"])
    out.SetGeoTransform(like.GetGeoTransform()); out.SetProjection(like.GetProjection()); b = out.GetRasterBand(1)
    b.WriteArray(np.where(np.isnan(arr), nodata, arr)); b.SetNoDataValue(nodata); out.FlushCache(); return os.path.join(WORK, name)

# The processed area (AOI) is the set of valid DTM cells; after FillNodata it has no internal holes, so every
# nodata cell lies outside the AOI rim. Filling that nodata with a constant before filtering (the first version
# used the mean elevation for the DTM and 0 for the CHM) put a cliff at the rim, and the 15 ft Gaussian and the
# 99 ft averaging spread it inward: planning slopes over 1,000 % within about 110 ft of the rim. Two fixes:
#   1. the DTM and CHM are extended outward by their nearest valid cell before any filter (no cliff), and
#   2. the window means (canopy cover, planning slope) are normalized convolutions that average valid cells only.
# Cells more than about 110 ft inside the rim see exactly the same window contents as before; the units lie more
# than 900 ft inside it.
dtm_a, dtm_ds = read(dtm_p); aoi = ~np.isnan(dtm_a); aoi_f = aoi.astype("float32")
near = ndimage.distance_transform_edt(~aoi, return_distances=False, return_indices=True)   # row, col of the nearest valid cell
def nearest_fill(a):
    """Extend a (nan-free inside the AOI) outward by the nearest valid cell."""
    return a[near[0], near[1]]
def window_mean(a, size):
    """Mean of a over the valid cells of a size x size window (normalized convolution); nan outside the AOI."""
    w = ndimage.uniform_filter(aoi_f, size=size, mode="nearest")
    return np.where(aoi, ndimage.uniform_filter(a * aoi_f, size=size, mode="nearest") / np.maximum(w, 1e-6), np.nan)

chm, chm_ds = read(chm_p); chm = np.where(np.isnan(chm), 0, chm)   # no non-noise return in an AOI cell: 0 ft (bare ground)
win = int(round(66 / CELL))
cover = window_mean((chm > 6.5).astype("float32"), win)
write_like("canopy_cover_66ft.tif", cover, chm_ds)
dom = np.where(aoi, ndimage.percentile_filter(nearest_fill(chm), 95, size=win, mode="nearest"), np.nan)
write_like("dom_height_66ft.tif", dom, chm_ds)
slope, slope_ds = read(slope_p)
# planning slope: gradient of a DTM smoothed with a 15 ft Gaussian, then averaged over 99 ft, so single
# cut banks, boulders and interpolation noise under dense canopy do not drive the yarding class
dtm_sm = ndimage.gaussian_filter(nearest_fill(dtm_a), sigma=15 / CELL)
gy, gx = np.gradient(dtm_sm, CELL); slope_plan = np.hypot(gx, gy) * 100; del dtm_sm, gx, gy
slope_plan = window_mean(slope_plan, int(round(99 / CELL))).astype("float32")
write_like("slope_plan_pct.tif", slope_plan, dtm_ds)
slope_s = np.nan_to_num(slope_plan, nan=0)
ycls = np.where(np.isnan(slope), np.nan, np.where(slope_s <= 35, 1, np.where(slope_s <= 50, 2, 3))).astype("float32")
write_like("yarding_class.tif", ycls, slope_ds, dtype=gdal.GDT_Float32); del slope_s, near
# Summary statistics exclude a 150 ft rim inside the AOI boundary (the array edge counts as boundary): the 99 ft
# window means there are averages over partial windows, and the rim is terrain context outside the treatment
# block anyway. The elevation range is reported over the whole processed area, where no filter is involved.
RIM_FT = 150
rim = ndimage.distance_transform_edt(np.pad(aoi, 1, constant_values=False))[1:-1, 1:-1] * CELL < RIM_FT
valid = ~np.isnan(slope); interior = valid & ~rim; del rim
stats = dict(cells=int(valid.sum()), acres=round(float(valid.sum()) * CELL * CELL / 43560, 1),
             rim_excluded_ft=RIM_FT, interior_acres=round(float(interior.sum()) * CELL * CELL / 43560, 1),
             slope_mean_pct=round(float(np.nanmean(slope[interior])), 1), slope_plan_median_pct=round(float(np.nanmedian(slope_plan[interior])), 1),
             pct_ground_based=round(float((ycls[interior] == 1).mean() * 100), 1),
             pct_marginal=round(float((ycls[interior] == 2).mean() * 100), 1), pct_cable=round(float((ycls[interior] == 3).mean() * 100), 1),
             canopy_cover_mean=round(float(np.nanmean(cover[interior]) * 100), 1), chm_p95_ft=round(float(np.percentile(chm[interior], 95)), 1),
             slope_plan_max_pct=round(float(np.nanmax(slope_plan)), 1), slope_plan_max_interior_pct=round(float(np.nanmax(slope_plan[interior])), 1),
             dtm_min_ft=round(float(np.nanmin(dtm_a)), 0), dtm_max_ft=round(float(np.nanmax(dtm_a)), 0))
json.dump(stats, open(os.path.join(WORK, "terrain_summary.json"), "w"), indent=1); print(stats)
print(f"done in {time.time()-t0:.0f}s")
