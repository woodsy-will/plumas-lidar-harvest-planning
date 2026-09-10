"""02c_relief_tint.py - one pre-composed relief-tint raster for the unit sheets.

Cartographic rule (Patterson, shadedrelief.com; Esri design principles): the base must recede so the units read as
the figure. Shadow values are held to 62 % luminosity, inside Patterson's 70 % floor, the class tints are pale and desaturated, and the hillshade is
multiplied into the tint once here rather than blended in the layout, so the map export stays vector and no
translucent fill can blend into a third color. Output data/work/relief_tint.tif, RGBA, 3 ft cells.
Run: python-qgis-ltr.bat scripts/02c_relief_tint.py
"""
import os

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "data", "work")
# pale tints of the Okabe-Ito hues used everywhere else (ground-based green, marginal yellow, cable vermillion)
TINT = {1: (206, 232, 222), 2: (248, 241, 190), 3: (243, 205, 178)}
SHADOW_MAX = 0.62     # darkest a shadow may go (1 = no darkening); shadow values are held to 62 % luminosity, inside Patterson's 70 % floor

hs_ds = gdal.Open(os.path.join(WORK, "hillshade.tif")); hs = hs_ds.GetRasterBand(1).ReadAsArray().astype("float32")
yc_ds = gdal.Open(os.path.join(WORK, "yarding_class.tif")); yc = yc_ds.GetRasterBand(1).ReadAsArray()
valid = hs > 0
lum = 1.0 - (1.0 - SHADOW_MAX) * (1.0 - hs / 255.0)          # 1 in full light, SHADOW_MAX in full shadow
lum = np.clip(lum, SHADOW_MAX, 1.0)
rgb = np.zeros(hs.shape + (3,), dtype="float32")
for k, c in TINT.items():
    m = yc == k
    for i in range(3):
        rgb[..., i][m] = c[i]
none = valid & ~np.isin(yc, list(TINT))                          # hillshade where no class (outside the DTM or nodata class)
for i in range(3):
    rgb[..., i][none] = 235
out = np.clip(rgb * lum[..., None], 0, 255).astype("uint8")
alpha = np.where(valid, 255, 0).astype("uint8")

drv = gdal.GetDriverByName("GTiff"); dst = os.path.join(WORK, "relief_tint.tif")
ds = drv.Create(dst, hs_ds.RasterXSize, hs_ds.RasterYSize, 4, gdal.GDT_Byte, options=["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "PHOTOMETRIC=RGB", "ALPHA=YES"])
ds.SetGeoTransform(hs_ds.GetGeoTransform()); ds.SetProjection(hs_ds.GetProjection())
for i in range(3):
    ds.GetRasterBand(i + 1).WriteArray(out[..., i])
ds.GetRasterBand(4).WriteArray(alpha); ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
ds.BuildOverviews("AVERAGE", [2, 4, 8, 16]); ds = None
print("relief tint written:", dst, round(os.path.getsize(dst) / 1e6, 1), "MB; luminosity range", float(lum[valid].min()), "to", float(lum[valid].max()))
