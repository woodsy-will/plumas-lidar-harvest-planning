"""01_get_data.py - fetch every public input for the Mohawk Valley west-slope harvest-planning rebuild.

Area of interest: the Community Protection (Central and West Slope, 2025 decision) treatment block
on National Forest land nearest Whitehawk Ranch, Clio CA, buffered 300 m for terrain context.
Everything here is public data. No former-employer material is used anywhere in this repository.

Sources
  USFS EDW Activity Project Areas (NEPA)  -> Community Protection treatment blocks
  BLM Surface Management Agency (USFS)    -> National Forest System land
  USFS EDW Road Core                      -> NFS roads
  USGS NHD                                -> flowlines, waterbodies
  BLM PLSS CadNSDI                        -> townships, sections
  USGS 3DEP  CA_NoCAL_Wildfires_PlumasNF B1/B2 2018 (QL1) -> LAZ tiles intersecting the AOI
Run with QGIS's bundled Python:  python-qgis-ltr.bat scripts\01_get_data.py [--download]
"""
import json, math, os, re, sys, time, urllib.parse, urllib.request
from osgeo import ogr, osr
osr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw"); LAZ = os.path.join(RAW, "laz"); os.makedirs(LAZ, exist_ok=True)
UA = {"User-Agent": "plumas-lidar-harvest-planning (github.com/woodsy-will)"}
ANCHOR = (-120.60, 39.72)      # Whitehawk Ranch, Clio (lon, lat)
SEARCH = [-120.78, 39.60, -120.50, 39.82]
BUFFER_M = 300

def get_json(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=UA)
    for attempt in range(4):
        try: return json.load(urllib.request.urlopen(req, timeout=300))
        except Exception:
            if attempt == 3: raise
            time.sleep(8)

def arcgis(url, where="1=1", bbox=None, extra=None):
    p = dict(where=where, outFields="*", returnGeometry="true", outSR=4326, f="geojson")
    if bbox: p.update(geometry=json.dumps(dict(xmin=bbox[0], ymin=bbox[1], xmax=bbox[2], ymax=bbox[3], spatialReference=dict(wkid=4326))), geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects")
    if extra: p.update(extra)
    out, offset = None, 0
    while True:
        p["resultOffset"] = offset; gj = get_json(url, p); feats = gj.get("features", [])
        if out is None: out = gj
        else: out["features"] += feats
        if not gj.get("properties", {}).get("exceededTransferLimit") and len(feats) < 1000: break
        offset += len(feats)
    return out

def save(name, gj):
    json.dump(gj, open(os.path.join(RAW, name), "w")); print(f"  {name}: {len(gj.get('features', []))} features", flush=True)

def geom(f): return ogr.CreateGeometryFromJson(json.dumps(f["geometry"]))
s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
utm = osr.SpatialReference(); utm.ImportFromEPSG(26910); utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
alb = osr.SpatialReference(); alb.ImportFromEPSG(5070); alb.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_utm, to_ll, to_alb = (osr.CoordinateTransformation(a, b) for a, b in ((s4326, utm), (utm, s4326), (utm, alb)))

EDW = "https://apps.fs.usda.gov/arcx/rest/services/EDW"
print("Community Protection treatment blocks")
cp = arcgis(f"{EDW}/EDW_ActivityProjectAreas_01/MapServer/0/query", where="name LIKE 'COMMUNITY PROTECTION%'", bbox=SEARCH)
save("facts_cp_project_areas.geojson", cp)
usfs = arcgis("https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_SMA_LimitedScale/MapServer/9/query", bbox=SEARCH)
save("blm_sma_usfs.geojson", usfs)
nfs = None
for f in usfs["features"]: nfs = geom(f) if nfs is None else nfs.Union(geom(f))

best = None
for f in cp["features"]:
    if f["properties"]["gis_acres"] < 100000: continue          # 2025 decision polygons only
    g = geom(f).Intersection(nfs)
    parts = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryName() == "MULTIPOLYGON" else [g]
    for p in parts:
        c = p.Centroid(); d = math.hypot((c.GetX() - ANCHOR[0]) * 85.6, (c.GetY() - ANCHOR[1]) * 111.0)
        pu = p.Clone(); pu.Transform(to_utm); acres = pu.GetArea() / 4046.86
        if acres >= 1000 and (best is None or d < best[0]): best = (d, acres, pu, p.Clone())
d, acres, block_utm, block_ll = best
print(f"  selected block: {acres:,.0f} ac, {d:.1f} km from Whitehawk Ranch")
aoi_utm = block_utm.Buffer(BUFFER_M); aoi_ll = aoi_utm.Clone(); aoi_ll.Transform(to_ll)
e = aoi_ll.GetEnvelope(); bbox = [e[0], e[2], e[1], e[3]]
json.dump(dict(type="FeatureCollection", features=[dict(type="Feature", properties=dict(role="treatment_block", acres=round(acres)), geometry=json.loads(block_ll.ExportToJson())), dict(type="Feature", properties=dict(role="aoi", buffer_m=BUFFER_M), geometry=json.loads(aoi_ll.ExportToJson()))]), open(os.path.join(RAW, "aoi.geojson"), "w"))
print("  AOI bbox lon/lat:", [round(v, 4) for v in bbox], flush=True)

print("Roads, streams, PLSS")
save("fs_roads.geojson", arcgis(f"{EDW}/EDW_RoadBasic_01/MapServer/0/query", bbox=bbox))
NHD = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"
save("nhd_flowlines.geojson", arcgis(f"{NHD}/6/query", bbox=bbox))
save("nhd_waterbodies.geojson", arcgis(f"{NHD}/10/query", bbox=bbox))
PLSS = "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer"
save("plss_townships.geojson", arcgis(f"{PLSS}/1/query", bbox=bbox))
save("plss_sections.geojson", arcgis(f"{PLSS}/2/query", bbox=bbox))

print("USGS 3DEP tiles")
aoi_alb = aoi_utm.Clone(); aoi_alb.Transform(to_alb)
base = "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/CA_NoCAL_3DEP_Supp_Funding_2018_D18/"
links = []
for sub in ("CA_NoCAL_Wildfires_PlumasNF_B2_2018", "CA_NoCAL_Wildfires_PlumasNF_B1_2018"):
    txt = urllib.request.urlopen(urllib.request.Request(base + sub + "/0_file_download_links.txt", headers=UA), timeout=120).read().decode()
    links += [l for l in txt.split() if l.endswith(".laz")]
need = []
for L in links:
    m = re.search(r"w(\d{4})n(\d{4})\.laz$", L)
    if not m: continue
    x0, y0 = -int(m.group(1)) * 1000, int(m.group(2)) * 1000
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((x0, y0), (x0 + 1000, y0), (x0 + 1000, y0 + 1000), (x0, y0 + 1000), (x0, y0)): ring.AddPoint(x, y)
    tile = ogr.Geometry(ogr.wkbPolygon); tile.AddGeometry(ring)
    if tile.Intersects(aoi_alb): need.append(L)
need = sorted(set(need)); open(os.path.join(RAW, "usgs_tiles.txt"), "w").write("\n".join(need))
print(f"  {len(need)} tiles intersect the AOI", flush=True)
if "--download" in sys.argv:
    for i, L in enumerate(need, 1):
        dst = os.path.join(LAZ, L.split("/")[-1])
        if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000: print(f"  [{i}/{len(need)}] have {os.path.basename(dst)}", flush=True); continue
        for attempt in range(4):
            try: urllib.request.urlretrieve(L, dst + ".part"); os.replace(dst + ".part", dst); break
            except Exception as ex: print("   retry", os.path.basename(dst), ex, flush=True); time.sleep(15)
        print(f"  [{i}/{len(need)}] {os.path.basename(dst)} {os.path.getsize(dst)/1e6:.0f} MB", flush=True)
print("done")
