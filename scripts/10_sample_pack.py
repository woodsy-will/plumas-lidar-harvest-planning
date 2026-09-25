"""10_sample_pack.py - a small sample of the map series for people who will not download 190 MB.

Three sheets out of the twenty-five: the overview, one ground-based unit and one cable unit, merged with
bookmarks, plus the Avenza GeoPDF of the cable unit so the sample can be opened in the field. Everything comes
from output/maps, so this only runs after 05_unit_maps.py.

Outputs output/maps/sample/Sample_Sheets.pdf and Sample_Unit_404_GeoPDF.pdf
Run: python-qgis-ltr.bat scripts/10_sample_pack.py
"""
import os
import shutil

from pypdf import PdfWriter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPS = os.path.join(ROOT, "output", "maps")
OUT = os.path.join(MAPS, "sample")
os.makedirs(OUT, exist_ok=True)

SHEETS = [("Overview.pdf", "Overview, all 24 units"),
          ("Unit_101.pdf", "Unit 101, tractor"),
          ("Unit_404.pdf", "Unit 404, cable")]

missing = [s for s, _ in SHEETS if not os.path.exists(os.path.join(MAPS, s))]
if missing:
    raise SystemExit("run 05_unit_maps.py first, missing: " + ", ".join(missing))

w = PdfWriter()
for i, (sheet, title) in enumerate(SHEETS):
    w.append(os.path.join(MAPS, sheet))
    w.add_outline_item(title, i)
w.add_metadata({"/Title": "Mohawk Valley West Slope unit planning map, 3-sheet sample (demonstration from public data)",
                "/Author": "William Steinley",
                "/Creator": "PyQGIS 3.44 layout export, merged with pypdf",
                "/Subject": "Sample of the 25-sheet series. Full series and Avenza GeoPDFs are on the v1.1 release."})
dst = os.path.join(OUT, "Sample_Sheets.pdf")
w.write(dst)

geo_src = os.path.join(MAPS, "geopdf", "Unit_404.pdf")
geo_dst = os.path.join(OUT, "Sample_Unit_404_GeoPDF.pdf")
if os.path.exists(geo_src):
    shutil.copy2(geo_src, geo_dst)

for f in sorted(os.listdir(OUT)):
    print(f"  {f:34s} {os.path.getsize(os.path.join(OUT, f)) / 1e6:5.1f} MB")
