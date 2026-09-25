"""05_unit_maps.py - 11x17 unit map series and sale overview with PyQGIS.

One landscape 11x17 page per unit: hillshade with yarding-class tint, the unit and its neighbors, riparian
conservation areas, streams by class, NFS roads, selected landings and feasible skyline corridors, PLSS
sections, a unit panel (terrain, stand and yarding attributes), legend, scale bar, locator inset and a
sources / disclaimer block. Plus an overview sheet of the whole block with a unit table.

Outputs output/maps/Unit_<id>.pdf and Overview.pdf (print PDF: vector text, rasters at 300 dpi), output/maps/geopdf/
        copies at 200 dpi for Avenza, .png at 150 dpi, and the merged output/maps/Unit_Map_Series.pdf
Run: python-qgis-ltr.bat scripts/05_unit_maps.py
"""
import csv
import os
import sys

from qgis.core import (QgsLayoutMeasurement, QgsCoordinateTransform, QgsMapLayerLegendUtils, QgsLegendStyle, QgsApplication, QgsCoordinateReferenceSystem, QgsFillSymbol, QgsLayoutExporter, QgsLayoutItemLabel,
                       QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutPoint,
                       QgsLayoutSize, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings, QgsPrintLayout, QgsProject,
                       QgsRasterLayer, QgsTextFormat, QgsUnitTypes, QgsVectorLayer, QgsVectorLayerSimpleLabeling, QgsLayoutItemMapOverview,
                       QgsLayoutItemPage, QgsCategorizedSymbolRenderer, QgsRendererCategory,
                       QgsSimpleFillSymbolLayer, QgsLinePatternFillSymbolLayer)
from qgis.core import QgsRenderContext, QgsGeometry, QgsSimpleLineSymbolLayer
from qgis.core import QgsTextBackgroundSettings, QgsSimpleLineCallout, Qgis, QgsLayoutItemMapGrid, QgsLayoutItemShape
from qgis.PyQt.QtCore import Qt, QSizeF
from qgis.PyQt.QtGui import QColor, QFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, WORK, OUT = (os.path.join(ROOT, p) for p in (os.path.join("data", "raw"), os.path.join("data", "work"), os.path.join("output", "maps")))
os.makedirs(OUT, exist_ok=True)
CRS = QgsCoordinateReferenceSystem("EPSG:2226")
import datetime
TITLE = "Mohawk Valley West Slope Unit Planning Map"
DATE = datetime.date.today().strftime("%B %d, %Y"); SHEET = [1, 1]
DECL = "12.9 deg E"   # short in the margin; the model, epoch and drift are cited in the sources block
SUBTITLE = "Demonstration from public data (USGS 3DEP LiDAR 2018, USFS EDW, NHD, BLM). Not a Forest Service proposal."

QgsApplication.setPrefixPath(r"C:\Program Files\QGIS 3.44.12\apps\qgis-ltr", True)
app = QgsApplication([], False); app.initQgis()
proj = QgsProject.instance(); proj.setCrs(CRS)
md = proj.metadata(); md.setTitle("Mohawk Valley West Slope unit planning map (demonstration from public data)"); md.setAuthor("William Steinley"); proj.setMetadata(md)
GEO = os.path.join(OUT, "geopdf"); os.makedirs(GEO, exist_ok=True)


def vl(path, layer, name, crs=None):
    lyr = QgsVectorLayer(f"{path}|layername={layer}" if layer else path, name, "ogr")
    if not lyr.isValid():
        raise RuntimeError("bad layer " + name)
    if crs:
        lyr.setCrs(crs)
    return lyr


def rl(path, name):
    lyr = QgsRasterLayer(path, name)
    if not lyr.isValid():
        raise RuntimeError(f"bad raster {os.path.basename(path)}" + (" - run 02c_relief_tint.py first" if path.endswith("relief_tint.tif") else ""))
    return lyr


def fill(color, outline="0,0,0,0", width=0.0, style="solid"):
    return QgsFillSymbol.createSimple({"color": color, "outline_color": outline, "outline_width": str(width), "style": style})


def hatch(color, outline, angle=135, dist=2.0, lw=0.3, ow=1.0):
    """Line-pattern fill in a solid color: identifiable over the yarding-class tints and under color-vision deficiency,
    where a translucent solid fill blends into a third color (blue over yellow read as green on the first drafts)."""
    s = QgsFillSymbol(); s.deleteSymbolLayer(0)
    pat = QgsLinePatternFillSymbolLayer(); pat.setLineAngle(angle); pat.setDistance(dist); pat.setLineWidth(lw); pat.setColor(QColor(*color)); s.appendSymbolLayer(pat)
    edge = QgsSimpleFillSymbolLayer(); edge.setFillColor(QColor(0, 0, 0, 0)); edge.setStrokeColor(QColor(*outline)); edge.setStrokeWidth(ow); s.appendSymbolLayer(edge)
    return s


def cased_outline(inner=(0, 0, 0), outer=(255, 255, 255), wi=1.3, wo=3.0):
    s = QgsFillSymbol(); s.deleteSymbolLayer(0)
    for col, w in ((outer, wo), (inner, wi)):
        e = QgsSimpleFillSymbolLayer(); e.setFillColor(QColor(0, 0, 0, 0)); e.setStrokeColor(QColor(*col)); e.setStrokeWidth(w); s.appendSymbolLayer(e)
    return s


def unit_face(fill_rgb, line_rgb, casing=1.5, edge=0.5, hatch_angle=None, hatch_dist=2.4, hatch_lw=0.22):
    """Filled unit for the overview: method tint, a white casing, then the unit boundary on top. Two units of the same
    method share an edge, so without the casing the common boundary disappears into the fill; the casing reads as a
    white seam on both sides and each unit stays a separate figure (Forest Service sale area maps keep the cutting unit
    boundary as the strongest line on the sheet)."""
    s = QgsFillSymbol(); s.deleteSymbolLayer(0)
    face = QgsSimpleFillSymbolLayer(); face.setFillColor(QColor(*fill_rgb)); face.setStrokeStyle(Qt.NoPen); s.appendSymbolLayer(face)
    if hatch_angle is not None:   # cable units sit in the drainages and a flat blue tint there reads as water; the ruling marks them as treatment
        pat = QgsLinePatternFillSymbolLayer(); pat.setLineAngle(hatch_angle); pat.setDistance(hatch_dist); pat.setLineWidth(hatch_lw); pat.setColor(QColor(*line_rgb)); s.appendSymbolLayer(pat)
    cas = QgsSimpleFillSymbolLayer(); cas.setFillColor(QColor(0, 0, 0, 0)); cas.setStrokeColor(QColor(255, 255, 255, 235)); cas.setStrokeWidth(casing); s.appendSymbolLayer(cas)
    top = QgsSimpleFillSymbolLayer(); top.setFillColor(QColor(0, 0, 0, 0)); top.setStrokeColor(QColor(*line_rgb)); top.setStrokeWidth(edge); s.appendSymbolLayer(top)
    return s


def number_label(layer, size=7.5, callout=True):
    """Unit number in a circle, the sale-area-map callout. Short labels fit inside narrow units where a two-line
    'Unit 405 / Cable' block does not, and a leader line carries the few that still have to sit outside."""
    s = QgsPalLayerSettings(); s.fieldName = "unit_id"; s.isExpression = False; s.enabled = True
    f = QgsTextFormat(); f.setFont(QFont("Arial", int(size), QFont.Bold)); f.setSize(size); f.setColor(QColor(20, 20, 20))
    b = f.background(); b.setEnabled(True); b.setType(QgsTextBackgroundSettings.ShapeCircle)
    b.setFillColor(QColor(255, 255, 255, 235)); b.setStrokeColor(QColor(20, 20, 20)); b.setStrokeWidth(0.25)
    b.setSizeType(QgsTextBackgroundSettings.SizeBuffer); b.setSize(QSizeF(0.7, 0.7)); b.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    f.setBackground(b); s.setFormat(f)
    s.placement = QgsPalLayerSettings.Placement.Horizontal
    s.setPolygonPlacementFlags(Qgis.LabelPolygonPlacementFlags(Qgis.LabelPolygonPlacementFlag.AllowPlacementInsideOfPolygon | Qgis.LabelPolygonPlacementFlag.AllowPlacementOutsideOfPolygon))
    if callout:
        co = QgsSimpleLineCallout(); co.setEnabled(True); co.setLineSymbol(line("40,40,40,200", 0.2))
        co.setMinimumLength(0.6); co.setMinimumLengthUnit(QgsUnitTypes.RenderMillimeters); s.setCallout(co)
    layer.setLabelsEnabled(True); layer.setLabeling(QgsVectorLayerSimpleLabeling(s))


def line(color, width, style="solid"):
    return QgsLineSymbol.createSimple({"color": color, "width": str(width), "line_style": style, "capstyle": "round"})


def label(layer, expr, size=9, color="0,0,0", bold=True, buffer=True):
    s = QgsPalLayerSettings(); s.fieldName = expr; s.isExpression = True; s.enabled = True
    f = QgsTextFormat(); f.setFont(QFont("Arial", size, QFont.Bold if bold else QFont.Normal)); f.setSize(size); f.setColor(QColor(*[int(c) for c in color.split(",")]))
    if buffer:
        f.buffer().setEnabled(True); f.buffer().setSize(0.9); f.buffer().setColor(QColor(255, 255, 255))
    s.setFormat(f); layer.setLabelsEnabled(True); layer.setLabeling(QgsVectorLayerSimpleLabeling(s))


# ---- layers ----
gpkg = os.path.join(WORK, "planning.gpkg"); cable = os.path.join(WORK, "cable.gpkg")
hill = rl(os.path.join(WORK, "hillshade.tif"), "Hillshade (LiDAR DTM)"); hill.renderer().setOpacity(0.35)   # overview and inset: subdued grey base
relief = rl(os.path.join(WORK, "relief_tint.tif"), "Relief tint: yarding class from planning slope over the LiDAR hillshade")   # unit sheets: composed once in 02c
ycls = rl(os.path.join(WORK, "yarding_class.tif"), "Yarding Class by Planning Slope, over LiDAR Hillshade")   # legend swatches only
from qgis.core import QgsPalettedRasterRenderer
classes = [QgsPalettedRasterRenderer.Class(1, QColor(206, 232, 222), "Ground-based, Slope 35 % and Under"),
           QgsPalettedRasterRenderer.Class(2, QColor(248, 241, 190), "Marginal, 35 to 50 %"),
           QgsPalettedRasterRenderer.Class(3, QColor(243, 205, 178), "Cable, Over 50 %")]
ycls.setRenderer(QgsPalettedRasterRenderer(ycls.dataProvider(), 1, classes))
block = vl(os.path.join(RAW, "aoi.geojson"), None, "Community Protection Block Boundary (USFS)"); block.setSubsetString("role = 'treatment_block'")
block.renderer().setSymbol(fill("0,0,0,0", "0,0,0,255", 1.2)); block.renderer().symbol().symbolLayer(0).setStrokeStyle(Qt.DashLine)   # sale area boundary: heavy black dash
forest = vl(os.path.join(RAW, "blm_sma_usfs.geojson"), None, "National Forest (BLM SMA)"); forest.renderer().setSymbol(fill("209,229,209,255", "90,130,95,255", 0.3))
projects = vl(os.path.join(RAW, "facts_cp_project_areas.geojson"), None, "NEPA Project Areas (USFS EDW)"); projects.renderer().setSymbol(fill("120,140,120,120", "70,90,70,255", 0.3))
sections = vl(os.path.join(RAW, "plss_sections.geojson"), None, "PLSS Sections (BLM)"); sections.renderer().setSymbol(fill("0,0,0,0", "110,110,110,150", 0.25)); label(sections, "\"FRSTDIVNO\"", 7, "110,110,110", False)
rca = vl(gpkg, "rca_buffers", "Riparian Conservation Area, SNFPA Widths")
rca.renderer().setSymbol(fill("0,112,192,38", "0,112,192,90", 0.15))   # mapped only: a pale wash, so it never competes with the units (any lighter and the legend swatch reads as blank white)
eez = vl(gpkg, "eez_buffers", "Stream Equipment Exclusion Zone, Netted from Unit Acres")
eez.renderer().setSymbol(hatch((0, 112, 192), (0, 112, 192), angle=45, dist=1.2, lw=0.2, ow=0.25))
streams = vl(gpkg, "streams_aoi", "Streams (NHD)")
cats = []
for cls, name, w, st, col in (("perennial", "Perennial Stream", 0.7, "solid", "0,112,192,255"), ("intermittent", "Intermittent Stream", 0.4, "dash dot", "0,112,192,230"), ("ephemeral", "Ephemeral Draw", 0.25, "dot", "60,140,210,200"), ("other", "Other NHD", 0.4, "solid", "0,112,192,255")):
    sym = line(col, w, st)
    if cls == "perennial":   # white casing so the solid stream stays distinct from contour lines in grayscale
        cas = QgsSimpleLineSymbolLayer(); cas.setColor(QColor(255, 255, 255)); cas.setWidth(1.4); sym.insertSymbolLayer(0, cas)
    cats.append(QgsRendererCategory(cls, sym, name))   # USGS hydrography blue; class by line pattern, readable under any color vision
streams.setRenderer(QgsCategorizedSymbolRenderer("class", cats))
roads = vl(os.path.join(RAW, "fs_roads.geojson"), None, "NFS Roads (EDW Road Core)"); rsym = QgsLineSymbol(); rsym.deleteSymbolLayer(0)
for col, w in (((255, 255, 255, 230), 1.4), ((40, 40, 40, 255), 0.6)):
    sl = QgsSimpleLineSymbolLayer(); sl.setColor(QColor(*col)); sl.setWidth(w); sl.setPenCapStyle(Qt.RoundCap); rsym.appendSymbolLayer(sl)
roads.renderer().setSymbol(rsym); label(roads, "\"id\"", 7, "40,40,40", True)
tiger = vl(os.path.join(RAW, "tiger_roads.geojson"), None, "Local Roads (Census TIGER)"); tiger.renderer().setSymbol(line("90,90,90,255", 0.4, "dash"))
contours = vl(gpkg, "contours", "Contours, 40 ft, Index 200 ft")
ccats = [QgsRendererCategory(0, line("150,75,40,210", 0.22), "40 ft"), QgsRendererCategory(1, line("150,75,40,255", 0.45), "200 ft Index")]   # USGS contour brown, held back so the units lead
contours.setRenderer(QgsCategorizedSymbolRenderer("index", ccats)); contours.setSubsetString('"index" IN (0, 1)')   # "index" must be quoted: it is an SQL reserved word, and the unquoted filter silently returned no features
cl_s = QgsPalLayerSettings(); cl_s.fieldName = "round(\"elev\")"; cl_s.isExpression = True; cl_s.enabled = True; cl_s.placement = QgsPalLayerSettings.Line
cl_f = QgsTextFormat(); cl_f.setFont(QFont("Arial", 7)); cl_f.setSize(7); cl_f.setColor(QColor(140, 75, 40)); cl_f.buffer().setEnabled(True); cl_f.buffer().setSize(1.0); cl_s.setFormat(cl_f)
from qgis.core import QgsRuleBasedLabeling
cl_root = QgsRuleBasedLabeling.Rule(None); cl_rule = QgsRuleBasedLabeling.Rule(cl_s); cl_rule.setFilterExpression("\"index\" = 1"); cl_root.appendChild(cl_rule)
contours.setLabelsEnabled(True); contours.setLabeling(QgsRuleBasedLabeling(cl_root))
units = vl(gpkg, "units", "Harvest Unit Boundary by Yarding System"); SHEET[1] = sum(1 for _ in units.getFeatures()) + 1   # overview plus one sheet per unit (featureCount() can be -1 before the provider has counted)
# method colors: Okabe-Ito vermillion for tractor, blue for cable, green for hand thinning (dark for lines, pale for fills)
METHOD_COLORS = {"Tractor": ((213, 94, 0), (247, 205, 178)), "Cable": ((0, 90, 170), (176, 208, 234)), "Hand Thinning": ((0, 120, 90), (190, 228, 214))}
present = {f["method"] for f in units.getFeatures()}
# unit sheets: cased outline by method, interior open so the slope tint inside the unit stays readable (figure over a receded base)
ucats = [QgsRendererCategory(m, cased_outline(inner=o, outer=(255, 255, 255), wi=0.9, wo=2.2), m) for m, (o, f_) in METHOD_COLORS.items() if m in present]
units.setRenderer(QgsCategorizedSymbolRenderer("method", ucats)); number_label(units, 7.5)
from qgis.core import QgsLabelObstacleSettings
_ls = units.labeling().settings(); _ob = _ls.obstacleSettings(); _ob.setIsObstacle(True); _ob.setType(QgsLabelObstacleSettings.ObstacleType.PolygonBoundary); _ob.setFactor(2.0); _ls.setObstacleSettings(_ob); units.setLabeling(QgsVectorLayerSimpleLabeling(_ls))   # contour labels avoid unit outlines
# overview and inset: sale-area-map convention, units filled by method, each one cased so neighbours of the same method
# still read as separate cutting units, numbered in a circle with the method in the table and legend
units_plain = vl(gpkg, "units", "Harvest Units by Yarding System")
HATCH = {"Cable": 45}   # ruling by method: ground-based units plain, cable units ruled, so method survives a grey print and color-vision deficiency
pcats = [QgsRendererCategory(m, unit_face(f_ + (255,), o + (255,), hatch_angle=HATCH.get(m)), m) for m, (o, f_) in METHOD_COLORS.items() if m in present]
units_plain.setRenderer(QgsCategorizedSymbolRenderer("method", pcats)); number_label(units_plain, 7.5)
units_inset = vl(gpkg, "units", "units_inset")   # same fills, thinner casing: the locator is 55 mm wide and the overview weights would close the gaps
units_inset.setRenderer(QgsCategorizedSymbolRenderer("method", [QgsRendererCategory(m, unit_face(f_ + (255,), o + (255,), casing=0.45, edge=0.18, hatch_angle=HATCH.get(m), hatch_dist=1.2, hatch_lw=0.12), m) for m, (o, f_) in METHOD_COLORS.items() if m in present]))
cur = vl(gpkg, "units", "This Unit"); cur.renderer().setSymbol(cased_outline(wi=1.6, wo=3.6))
have_cable = os.path.exists(cable)
if have_cable:
    corr = vl(cable, "corridors", "Feasible Skyline Corridors from Selected Landings, Yarded toward Landing"); corr.setSubsetString("feasible = 1"); corr.renderer().setSymbol(line("0,0,0,205", 0.35))   # the corridors are the analysis result on a unit sheet: dark enough to read over the slope tint
    landings = vl(cable, "landings", "Selected Landings on Roads, This Unit"); landings.setSubsetString("corridors_ok > 0")
    landings.renderer().setSymbol(QgsMarkerSymbol.createSimple({"name": "triangle", "color": "240,228,66,255", "outline_color": "0,0,0,255", "size": "2.8"}))
layers = [cur, units] + ([landings, corr] if have_cable else []) + [roads, tiger, streams, contours, eez, rca, sections, block, relief]
proj.addMapLayer(units_plain, False); proj.addMapLayer(units_inset, False); proj.addMapLayer(forest, False); proj.addMapLayer(projects, False)
for l in layers:
    proj.addMapLayer(l, False)
root = proj.layerTreeRoot()
for l in layers:
    root.addLayer(l)

block_ext = QgsCoordinateTransform(block.crs(), CRS, proj).transformBoundingBox(block.extent())   # block layer is EPSG:4326
# township / range label from the PLSS townships intersecting the block
twp = vl(os.path.join(RAW, "plss_townships.geojson"), None, "twp"); twp_names = [x.name() for x in twp.fields()]
to_twp = QgsCoordinateTransform(CRS, twp.crs(), proj)


def trs_text(geom=None):
    """Township and range in the T21N R12E form for the townships a geometry (EPSG:2226) touches; whole block when None."""
    labs = set()
    g = QgsGeometry(geom) if geom is not None else QgsGeometry.fromRect(block_ext); g.transform(to_twp)
    for f in twp.getFeatures():
        d = dict(zip(twp_names, f.attributes())); lab = str(d.get("TWNSHPLAB") or d.get("twnshplab") or "")
        if lab and f.geometry().intersects(g):
            parts = lab.split(); labs.add(f"T{parts[0]} R{parts[1]}" if len(parts) == 2 else lab)
    return (", ".join(sorted(labs)) + ", MDB&M.  " if labs else "") + "Plumas National Forest, Plumas County, California"
summary = {}
sp = os.path.join(ROOT, "output", "cable", "unit_summary.csv")
if os.path.exists(sp):
    for r in csv.DictReader(open(sp)):
        summary[int(r["unit_id"])] = r


def add_label(layout, text, x, y, w, h, size=10, bold=False, halign=Qt.AlignLeft, frame=False):
    lab = QgsLayoutItemLabel(layout); lab.setText(text); f = QFont("Arial", size); f.setBold(bold); lab.setFont(f)
    lab.setHAlign(halign); lab.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters)); lab.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    lab.setFrameEnabled(frame); layout.addLayoutItem(lab); return lab


def make_layout(name, feat=None, extent=None, scale=None):
    layout = QgsPrintLayout(proj); layout.initializeDefaults(); layout.setName(name)
    page = layout.pageCollection().page(0); page.setPageSize("ANSI B", QgsLayoutItemPage.Landscape)   # 17 x 11 in = 431.8 x 279.4 mm
    W, H = 431.8, 279.4
    m = QgsLayoutItemMap(layout); m.setKeepLayerSet(True); m.setLayers(layers if feat is not None else [units_plain, roads, tiger, streams, eez, rca, sections, block, hill])
    m.attemptMove(QgsLayoutPoint(8, 22, QgsUnitTypes.LayoutMillimeters)); m.attemptResize(QgsLayoutSize(300, 226, QgsUnitTypes.LayoutMillimeters)); m.setFrameEnabled(True)
    m.setCrs(CRS)
    if extent is not None:
        m.zoomToExtent(extent)
    if scale:
        m.setScale(scale)
    layout.addLayoutItem(m)
    # State Plane grid: ticks in the frame with eastings along the bottom and northings up the left side, so a
    # position read off a GPS can be put on the paper sheet. Interval is the round number that gives about six
    # divisions across the 300 mm map at whatever scale the sheet was fitted to.
    span_ft = m.scale() * (300 / 304.8)
    iv = min(x for x in (500, 1000, 2000, 2500, 5000, 10000, 20000) if x >= span_ft / 6.5)
    gr = QgsLayoutItemMapGrid("State Plane grid", m)
    gr.setEnabled(True); gr.setCrs(CRS); gr.setUnits(QgsLayoutItemMapGrid.MapUnit)
    gr.setIntervalX(iv); gr.setIntervalY(iv)
    gr.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly)          # no lines across the map face: the units stay the figure
    gr.setFrameStyle(QgsLayoutItemMapGrid.InteriorTicks); gr.setFrameWidth(1.6); gr.setFramePenSize(0.2)
    gr.setAnnotationEnabled(True); gr.setAnnotationPrecision(0)
    # values in thousands of feet, the USGS quad convention: a seven-digit number inside the frame is wide enough to
    # print across a unit number, and the first sweep of all 25 sheets caught it doing exactly that
    gr.setAnnotationFormat(QgsLayoutItemMapGrid.CustomFormat)
    gr.setAnnotationExpression('format_number(@grid_number / 1000, 0)')
    gf = QgsTextFormat(); gf.setFont(QFont("Arial", 6)); gf.setSize(6); gf.setColor(QColor(70, 70, 70))
    gf.buffer().setEnabled(True); gf.buffer().setSize(1.0); gf.buffer().setColor(QColor(255, 255, 255))
    gr.setAnnotationTextFormat(gf)
    gr.setAnnotationFrameDistance(0.6)
    gr.setAnnotationDisplay(QgsLayoutItemMapGrid.LongitudeOnly, QgsLayoutItemMapGrid.Bottom)
    gr.setAnnotationPosition(QgsLayoutItemMapGrid.InsideMapFrame, QgsLayoutItemMapGrid.Bottom)
    gr.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Bottom)
    gr.setAnnotationDisplay(QgsLayoutItemMapGrid.LatitudeOnly, QgsLayoutItemMapGrid.Left)
    gr.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Left)   # the page margin is free
    gr.setAnnotationDirection(QgsLayoutItemMapGrid.VerticalDescending, QgsLayoutItemMapGrid.Left)
    for border in (QgsLayoutItemMapGrid.Top, QgsLayoutItemMapGrid.Right):
        gr.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, border)   # one set of numbers is enough on a sheet this busy
    m.grids().addGrid(gr); m.updateBoundingRect()
    # the grid numbers sit in the bottom of the frame, and a unit number placed hard against that edge printed
    # straight through one on sheet 110. An invisible strip along the bottom keeps map labels off the numbers;
    # a unit pushed inward keeps its leader back to its own polygon.
    guard = QgsLayoutItemShape(layout); guard.setShapeType(QgsLayoutItemShape.Rectangle)
    guard.attemptMove(QgsLayoutPoint(8, 242.5, QgsUnitTypes.LayoutMillimeters)); guard.attemptResize(QgsLayoutSize(300, 5.5, QgsUnitTypes.LayoutMillimeters))
    guard.setSymbol(fill("0,0,0,0", "0,0,0,0", 0)); layout.addLayoutItem(guard); m.addLabelBlockingItem(guard)
    add_label(layout, TITLE, 8, 5, 300, 9, 18, True)
    add_label(layout, SUBTITLE + f"   {trs_text(feat.geometry() if feat is not None else None)}", 8, 14, 300, 6, 8)
    # right panel
    px = 314; pw = 110
    if feat is not None:
        a = feat.attributes(); names = [f.name() for f in units.fields()]; d = dict(zip(names, a)); s = summary.get(int(d["unit_id"]), {})
        add_label(layout, f"UNIT {d['unit_id']}  -  {d['method'].upper()}", px, 22, pw, 9, 15, True)
        rows = [("Acres", f"{d['acres']:.1f}"), ("Mean slope", f"{d['slope_mean']:.0f} %  (98th pct {d['slope_max']:.0f} %)"), ("Aspect", d["aspect"]),
                ("Elevation", f"{d['elev_min']:.0f} - {d['elev_max']:.0f} ft"), ("Canopy cover", f"{d['cover_pct']:.0f} %  (66 ft window)"), ("Dominant height", f"{d['dom_ht']:.0f} ft  (unit mean of 66 ft p95 CHM)"),
                ("Nearest road", "road inside unit" if d["road_ft"] < 1 else f"{d['road_ft']:,.0f} ft  (NFS or local)")]
        if s and d["method"] == "Cable":
            rows += [("", ""), ("YARDING SCREEN", ""), ("Landings selected", f"{s['landings_used']} of {s['landings']} candidates"), ("Feasible corridors", f"{int(s['corridors_feasible']):,} of {int(s['corridors']):,}  (50 ft tower)"),
                     ("With 70 ft tower", f"{int(s['corridors_feasible_70ft']):,}"), ("Unit coverage", f"{s['coverage_pct']} %"), ("Mean deflection", f"{s['mean_deflection_pct']} %"),
                     ("Downhill yarding", f"{s['downhill_share_pct']} % of corridors"), ("Longest feasible span", f"{float(s['max_feasible_span_ft']):,.0f} ft"), ("Equipment class", s["equipment"]), ("Difficulty", s["difficulty"])]
            if s.get("payload_at_best_lb", "").strip():
                rows.append(("Allowable load", f"{float(s['payload_at_best_lb']):,.0f} lb  (7/8 in skyline, SF 3)"))   # best corridor by payload at the governing loaded deflection; method in docs/methods.md
        elif s:
            rows += [("", ""), ("YARDING SCREEN", ""), ("System", "Ground-based (slope <= 35 %)"), ("Skyline check", f"{int(s['corridors_feasible']):,} feasible corridors, {float(s['coverage_pct']):.0f} % corridor coverage if yarded by cable")]
        y = 34
        for k, v in rows:
            if k == "":
                y += 3; continue
            add_label(layout, k, px, y, 44, 6, 9, k.isupper()); add_label(layout, v, px + 44, y, pw - 44, 6, 9); y += 6
        ly = y + 4
    else:
        add_label(layout, "OVERVIEW", px, 22, pw, 9, 15, True)
        y = 34
        # fixed column positions (mm from px) so the proportional font cannot drift the columns
        cols = [(0, 8, Qt.AlignLeft), (8, 17, Qt.AlignLeft), (25, 12, Qt.AlignRight), (37, 12, Qt.AlignRight), (49, 12, Qt.AlignRight), (61, 12, Qt.AlignRight), (76, pw - 76, Qt.AlignLeft)]
        def row(vals, yy, size=7, bold=False):
            for (cx, cw, al), v in zip(cols, vals):
                add_label(layout, v, px + cx, yy, cw, 5, size, bold, al)
        row(["Unit", "System", "Gross ac", "Net ac", "Slope", "Canopy", "Skyline screen"], y, 7, True); y += 5
        tg = tn = 0.0
        for f in sorted(units.getFeatures(), key=lambda x: int(x["unit_id"])):
            dd = dict(zip([x.name() for x in units.fields()], f.attributes())); s = summary.get(int(dd["unit_id"]), {}); tg += round(dd["acres"], 2); tn += round(dd["net_acres"], 2)
            short = {"Small yarder": "small yarder", "Medium yarder": "medium yarder", "Long-span yarder": "long-span", "Intermediate support needed": "interm. support", "No feasible corridor": "no corridor"}
            # kept short: the column is pw - 76 = 34 mm at 7 pt, and "61 % coverage, interm. support" wrapped onto the next row
            scr = (f"{float(s.get('coverage_pct', 0)):.0f} %, {short.get(s.get('equipment', ''), s.get('equipment', ''))}" if dd["method"] == "Cable" else "ground-based") if s else ""
            row([str(dd["unit_id"]), dd["method"], f"{dd['acres']:.0f}", f"{dd['net_acres']:.0f}", f"{dd['slope_mean']:.0f}", f"{dd['cover_pct']:.0f}", scr], y); y += 4.2
        row(["Total", "", f"{int(round(tg, 2) + 0.5)}", f"{int(round(tn, 2) + 0.5)}", "", "", "24 units"], y + 1, 7, True); y += 5   # half-up so the total matches the review sheets
        add_label(layout, "Slope is mean planning slope, percent. Canopy is cover, percent. Net acres are gross less stream equipment exclusion zones. Unit acres rounded; totals from unrounded values. Skyline screen: corridor coverage, percent, and equipment class.", px, y, pw, 10, 6); y += 9
        ly = y + 4
    leg = QgsLayoutItemLegend(layout); leg.setTitle("Legend"); leg.setAutoUpdateModel(False); leg.setLinkedMap(m)
    mdl = leg.model().rootGroup(); mdl.clear()
    has_sel = bool(feat is not None and summary.get(int(feat["unit_id"]), {}).get("chosen_landings", ""))
    skip = {relief, sections} | (set() if (not have_cable or has_sel) else {landings, corr})
    for l in ([x for x in layers if x not in skip] + [ycls] if feat is not None else [units_plain, roads, tiger, streams, eez, rca, block]):
        node = mdl.addLayer(l)
        if l is ycls:                                            # hide the raster band-name node, keep the three classes
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, [1, 2, 3]); leg.model().refreshLayerLegend(node)
        if l is streams:                                         # drop the 'Other NHD' entry from the legend
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, [0, 1, 2]); leg.model().refreshLayerLegend(node)
    leg.setSymbolHeight(2.4); leg.setSymbolWidth(6); leg.setLineSpacing(0.4); leg.setBoxSpace(1.0)
    leg.setStyleMargin(QgsLegendStyle.Subgroup, QgsLegendStyle.Top, 2.0); leg.setStyleMargin(QgsLegendStyle.Symbol, QgsLegendStyle.Top, 1.4)
    for style, size in ((QgsLegendStyle.Title, 10), (QgsLegendStyle.Group, 8), (QgsLegendStyle.Subgroup, 8), (QgsLegendStyle.SymbolLabel, 7.5)):
        st = leg.style(style); fnt = QFont("Arial"); fnt.setPointSizeF(size); fnt.setBold(style in (QgsLegendStyle.Title, QgsLegendStyle.Subgroup)); st.setFont(fnt); leg.setStyle(style, st)
    leg.attemptMove(QgsLayoutPoint(px, ly, QgsUnitTypes.LayoutMillimeters)); leg.attemptResize(QgsLayoutSize(pw, 268 - ly, QgsUnitTypes.LayoutMillimeters)); layout.addLayoutItem(leg)
    sb = QgsLayoutItemScaleBar(layout); sb.setLinkedMap(m); sb.setStyle("Single Box"); sb.setUnits(QgsUnitTypes.DistanceFeet); sb.setUnitLabel("ft"); sb.setNumberOfSegments(2); sb.setNumberOfSegmentsLeft(0); sb.setUnitsPerSegment(500 if scale and scale <= 6000 else 1000 if scale and scale <= 12000 else 2000)
    sb.setHeight(2.5); sb.setLabelBarSpace(1); sb.attemptMove(QgsLayoutPoint(10, 250, QgsUnitTypes.LayoutMillimeters)); layout.addLayoutItem(sb)
    add_label(layout, f"Scale 1:{int(round(m.scale())):,}   Contours 40 ft   Grid north, CA State Plane Zone 2, ticks in 1,000 ft", 140, 251, 100, 6, 7)
    add_label(layout, f"Sheet {SHEET[0]} of {SHEET[1]}   {DATE}", 250, 251, 56, 6, 8, False, Qt.AlignRight); add_label(layout, "N", 247.8, 250.3, 5, 5, 7, True)
    add_label(layout, f"MN {DECL}", 233, 256.2, 22, 4, 6, False, Qt.AlignHCenter)   # declination under the north arrow, where a compass user looks for it
    north = QgsLayoutItemPicture(layout); north.setPicturePath(os.path.join(QgsApplication.prefixPath(), "svg", "arrows", "NorthArrow_04.svg")); north.attemptMove(QgsLayoutPoint(240.5, 248.5, QgsUnitTypes.LayoutMillimeters)); north.attemptResize(QgsLayoutSize(7, 7.5, QgsUnitTypes.LayoutMillimeters)); layout.addLayoutItem(north)
    if feat is not None:
        ins = QgsLayoutItemMap(layout); ins.setKeepLayerSet(True); ins.setLayers([cur, units_inset, block, hill]); ins.setCrs(CRS); ins.attemptMove(QgsLayoutPoint(251, 206, QgsUnitTypes.LayoutMillimeters)); ins.attemptResize(QgsLayoutSize(55, 35, QgsUnitTypes.LayoutMillimeters)); ins.setBackgroundEnabled(True); ins.setBackgroundColor(QColor(255, 255, 255)); ins.zoomToExtent(block_ext.buffered(1500)); ins.setFrameEnabled(True); ins.setFrameStrokeWidth(QgsLayoutMeasurement(0.5, QgsUnitTypes.LayoutMillimeters)); ins.setFrameStrokeColor(QColor(0, 0, 0)); m.addLabelBlockingItem(ins); ins.refresh()   # locator in the map corner so the panel legend can run to the footer; ins.zoomToExtent(block_ext.buffered(1500)); ins.setFrameEnabled(True)
        ov = QgsLayoutItemMapOverview("cur", ins); ov.setLinkedMap(m); ov.setFrameSymbol(fill("255,0,0,40", "255,0,0,255", 0.5)); ins.overviews().addOverview(ov); layout.addLayoutItem(ins)
    else:
        # the overview sheet had no locator at all: a reader could not place the block without reading the title.
        # Vicinity map in the empty west corner, block in red inside the Plumas National Forest and its project areas.
        vic = QgsLayoutItemMap(layout); vic.setKeepLayerSet(True); vic.setLayers([block, projects, forest]); vic.setCrs(CRS)   # no roads: at forest scale the TIGER network is a hairball and buries the project areas
        vic.attemptMove(QgsLayoutPoint(12, 26, QgsUnitTypes.LayoutMillimeters)); vic.attemptResize(QgsLayoutSize(58, 46, QgsUnitTypes.LayoutMillimeters))
        vic.setBackgroundEnabled(True); vic.setBackgroundColor(QColor(255, 255, 255))
        fx = forest.extent(); ct = QgsCoordinateTransform(forest.crs(), CRS, proj); fx = ct.transformBoundingBox(fx)
        vic.zoomToExtent(fx.buffered(3000))
        vic.setFrameEnabled(True); vic.setFrameStrokeWidth(QgsLayoutMeasurement(0.5, QgsUnitTypes.LayoutMillimeters)); vic.setFrameStrokeColor(QColor(0, 0, 0))
        m.addLabelBlockingItem(vic); vic.refresh(); layout.addLayoutItem(vic)
        vov = QgsLayoutItemMapOverview("block", vic); vov.setLinkedMap(m); vov.setFrameSymbol(fill("255,0,0,60", "255,0,0,255", 0.6)); vic.overviews().addOverview(vov)
        add_label(layout, "Vicinity: Plumas National Forest", 12, 72.4, 58, 4, 6)
    add_label(layout, "Sources: USGS 3DEP CA_NoCAL_Wildfires_PlumasNF 2018 (QL1); USFS EDW Activity Project Areas and Road Core; USGS NHD, 1:24,000; BLM SMA and PLSS; Census TIGER roads. "
                      "CA State Plane Zone 2, NAD83, US ft; grid ticks at the interval in the scale line. Magnetic declination from NOAA WMM-2025 at the block centre for September 2026, changing -0.1 deg per year. LiDAR flown 2018; roads, NEPA areas, ownership and hydrography as downloaded Sept 2026. Units delineated by the rules in docs/methods.md. "
                      "Planning map, not a proposal; no field verification. Wildlife, cultural and soils constraints not modeled. Symbology after Forest Service sale area maps: heavy dashed sale-area boundary, cased cutting-unit boundaries, unit numbers in circles with leaders, units over a light base, Okabe-Ito color-blind-safe palette, USGS hydrography and contour conventions. "
                      "GeoPDF copy of this sheet (output/maps/geopdf) opens in Avenza Maps with field position.",
              8, 262, 300, 14, 7)
    add_label(layout, "William Steinley, github.com/woodsy-will/plumas-lidar-harvest-planning", px, 266.5, pw, 6, 7, True, Qt.AlignRight)
    return layout, m


def export(layout, base):
    ex = QgsLayoutExporter(layout)
    # print PDF: text and linework stay vector (searchable, sharp at any size), rasters at 300 dpi, the print standard
    pdf = QgsLayoutExporter.PdfExportSettings(); pdf.dpi = 300; pdf.writeGeoPdf = False; pdf.textRenderFormat = QgsRenderContext.TextFormatAlwaysText
    ex.exportToPdf(os.path.join(OUT, base + ".pdf"), pdf)
    # field GeoPDF: QGIS rasterizes the whole sheet for GeoPDF, so 200 dpi keeps it under the 12 Mpx limit at which Avenza downsamples to 72 dpi
    geo = QgsLayoutExporter.PdfExportSettings(); geo.dpi = 200; geo.writeGeoPdf = True; geo.includeGeoPdfFeatures = False
    r = ex.exportToPdf(os.path.join(GEO, base + ".pdf"), geo)
    if r != QgsLayoutExporter.Success:
        print("  (GeoPDF export failed:", r, ")")
    img = QgsLayoutExporter.ImageExportSettings(); img.dpi = 150; ex.exportToImage(os.path.join(OUT, base + ".png"), img)
    print("  wrote", base)


# overview
cur.setSubsetString("unit_id = -1")
lay, m = make_layout("Overview", None, block_ext.buffered(600), scale=24000); export(lay, "Overview")   # the quadrangle scale
# per unit
pages = []
ONLY = {int(u) for u in os.environ.get("ONLY_UNITS", "").split()} if os.environ.get("ONLY_UNITS") else None   # ONLY_UNITS="404 101" renders a subset for design checks
for idx, f in enumerate(sorted(units.getFeatures(), key=lambda x: int(x["unit_id"])), start=2):
    uid = f["unit_id"]
    SHEET[0] = idx - 1                                                   # sheet number from the unit's position in the full list, so a subset run keeps the right number
    if ONLY and int(uid) not in ONLY:
        continue
    ext = f.geometry().boundingBox(); ext = ext.buffered(max(ext.width(), ext.height()) * 0.2 + 250)
    cur.setSubsetString(f"unit_id = {uid}")
    if have_cable:
        chosen = summary.get(int(uid), {}).get("chosen_landings", "").split()
        sel = " AND landing_id IN (" + ",".join(chosen) + ")" if chosen else ""
        corr.setSubsetString(f"feasible = 1 AND unit_id = {uid}{sel}"); landings.setSubsetString(f"unit_id = {uid}{sel if chosen else ' AND corridors_ok > 0'}")
    SHEET[0] = idx
    sc = max(ext.width() / (300 / 304.8), ext.height() / (226 / 304.8))   # scale that fits the extent in the 300 x 226 mm map (extent in US ft)
    sc = min(s for s in (2400, 3000, 3600, 4800, 6000, 7200, 9600, 12000, 15000, 20000) if s >= sc) if sc <= 20000 else sc   # readable round scale
    lay, m = make_layout(f"Unit {uid}", f, ext, scale=sc)
    export(lay, f"Unit_{uid}"); pages.append(os.path.join(OUT, f"Unit_{uid}.pdf"))
# merge
try:
    if ONLY:
        raise RuntimeError("subset run, no merge")
    from pypdf import PdfWriter
    w = PdfWriter()
    for p in [os.path.join(OUT, "Overview.pdf")] + pages:
        w.append(p)
    w.add_outline_item("Overview", 0)   # bookmarks: one per sheet so readers can jump by unit
    for i, p in enumerate(pages, start=1):
        w.add_outline_item("Unit " + os.path.basename(p)[5:-4], i)
    w.add_metadata({"/Title": "Mohawk Valley West Slope Unit Planning Map, 25-sheet series (demonstration from public data)", "/Author": "William Steinley", "/Creator": "PyQGIS 3.44 layout export, merged with pypdf"})
    w.write(os.path.join(OUT, "Unit_Map_Series.pdf")); print("merged", len(pages) + 1, "pages")
except Exception as e:
    print("merge skipped:", e)
app.exitQgis()
