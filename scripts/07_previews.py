"""07_previews.py - JPEG previews and a review contact sheet for the portfolio.

Renders the overview and every unit sheet to JPEG (site-friendly), copies the cable figures, review sheet
first pages and quicklooks into output/previews, and writes output/previews/INDEX.md listing everything.
Run: python-qgis-ltr.bat scripts/07_previews.py
"""
import glob
import os
import shutil

import pymupdf
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output"); PV = os.path.join(OUT, "previews")
shutil.rmtree(PV, ignore_errors=True); os.makedirs(PV, exist_ok=True)   # start clean so stale previews never survive a rerun
lines = ["# Preview index", ""]


def pdf_to_jpg(pdf, dst, dpi=110, page=0):
    with pymupdf.open(pdf) as d:
        pix = d[page].get_pixmap(dpi=dpi)
    pix.save(dst.replace(".jpg", ".png"))
    Image.open(dst.replace(".jpg", ".png")).convert("RGB").save(dst, quality=88, optimize=True, subsampling=0); os.remove(dst.replace(".jpg", ".png"))


lines.append("## Map series (11x17)")
for pdf in sorted(glob.glob(os.path.join(OUT, "maps", "*.pdf"))):
    base = os.path.splitext(os.path.basename(pdf))[0]
    if base == "Unit_Map_Series":
        continue
    dst = os.path.join(PV, f"map_{base}.jpg"); pdf_to_jpg(pdf, dst); lines.append(f"- map_{base}.jpg")
lines.append("\n## Cable-yarding figures")
for png in sorted(glob.glob(os.path.join(OUT, "cable", "*.png"))):
    dst = os.path.join(PV, "cable_" + os.path.basename(png).replace(".png", ".jpg"))
    im = Image.open(png).convert("RGB"); im.thumbnail((2400, 2400)); im.save(dst, quality=88, optimize=True, subsampling=0); lines.append(f"- {os.path.basename(dst)}")   # web size: 2,400 px long edge
lines.append("\n## Field data review sheets (page 1)")
for pdf in sorted(glob.glob(os.path.join(OUT, "review", "Unit_*_Review.pdf"))):
    dst = os.path.join(PV, "review_" + os.path.basename(pdf).replace(".pdf", ".jpg")); pdf_to_jpg(pdf, dst, dpi=90); lines.append(f"- {os.path.basename(dst)}")
lines.append("\n## Terrain quicklooks")
for png in sorted(glob.glob(os.path.join(OUT, "quicklooks", "*.png"))):
    dst = os.path.join(PV, "terrain_" + os.path.basename(png).replace(".png", ".jpg"))
    im = Image.open(png).convert("RGB"); im.thumbnail((2400, 2400)); im.save(dst, quality=88, optimize=True, subsampling=0); lines.append(f"- {os.path.basename(dst)}")
open(os.path.join(PV, "INDEX.md"), "w").write("\n".join(lines) + "\n")
print("previews:", len(os.listdir(PV)) - 1)
