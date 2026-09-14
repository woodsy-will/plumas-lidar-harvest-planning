"""08_package_gis.py - distributable GIS deliverable and metadata.

Bundles the vector products from planning.gpkg, cable.gpkg and cruise_plots.gpkg into one GeoPackage,
output/gis/mohawk_west_slope.gpkg, with a layer description on every layer (gpkg_contents.description) and a
project_metadata key / value summary table (not a gpkg_metadata ISO record), and writes four rasters (yarding class, planning slope, canopy cover, dominant height) alongside it
as compressed, tiled GeoTIFFs with overviews. docs/data_dictionary.md documents every layer and field.
Run: python-qgis-ltr.bat scripts/08_package_gis.py
"""
import datetime
import os
import shutil
import sqlite3

from osgeo import gdal, ogr

gdal.UseExceptions(); ogr.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK, OUT = os.path.join(ROOT, "data", "work"), os.path.join(ROOT, "output", "gis")
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
GPKG = os.path.join(OUT, "mohawk_west_slope.gpkg")

DESC = {
    "units": "Demonstration harvest units delineated by the rules in docs/methods.md; method Tractor / Cable / Hand Thinning; gross and net (EEZ removed) acres",
    "eez_buffers": "Stream equipment exclusion zones, 100 / 50 / 25 ft by NHD class, kept inside units and netted out",
    "rca_buffers": "Riparian conservation areas, 300 / 150 / 100 ft (Sierra Nevada Forest Plan Amendment) and 300 ft on waterbodies, mapped only",
    "streams_aoi": "NHD flowlines clipped to the area of interest with a perennial / intermittent / ephemeral class from FCode",
    "contours": "40 ft contours from the LiDAR DTM; index = 1 on 200 ft contours",
    "operable_mask": "Operable ground before splitting: treatment block, NFS land, stand present, planning slope <= 100 %, within 3,500 ft of a road",
    "landings": "Candidate cable landings sampled every 200 ft along roads within 500 ft of a unit (nearest road up to 2,000 ft as a fallback)",
    "corridors": "Skyline corridors cast from each landing every 5 degrees (10 for tractor units) to a tailhold 100 ft past the far boundary; straight 2D lines from landing to tailhold (the profile is sampled from the DTM in 04b)",
    "plots": "Simulated BAF 20 cruise plots on a 300 ft grid with QA flags; not field data",
}
SRC = [("planning.gpkg", ["units", "eez_buffers", "rca_buffers", "streams_aoi", "contours", "operable_mask"]), ("cable.gpkg", ["landings", "corridors"]), ("cruise_plots.gpkg", ["plots"])]
first = True
for gp, layers in SRC:
    for lyr in layers:
        out = gdal.VectorTranslate(GPKG, os.path.join(WORK, gp), layers=[lyr], accessMode=None if first else "update", format="GPKG"); out = None
        first = False
con = sqlite3.connect(GPKG); cur = con.cursor()
for lyr, d in DESC.items():
    cur.execute("UPDATE gpkg_contents SET description = ?, identifier = ? WHERE table_name = ?", (d, lyr, lyr))
cur.execute("CREATE TABLE IF NOT EXISTS project_metadata (key TEXT PRIMARY KEY, value TEXT)")
meta = [
    ("title", "Mohawk Valley West Slope: LiDAR-based harvest-unit planning (demonstration)"),
    ("abstract", "Harvest-unit layout, cable-yarding screen and simulated cruise for the Community Protection treatment block nearest Whitehawk Ranch, Plumas National Forest, computed from public data only."),
    ("purpose", "Portfolio demonstration of a planning workflow. Not a Forest Service proposal; no field verification."),
    ("author", "William Steinley"),
    ("date", datetime.date.today().isoformat()),                  # packaging date
    ("crs", "EPSG:2226 NAD83 / California zone 2 (US survey feet); vertical datum NAVD88, meters converted to US survey feet"),
    ("lidar", "USGS 3DEP CA_NoCAL_Wildfires_PlumasNF_B2_2018, QL1, flown 2018; read from the USGS Entwine copy; ~650 million points over 3,948 ac"),
    ("vector_sources", "USFS EDW Activity Project Areas and Road Core; BLM Surface Management Agency and CadNSDI PLSS; USGS NHD (1:24,000); Census TIGER roads (TIGER2024); all downloaded September 2026"),
    ("accuracy", "DTM at 3 ft cells from class 2 returns; planning slope from a 15 ft smoothed DTM averaged over 99 ft. Unit boundaries are model output, not surveyed lines. NHD stream classes are unverified."),
    ("lineage", "scripts 01 to 08 in github.com/woodsy-will/plumas-lidar-harvest-planning; rules and thresholds in docs/methods.md"),
    ("constraints", "Public-domain inputs. Units, corridors and plots are demonstration products and must not be used for operations."),
]
cur.executemany("INSERT OR REPLACE INTO project_metadata VALUES (?, ?)", meta); con.commit(); con.close()

for name in ("yarding_class", "slope_plan_pct", "canopy_cover_66ft", "dom_height_66ft"):
    dst = os.path.join(OUT, name + ".tif")
    src = os.path.join(WORK, name + ".tif"); co = ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BIGTIFF=IF_SAFER"]
    if name == "yarding_class":                                   # class codes 1 to 3: Byte with 0 as nodata; the others stay Float32
        gdal.Translate(dst, src, creationOptions=co, outputType=gdal.GDT_Byte, noData=0)
    else:
        gdal.Translate(dst, src, creationOptions=co)
    ds = gdal.Open(dst, gdal.GA_Update); ds.BuildOverviews("AVERAGE" if name != "yarding_class" else "NEAREST", [2, 4, 8, 16]); ds = None
    print(" ", name, round(os.path.getsize(dst) / 1e6, 1), "MB")
ds = ogr.Open(GPKG); print(GPKG, round(os.path.getsize(GPKG) / 1e6, 1), "MB;", [ (ds.GetLayer(i).GetName(), ds.GetLayer(i).GetFeatureCount()) for i in range(ds.GetLayerCount())])
