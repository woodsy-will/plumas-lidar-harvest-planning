"""ept_fetch.py - pull the AOI's points from the USGS Entwine (EPT) copy of the 2018 Plumas LiDAR on Amazon.

The staged LAZ tiles on rockyweb.usgs.gov serve at a few hundred KB/s; the Entwine octree of the same survey on
s3://usgs-lidar-public serves at many MB/s. This walks the EPT hierarchy, selects every node whose cube
intersects the AOI, downloads those node files (each is a plain LAZ) in parallel, and writes the list for
02_build_terrain.py. Point cloud content is identical to the tiles; only the container differs.

Usage: python-qgis-ltr.bat scripts/ept_fetch.py [--probe]     (--probe only indexes and times one node)
"""
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

from osgeo import ogr, osr

osr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "data", "work"); NODES = os.path.join(ROOT, "data", "raw", "ept"); os.makedirs(NODES, exist_ok=True); os.makedirs(WORK, exist_ok=True)
PROJECT = "CA_NoCAL_Wildfires_PlumasNF_B2_2018"
BASE = f"https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{PROJECT}/"
UA = {"User-Agent": "plumas-lidar-harvest-planning (github.com/woodsy-will)"}


def get(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


ept = json.loads(get(BASE + "ept.json"))
b = ept["bounds"]
print("srs:", ept["srs"].get("horizontal"), "| points:", f"{ept['points']:,}", "| span:", ept["span"], "| data:", ept["dataType"])

aoi = json.load(open(os.path.join(ROOT, "data", "raw", "aoi.geojson")))
g = ogr.CreateGeometryFromJson(json.dumps([f for f in aoi["features"] if f["properties"]["role"] == "aoi"][0]["geometry"]))
s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s3857 = osr.SpatialReference(); s3857.ImportFromEPSG(3857); s3857.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
g.Transform(osr.CoordinateTransformation(s4326, s3857)); ax0, ax1, ay0, ay1 = g.GetEnvelope()
print("AOI EPSG:3857 bounds:", [round(v) for v in (ax0, ay0, ax1, ay1)])


def node_bounds(key):
    d, x, y, z = map(int, key.split("-")); size = (b[3] - b[0]) / (2 ** d)
    return b[0] + x * size, b[1] + y * size, b[0] + (x + 1) * size, b[1] + (y + 1) * size


def intersects(key):
    x0, y0, x1, y1 = node_bounds(key)
    return x1 >= ax0 and x0 <= ax1 and y1 >= ay0 and y0 <= ay1


selected = {}; pending = [json.loads(get(BASE + "ept-hierarchy/0-0-0-0.json"))]; files = 1
while pending:
    hh = pending.pop()
    for key, cnt in hh.items():
        if not intersects(key):
            continue
        if cnt == -1:
            pending.append(json.loads(get(BASE + f"ept-hierarchy/{key}.json"))); files += 1
        elif cnt > 0:
            selected[key] = cnt
depths = {}
for k in selected:
    depths[int(k.split("-")[0])] = depths.get(int(k.split("-")[0]), 0) + 1
print(f"hierarchy files: {files} | nodes intersecting AOI: {len(selected)} | points: {sum(selected.values()):,} | by depth: {dict(sorted(depths.items()))}")
json.dump(selected, open(os.path.join(WORK, "ept_nodes.json"), "w"))

big = max(selected, key=selected.get)
t = time.time(); data = get(BASE + f"ept-data/{big}.laz"); dt = time.time() - t
open(os.path.join(NODES, f"{big}.laz"), "wb").write(data)
est = len(data) / selected[big] * sum(selected.values()) / 1e9
print(f"largest node {big}: {len(data)/1e6:.1f} MB in {dt:.1f} s = {len(data)/1e6/dt:.1f} MB/s | estimated total {est:.2f} GB")
if "--probe" in sys.argv:
    sys.exit(0)


def fetch(key):
    dst = os.path.join(NODES, f"{key}.laz")
    if os.path.exists(dst) and os.path.getsize(dst) > 100:
        return key, os.path.getsize(dst), True
    for attempt in range(5):
        try:
            d = get(BASE + f"ept-data/{key}.laz"); open(dst + ".part", "wb").write(d); os.replace(dst + ".part", dst); return key, len(d), False
        except Exception as ex:
            time.sleep(5 * (attempt + 1)); err = ex
    raise RuntimeError(f"{key}: {err}")


t = time.time(); total = 0; done = 0
with cf.ThreadPoolExecutor(max_workers=12) as pool:
    for key, n, cached in pool.map(fetch, sorted(selected, key=selected.get, reverse=True)):
        total += n; done += 1
        if done % 100 == 0 or done == len(selected):
            print(f"  {done}/{len(selected)} nodes, {total/1e9:.2f} GB, {total/1e6/max(1, time.time()-t):.1f} MB/s", flush=True)
open(os.path.join(ROOT, "data", "work", "ept_nodes.txt"), "w").write("\n".join(os.path.join(NODES, f"{k}.laz") for k in selected))
print(f"done: {len(selected)} node files, {total/1e9:.2f} GB in {time.time()-t:.0f} s")
