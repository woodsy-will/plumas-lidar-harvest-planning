"""03_delineate_units.py - demonstration harvest units from the terrain products.

Rules (repeated in docs/methods.md):
  operable  = inside the treatment block AND National Forest land
              AND a stand is present: canopy cover >= 30 % and dominant height >= 40 ft (66 ft windows)
              AND planning slope <= 100 % (smoothed DTM, 99 ft average) AND within 3,500 ft of a road
              (EDW NFS roads plus Census TIGER local roads)
  streams   = equipment exclusion zones (perennial 100 ft, intermittent 50 ft, ephemeral 25 ft, waterbody
              100 ft) stay inside the unit as an internal restriction and are netted out of net_acres;
              the wider riparian conservation areas (300 / 150 / 100 ft) are written for display
  cleaning  = morphological open then close with a 99 ft kernel, fill holes, drop regions under 20 ac
  splitting = ground-based (planning slope <= 35 %) and cable ground are kept separate; any region over
              150 ac is split toward 80 ac pieces by k-means on position, smoothed elevation and aspect,
              so split lines fall on ridges and draws; a 99 ft majority filter compacts the pieces and
              pieces under 20 ac merge into their largest neighbor
  method    = Hand Thinning where dominant height < 55 ft and cover >= 50 % (small-diameter fuels stand),
              otherwise Tractor where mean slope <= 35 %, Cable above that
  numbering = 100-series Tractor, 400-series Cable, 700-series Hand Thinning, numbered west to east
Writes data/work/planning.gpkg with layers units, rca_buffers, eez_buffers and operable_mask.
Run: python-qgis-ltr.bat scripts\03_delineate_units.py
"""
import json
import os

import numpy as np
from osgeo import gdal, ogr, osr
from scipy import ndimage
from scipy.ndimage import distance_transform_edt

gdal.UseExceptions(); osr.UseExceptions(); ogr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, WORK = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "work")
CELL = 3.0
CELLS_PER_AC = 43560.0 / (CELL * CELL)
RCA = {"perennial": 300, "intermittent": 150, "ephemeral": 100, "waterbody": 300}      # conservation area, mapped for display
EEZ = {"perennial": 100, "intermittent": 50, "ephemeral": 25, "waterbody": 100}        # equipment exclusion, removed from units
SLOPE_CAP = 100
MIN_AC, MAX_AC, TARGET_AC = 20, 150, 80
KERNEL = int(round(99 / CELL))


def ras(name):
    d = gdal.Open(os.path.join(WORK, name)); b = d.GetRasterBand(1)
    a = b.ReadAsArray().astype("float32"); nd = b.GetNoDataValue()
    return np.where(a == nd, np.nan, a), d


slope, ref = ras("slope_plan_pct.tif")      # planning slope (smoothed DTM, 99 ft average); slope_pct.tif keeps the 3 ft detail
cover, _ = ras("canopy_cover_66ft.tif")
dom, _ = ras("dom_height_66ft.tif")
ycls, _ = ras("yarding_class.tif")
dtm, _ = ras("dtm_3ft.tif")
aspect, _ = ras("aspect_deg.tif")
gt = ref.GetGeoTransform(); ny, nx = slope.shape; srs_wkt = ref.GetProjection()
sp = osr.SpatialReference(); sp.ImportFromWkt(srs_wkt); sp.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_sp = osr.CoordinateTransformation(s4326, sp)


def load(name, where=None):
    gj = json.load(open(os.path.join(RAW, name)))
    out = []
    for f in gj["features"]:
        if where and not where(f["properties"]):
            continue
        g = ogr.CreateGeometryFromJson(json.dumps(f["geometry"])); g.Transform(to_sp)
        out.append((g, f["properties"]))
    return out


def rasterize(geoms, buffer=0.0):
    ds = ogr.GetDriverByName("Memory").CreateDataSource("m")
    lyr = ds.CreateLayer("l", sp, ogr.wkbPolygon)
    for g in geoms:
        gg = g.Buffer(buffer) if buffer else g
        if gg.GetGeometryName() not in ("POLYGON", "MULTIPOLYGON"):
            continue
        f = ogr.Feature(lyr.GetLayerDefn()); f.SetGeometry(gg); lyr.CreateFeature(f)
    tgt = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Byte)
    tgt.SetGeoTransform(gt); tgt.SetProjection(srs_wkt)
    gdal.RasterizeLayer(tgt, [1], lyr, burn_values=[1])
    return tgt.GetRasterBand(1).ReadAsArray().astype(bool)


block = [g for g, p in load("aoi.geojson", lambda p: p["role"] == "treatment_block")]
nfs = [g for g, p in load("blm_sma_usfs.geojson")]
roads = [g for g, p in load("fs_roads.geojson")] + ([g for g, p in load("tiger_roads.geojson")] if os.path.exists(os.path.join(RAW, "tiger_roads.geojson")) else [])
flow = load("nhd_flowlines.geojson")
wb = [g for g, p in load("nhd_waterbodies.geojson")]


def fcode(p):
    return int(p.get("fcode") or p.get("FCODE") or 0)


per = [g for g, p in flow if fcode(p) in (46006, 55800, 33600)]   # perennial, artificial path, canal
inter = [g for g, p in flow if fcode(p) == 46003]
eph = [g for g, p in flow if fcode(p) == 46007]
print(f"streams: {len(per)} perennial, {len(inter)} intermittent, {len(eph)} ephemeral, {len(wb)} waterbodies, {len(roads)} road segments")

eez = (rasterize(per, EEZ["perennial"]) | rasterize(inter, EEZ["intermittent"])
       | rasterize(eph, EEZ["ephemeral"]) | rasterize(wb, EEZ["waterbody"]))
in_block = rasterize(block) & rasterize(nfs)
near_road = rasterize(roads, 3500)
stand = (np.nan_to_num(cover) >= 0.30) & (np.nan_to_num(dom) >= 40)
# Stream exclusion zones stay inside the unit boundary as an internal restriction (shown on the maps and
# netted out of the treatable acreage) rather than being cut out, which is how layout crews draw units.
operable = in_block & stand & (np.nan_to_num(slope, nan=999) <= SLOPE_CAP) & near_road
se = np.ones((KERNEL, KERNEL), bool)
operable = ndimage.binary_opening(operable, se)
operable = ndimage.binary_closing(operable, se) & in_block
operable = ndimage.binary_fill_holes(operable) & in_block
print(f"operable after cleaning: {operable.sum() / CELLS_PER_AC:,.0f} ac of {in_block.sum() / CELLS_PER_AC:,.0f} ac block")

# separate ground-based from cable ground, label regions, drop small ones
slope_s = ndimage.uniform_filter(np.nan_to_num(slope), size=KERNEL, mode="nearest")
ground = operable & (slope_s <= 35)
cable = operable & ~ground
lab = np.zeros(operable.shape, np.int32); nid = 0
for mask in (ground, cable):
    lbl, n = ndimage.label(mask, structure=np.ones((3, 3)))
    for i in range(1, n + 1):
        m = lbl == i
        if m.sum() / CELLS_PER_AC >= MIN_AC:
            nid += 1; lab[m] = nid
print(f"regions of at least {MIN_AC} ac: {nid}")

# split large regions along slope breaks: k-means on position, smoothed elevation and aspect, so the
# boundaries between pieces fall on ridges and draws where aspect turns, then a majority filter tidies them
dtm_s = ndimage.gaussian_filter(np.nan_to_num(dtm, nan=float(np.nanmean(dtm))), sigma=33 / CELL)
asp_r = np.deg2rad(np.nan_to_num(aspect, nan=0.0))
asp_c = ndimage.uniform_filter(np.cos(asp_r), size=KERNEL, mode="nearest")
asp_s = ndimage.uniform_filter(np.sin(asp_r), size=KERNEL, mode="nearest")
ELEV_W, ASPECT_W = 3.0, 400.0        # 1 ft of elevation ~ 3 ft of distance; a full aspect reversal ~ 800 ft


def split_region(m, nparts):
    ys, xs = np.nonzero(m)
    feats = np.column_stack([xs * CELL, ys * CELL, ELEV_W * dtm_s[ys, xs], ASPECT_W * asp_c[ys, xs], ASPECT_W * asp_s[ys, xs]]).astype("float32")
    rng = np.random.default_rng(1)
    cent = feats[rng.choice(len(feats), nparts, replace=False)]
    for _ in range(40):
        d = ((feats[:, None, :] - cent[None, :, :]) ** 2).sum(-1); a = d.argmin(1)
        cent = np.array([feats[a == j].mean(0) if (a == j).any() else cent[j] for j in range(nparts)])
    seg = np.zeros(m.shape, np.int32); seg[ys, xs] = a + 1
    # majority filter over 99 ft so the pieces are compact
    votes = np.stack([ndimage.uniform_filter((seg == j).astype("float32"), size=KERNEL, mode="nearest") for j in range(1, nparts + 1)])
    seg = np.where(m, votes.argmax(0) + 1, 0).astype(np.int32)
    # keep only the largest connected piece of each label; reassign fragments by the majority of their neighbors
    for j in range(1, nparts + 1):
        lbl, n = ndimage.label(seg == j)
        if n > 1:
            sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1)); keep = int(np.argmax(sizes)) + 1
            frag = (lbl > 0) & (lbl != keep); seg[frag] = 0
    while (m & (seg == 0)).any():
        grow = ndimage.grey_dilation(seg, size=3); fill = m & (seg == 0) & (grow > 0); seg[fill] = grow[fill]
        if not fill.any():
            break
    for j in range(1, nparts + 1):
        part = seg == j
        if 0 < part.sum() < MIN_AC * CELLS_PER_AC:
            ring = ndimage.binary_dilation(part, np.ones((3, 3))) & m & ~part
            nb = np.bincount(seg[ring], minlength=nparts + 1); nb[0] = 0; nb[j] = 0
            if nb.any():
                seg[part] = nb.argmax()
    return seg


final = np.zeros_like(lab); uid = 0
for i in range(1, nid + 1):
    m = lab == i; acres = m.sum() / CELLS_PER_AC
    if acres <= MAX_AC:
        uid += 1; final[m] = uid; continue
    seg = split_region(m, int(np.ceil(acres / TARGET_AC)))
    for j in np.unique(seg[m]):
        if j == 0:
            continue
        uid += 1; final[seg == j] = uid
print(f"units after splitting: {uid}")

# vectorize and attribute
gp = os.path.join(WORK, "planning.gpkg")
drv = ogr.GetDriverByName("GPKG")
if os.path.exists(gp):
    drv.DeleteDataSource(gp)
ds = drv.CreateDataSource(gp)
mem = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Int32)
mem.SetGeoTransform(gt); mem.SetProjection(srs_wkt); mem.GetRasterBand(1).WriteArray(final)
scratch = ogr.GetDriverByName("Memory").CreateDataSource("s")
tmp = scratch.CreateLayer("raw", sp, ogr.wkbPolygon); tmp.CreateField(ogr.FieldDefn("uid", ogr.OFTInteger))
gdal.Polygonize(mem.GetRasterBand(1), None, tmp, 0)
polys = {}
for f in tmp:
    u = f.GetField("uid")
    if u == 0:
        continue
    g = f.GetGeometryRef().Clone()
    polys[u] = polys[u].Union(g) if u in polys else g

road_dist = distance_transform_edt(~rasterize(roads, CELL)) * CELL
DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
rows = []
eez_ras = eez
for u, g in polys.items():
    g = g.Buffer(30).Buffer(-30).SimplifyPreserveTopology(20)        # round the raster stair-steps, then generalise to 20 ft
    if g.IsEmpty() or g.GetArea() / 43560 < MIN_AC * 0.8:
        continue
    m = final == u
    sl = slope[m]; asp = aspect[m]; asp = asp[~np.isnan(asp)]
    ang = np.deg2rad(asp)
    mean_asp = (np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) + 360) % 360
    smean = float(np.nanmean(sl)); dh = float(np.nanmean(dom[m])); cv = float(np.nanmean(cover[m])) * 100
    method = "Hand Thinning" if (dh < 55 and cv >= 50) else ("Tractor" if smean <= 35 else "Cable")
    rows.append(dict(geom=g, x=g.Centroid().GetX(), method=method, acres=g.GetArea() / 43560, net_acres=g.GetArea() / 43560 * (1 - float(eez_ras[m].mean())),
                     slope_mean=smean, slope_max=float(np.nanpercentile(sl, 98)),
                     aspect=DIRS[int(((mean_asp + 22.5) % 360) // 45)],
                     elev_min=float(np.nanmin(dtm[m])), elev_max=float(np.nanmax(dtm[m])),
                     cover_pct=cv, dom_ht=dh, road_ft=float(np.nanmin(road_dist[m]))))

units = ds.CreateLayer("units", sp, ogr.wkbMultiPolygon)
FIELDS = [("unit_id", ogr.OFTInteger), ("method", ogr.OFTString), ("acres", ogr.OFTReal), ("net_acres", ogr.OFTReal), ("slope_mean", ogr.OFTReal),
          ("slope_max", ogr.OFTReal), ("aspect", ogr.OFTString), ("elev_min", ogr.OFTReal), ("elev_max", ogr.OFTReal),
          ("cover_pct", ogr.OFTReal), ("dom_ht", ogr.OFTReal), ("road_ft", ogr.OFTReal)]
for n, t in FIELDS:
    units.CreateField(ogr.FieldDefn(n, t))
counters = {"Tractor": 100, "Cable": 400, "Hand Thinning": 700}
for r in sorted(rows, key=lambda r: r["x"]):
    counters[r["method"]] += 1; r["unit_id"] = counters[r["method"]]
    f = ogr.Feature(units.GetLayerDefn()); f.SetGeometry(ogr.ForceToMultiPolygon(r["geom"]))
    for n, _ in FIELDS:
        v = r[n]; f.SetField(n, round(v, 1) if isinstance(v, float) else v)
    units.CreateFeature(f)

aoi_poly = [g for g, p in load("aoi.geojson", lambda p: p["role"] == "aoi")][0]
for lname, widths in (("rca_buffers", RCA), ("eez_buffers", EEZ)):
    rl = ds.CreateLayer(lname, sp, ogr.wkbMultiPolygon)
    rl.CreateField(ogr.FieldDefn("class", ogr.OFTString)); rl.CreateField(ogr.FieldDefn("width_ft", ogr.OFTInteger))
    for cls, geoms in (("perennial", per), ("intermittent", inter), ("ephemeral", eph), ("waterbody", wb)):
        for g in geoms:
            b = g.Buffer(widths[cls]).Intersection(aoi_poly)          # clipped to the AOI so the sheets stay legible
            if b is None or b.IsEmpty():
                continue
            f = ogr.Feature(rl.GetLayerDefn()); f.SetGeometry(ogr.ForceToMultiPolygon(b))
            f.SetField("class", cls); f.SetField("width_ft", widths[cls]); rl.CreateFeature(f)
# contours from a lightly smoothed DTM: 40 ft interval, index every 200 ft (the sale-map convention on steep ground)
cl = ds.CreateLayer("contours", sp, ogr.wkbLineString)
cl.CreateField(ogr.FieldDefn("id", ogr.OFTInteger)); cl.CreateField(ogr.FieldDefn("elev", ogr.OFTReal))
dtm_c = ndimage.gaussian_filter(np.nan_to_num(dtm, nan=float(np.nanmean(dtm))), sigma=9 / CELL)
memc = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Float32)
memc.SetGeoTransform(gt); memc.SetProjection(srs_wkt); memc.GetRasterBand(1).WriteArray(np.where(np.isnan(dtm), -9999, dtm_c).astype("float32")); memc.GetRasterBand(1).SetNoDataValue(-9999)
gdal.ContourGenerate(memc.GetRasterBand(1), 40, 0, [], 1, -9999, cl, 0, 1)
cl.CreateField(ogr.FieldDefn("index", ogr.OFTInteger))
for f in cl:
    f.SetField("index", 1 if int(round(f.GetField("elev"))) % 200 == 0 else 0); cl.SetFeature(f)
print("contours:", cl.GetFeatureCount())
sl = ds.CreateLayer("streams_aoi", sp, ogr.wkbMultiLineString)
sl.CreateField(ogr.FieldDefn("class", ogr.OFTString)); sl.CreateField(ogr.FieldDefn("fcode", ogr.OFTInteger)); sl.CreateField(ogr.FieldDefn("name", ogr.OFTString))
for g, p in flow:
    c = g.Intersection(aoi_poly)
    if c is None or c.IsEmpty():
        continue
    cls = "perennial" if fcode(p) in (46006, 55800, 33600) else ("intermittent" if fcode(p) == 46003 else ("ephemeral" if fcode(p) == 46007 else "other"))
    f = ogr.Feature(sl.GetLayerDefn()); f.SetGeometry(ogr.ForceToMultiLineString(c)); f.SetField("class", cls); f.SetField("fcode", fcode(p)); f.SetField("name", p.get("gnis_name") or ""); sl.CreateFeature(f)
memo = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Byte)
memo.SetGeoTransform(gt); memo.SetProjection(srs_wkt); memo.GetRasterBand(1).WriteArray(operable.astype("uint8"))
ol = ds.CreateLayer("operable_mask", sp, ogr.wkbPolygon); ol.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
gdal.Polygonize(memo.GetRasterBand(1), memo.GetRasterBand(1), ol, 0)
ds = None

summary = {}
for r in rows:
    s = summary.setdefault(r["method"], [0, 0.0]); s[0] += 1; s[1] += r["acres"]
print("units:", {k: (v[0], round(v[1])) for k, v in summary.items()}, "| total", round(sum(r["acres"] for r in rows)), "ac")
