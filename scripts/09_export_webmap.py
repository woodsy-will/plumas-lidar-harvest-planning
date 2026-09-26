"""Export the web-map layers for the portfolio site from the project GeoPackage: GeoJSON in WGS84, simplified in State
Plane feet and rounded, plus a yarding-class PNG overlay warped to Web Mercator with WGS84 bounds.

Usage:  python-qgis-ltr.bat scripts/09_export_webmap.py [OUT_DIR]

OUT_DIR defaults to ../williamsteinley.github.io/projects/plumas-lidar-harvest-planning/map/data next to this repository.
Read-only on the project; writes only to OUT_DIR.
"""
import os, sys, json, csv
import geopandas as gpd
from osgeo import gdal, osr
import numpy as np
from PIL import Image
from shapely.geometry import shape, mapping

P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(P, "output", "gis", "mohawk_west_slope.gpkg")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(P), "williamsteinley.github.io", "projects", "plumas-lidar-harvest-planning", "map", "data")
os.makedirs(OUT, exist_ok=True)
gdal.UseExceptions()
CRS_FT = 2226  # CA State Plane Zone 2, US ft: simplify tolerances are in feet, so every layer is projected here first


def _distinct(coords):
    return len({tuple(c) for c in coords})


def _clean(geom):
    """Drop degenerate parts after rounding: lines with fewer than two distinct points, rings with fewer than four."""
    t = geom["type"]
    if t == "LineString":
        return geom if _distinct(geom["coordinates"]) >= 2 else None
    if t == "MultiLineString":
        parts = [l for l in geom["coordinates"] if _distinct(l) >= 2]
        return {"type": t, "coordinates": parts} if parts else None
    if t == "Polygon":
        rings = [r for r in geom["coordinates"] if _distinct(r) >= 4]
        return {"type": t, "coordinates": rings} if rings and rings[0] is geom["coordinates"][0] else None
    if t == "MultiPolygon":
        polys = []
        for poly in geom["coordinates"]:
            rings = [r for r in poly if _distinct(r) >= 4]
            if rings and rings[0] is poly[0]:
                polys.append(rings)
        return {"type": t, "coordinates": polys} if polys else None
    return geom


def write(gdf, name, tol_ft=None, cols=None, precision=5):
    gdf = gdf.to_crs(CRS_FT)
    full = gdf.copy()  # unsimplified copy: a feature that collapses under simplify + rounding falls back to this
    if tol_ft:
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.simplify(tol_ft, preserve_topology=True)
        if gdf.geom_type.isin(["Polygon", "MultiPolygon"]).all():
            gdf["geometry"] = gdf.geometry.buffer(0)
    if cols:
        gdf = gdf[cols + ["geometry"]]
        full = full[cols + ["geometry"]]
    gdf = gdf.to_crs(4326)
    full = full.to_crs(4326)
    gj = json.loads(gdf.to_json(drop_id=True))
    gj_full = json.loads(full.to_json(drop_id=True))

    def rnd(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], precision), round(c[1], precision)]
        return [rnd(x) for x in c]

    feats = []
    dropped = 0
    for f, f_full in zip(gj["features"], gj_full["features"]):
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
        g = _clean(f["geometry"])
        if g is None:  # keep the feature at full resolution rather than losing it (small EEZ slivers, short contour fragments)
            f_full["geometry"]["coordinates"] = rnd(f_full["geometry"]["coordinates"])
            g = _clean(f_full["geometry"])
            f = f_full
        if g is None:
            dropped += 1
            continue
        if g["type"] in ("Polygon", "MultiPolygon"):  # rounding can make a thin ring self-touch; a zero-width buffer repairs it
            sg = shape(g)
            if not sg.is_valid:
                sg = sg.buffer(0)
                if sg.is_empty:
                    dropped += 1
                    continue
                g = mapping(sg)
                g["coordinates"] = rnd(g["coordinates"])
        f["geometry"] = g
        f["properties"] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in f["properties"].items()}
        feats.append(f)
    gj["features"] = feats
    path = os.path.join(OUT, name)
    json.dump(gj, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{name:26} {len(feats):5} features  {os.path.getsize(path)/1e6:5.2f} MB" + (f"  ({dropped} dropped)" if dropped else ""))


# units with the cable summary joined
units = gpd.read_file(G, layer="units")
summ = {int(r["unit_id"]): r for r in csv.DictReader(open(os.path.join(P, "output", "cable", "unit_summary.csv"), encoding="utf-8"))}
keep = ["landings", "landings_used", "corridors", "corridors_feasible", "coverage_pct", "equipment", "difficulty", "payload_at_best_lb", "max_feasible_span_ft", "mean_deflection_pct"]
for k in keep:
    units[k] = units["unit_id"].map(lambda u: (summ.get(int(u), {}) or {}).get(k, ""))
write(units, "units.geojson", tol_ft=3, cols=["unit_id", "method", "acres", "net_acres", "slope_mean", "slope_max", "aspect", "elev_min", "elev_max", "cover_pct", "dom_ht", "road_ft"] + keep)

# treatment block: aoi.geojson is WGS84, so it is projected to feet inside write() before simplifying
block = gpd.read_file(os.path.join(P, "data", "raw", "aoi.geojson"))
block = block[block["role"] == "treatment_block"] if "role" in block.columns else block
write(block, "block.geojson", tol_ft=3, cols=[c for c in block.columns if c in ("role", "name")], precision=6)

streams = gpd.read_file(G, layer="streams_aoi"); write(streams, "streams.geojson", tol_ft=5, cols=["class", "name"])
eez = gpd.read_file(G, layer="eez_buffers"); write(eez, "eez.geojson", tol_ft=5, cols=["class", "width_ft"])
rca = gpd.read_file(G, layer="rca_buffers"); write(rca, "rca.geojson", tol_ft=8, cols=["class", "width_ft"])
cont = gpd.read_file(G, layer="contours"); cont = cont[cont["index"] == 1]; write(cont, "contours200.geojson", tol_ft=8, cols=["elev"])
land = gpd.read_file(G, layer="landings"); write(land, "landings.geojson", cols=["unit_id", "landing_id", "elev", "corridors_ok", "coverage_pct"])
corr = gpd.read_file(G, layer="corridors"); corr = corr[corr["feasible"] == 1]
write(corr, "corridors_feasible.geojson", tol_ft=10, cols=["unit_id", "landing_id", "span_ft", "deflection_pct", "min_clear_ft", "downhill", "span_class"])
plots = gpd.read_file(G, layer="plots"); write(plots, "plots.geojson", cols=["plot", "unit_id", "n_trees", "slope", "flags"])

# yarding class overlay: warp to EPSG:3857, 4-colour palette PNG with transparency, bounds in WGS84
src = os.path.join(P, "output", "gis", "yarding_class.tif")
tmp = os.path.join(OUT, "_yc3857.tif")
# clip to the units plus a 500 ft margin: over a topographic basemap the full DTM footprint reads as a hard-edged
# rectangle of colour across ground nobody proposed to treat, and the classes only mean anything next to the units
cut = os.path.join(OUT, "_ycmask.geojson")
gpd.GeoDataFrame(geometry=[gpd.read_file(G, layer="units").to_crs(CRS_FT).buffer(500).union_all()], crs=CRS_FT).to_file(cut, driver="GeoJSON")
gdal.Warp(tmp, src, dstSRS="EPSG:3857", xRes=6, yRes=6, resampleAlg="near", dstNodata=0,
          cutlineDSName=cut, cropToCutline=True)
os.remove(cut)
ds = gdal.Open(tmp); a = ds.GetRasterBand(1).ReadAsArray(); gt = ds.GetGeoTransform(); w, h = ds.RasterXSize, ds.RasterYSize
rgba = np.zeros((h, w, 4), dtype=np.uint8)
pal = {1: (166, 206, 189, 150), 2: (240, 228, 150, 160), 3: (241, 176, 140, 170)}   # ground-based, marginal, cable (pale Okabe tints)
for v, c in pal.items():
    rgba[a == v] = c
im = Image.fromarray(rgba, "RGBA").quantize(colors=4, method=Image.Quantize.FASTOCTREE)
im.save(os.path.join(OUT, "yarding_class.png"), optimize=True)
x0, y1 = gt[0], gt[3]; x1 = x0 + w * gt[1]; y0 = y1 + h * gt[5]
s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s3857 = osr.SpatialReference(); s3857.ImportFromEPSG(3857); s3857.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
tr = osr.CoordinateTransformation(s3857, s4326)
lon0, lat0, _ = tr.TransformPoint(x0, y0); lon1, lat1, _ = tr.TransformPoint(x1, y1)
json.dump({"bounds": [[round(lat0, 6), round(lon0, 6)], [round(lat1, 6), round(lon1, 6)]],
           "classes": {"1": "Ground-based, slope 35 % and under", "2": "Marginal, 35 to 50 %", "3": "Cable, over 50 %"}},
          open(os.path.join(OUT, "yarding_class.json"), "w"))
ds = None; os.remove(tmp)
print("yarding_class.png", w, "x", h, f"{os.path.getsize(os.path.join(OUT, 'yarding_class.png'))/1e6:.2f} MB")
print("total MB:", round(sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT)) / 1e6, 2))
