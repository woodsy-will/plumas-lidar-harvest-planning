"""05_unit_maps.py - 11x17 unit map series and sale overview with PyQGIS.

One landscape 11x17 page per unit: hillshade with yarding-class tint, the unit and its neighbors, riparian
conservation areas, streams by class, NFS roads, selected landings and feasible skyline corridors, PLSS
sections, a unit panel (terrain, stand and yarding attributes), legend, scale bar, locator inset and a
sources / disclaimer block. Plus an overview sheet of the whole block with a unit table.

Outputs output/maps/Unit_<id>.pdf|.png, output/maps/Overview.pdf|.png, output/maps/Unit_Map_Series.pdf
Run: python-qgis-ltr.bat scripts\05_unit_maps.py
"""
import csv
import os
import sys

from qgis.core import (QgsCoordinateTransform, QgsMapLayerLegendUtils, QgsLegendStyle, QgsApplication, QgsCoordinateReferenceSystem, QgsFillSymbol, QgsLayoutExporter, QgsLayoutItemLabel,
                       QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutPoint,
                       QgsLayoutSize, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings, QgsPrintLayout, QgsProject,
                       QgsRasterLayer, QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer,
                       QgsSingleBandGrayRenderer, QgsContrastEnhancement, QgsRuleBasedRenderer, QgsSymbol, QgsTextFormat,
                       QgsUnitTypes, QgsVectorLayer, QgsVectorLayerSimpleLabeling, QgsRectangle, QgsLayoutItemMapOverview,
                       QgsLayoutItemShape, QgsLayoutItemPage, QgsLayerTreeLayer, QgsCategorizedSymbolRenderer, QgsRendererCategory,
                       QgsSimpleFillSymbolLayer, QgsLinePatternFillSymbolLayer, QgsFeatureRequest)
from qgis.core import QgsRenderContext, QgsGeometry
from qgis.PyQt.QtCore import QSizeF, Qt
from qgis.PyQt.QtGui import QColor, QFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, WORK, OUT = (os.path.join(ROOT, p) for p in (os.path.join("data", "raw"), os.path.join("data", "work"), os.path.join("output", "maps")))
os.makedirs(OUT, exist_ok=True)
CRS = QgsCoordinateReferenceSystem("EPSG:2226")
TITLE = "Mohawk Valley West Slope - Harvest Unit Planning"
SUBTITLE = "Demonstration from public data (USGS 3DEP LiDAR 2018, USFS EDW, NHD, BLM). Not a Forest Service proposal."

QgsApplication.setPrefixPath(r"C:\Program Files\QGIS 3.44.12\apps\qgis-ltr", True)
app = QgsApplication([], False); app.initQgis()
proj = QgsProject.instance(); proj.setCrs(CRS)
md = proj.metadata(); md.setTitle("Mohawk Valley West Slope - harvest unit planning (demonstration from public data)"); md.setAuthor("William Steinley"); proj.setMetadata(md)
GEO = os.path.join(OUT, "geopdf"); os.makedirs(GEO, exist_ok=True)


def vl(path, layer, name, crs=None):
    lyr = QgsVectorLayer(f"{path}|layername={layer}" if layer else path, name, "ogr")
    if not lyr.isValid():
        raise RuntimeError("bad layer " + name)
    if crs:
        lyr.setCrs(crs)
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
hill = QgsRasterLayer(os.path.join(WORK, "hillshade.tif"), "Hillshade (LiDAR DTM)")
ycls = QgsRasterLayer(os.path.join(WORK, "yarding_class.tif"), "Yarding class from planning slope")
from qgis.core import QgsPalettedRasterRenderer
classes = [QgsPalettedRasterRenderer.Class(1, QColor(0, 158, 115, 70), "Ground-based, slope <= 35 %"),
           QgsPalettedRasterRenderer.Class(2, QColor(240, 228, 66, 110), "Marginal, 35-50 %"),
           QgsPalettedRasterRenderer.Class(3, QColor(213, 94, 0, 110), "Cable, > 50 %")]
ycls.setRenderer(QgsPalettedRasterRenderer(ycls.dataProvider(), 1, classes)); ycls.renderer().setOpacity(0.55)
block = vl(os.path.join(RAW, "aoi.geojson"), None, "Community Protection treatment block (USFS)"); block.setSubsetString("role = 'treatment_block'")
block.renderer().setSymbol(fill("0,0,0,0", "190,0,0,255", 1.1)); block.renderer().symbol().symbolLayer(0).setStrokeStyle(Qt.DashLine)
sections = vl(os.path.join(RAW, "plss_sections.geojson"), None, "PLSS sections (BLM)"); sections.renderer().setSymbol(fill("0,0,0,0", "90,90,90,160", 0.3)); label(sections, "\"FRSTDIVNO\"", 7, "80,80,80", False)
rca = vl(gpkg, "rca_buffers", "Riparian conservation area (SNFPA widths)")
rca.renderer().setSymbol(fill("0,0,0,0", "0,114,178,255", 0.45)); rca.renderer().symbol().symbolLayer(0).setStrokeStyle(Qt.DashLine)
eez = vl(gpkg, "eez_buffers", "Stream equipment exclusion zone (inside units, netted out)")
eez.renderer().setSymbol(hatch((0, 114, 178), (0, 114, 178), angle=45, dist=1.0, lw=0.3, ow=0.3))
streams = vl(gpkg, "streams_aoi", "Streams (NHD)")
cats = []
for cls, name, w, st in (("perennial", "Perennial", 0.7, "solid"), ("intermittent", "Intermittent", 0.5, "dash"), ("ephemeral", "Ephemeral", 0.35, "dot"), ("other", "Other NHD", 0.4, "solid")):
    cats.append(QgsRendererCategory(cls, line("20,90,200,255", w, st), name))
streams.setRenderer(QgsCategorizedSymbolRenderer("class", cats))
roads = vl(os.path.join(RAW, "fs_roads.geojson"), None, "NFS roads (EDW Road Core)"); roads.renderer().setSymbol(line("60,60,60,255", 0.9, "dash")); label(roads, "\"id\"", 7, "60,60,60", False)
tiger = vl(os.path.join(RAW, "tiger_roads.geojson"), None, "Local roads (Census TIGER)"); tiger.renderer().setSymbol(line("110,110,110,255", 0.5, "dash"))
contours = vl(gpkg, "contours", "Contours, 40 ft (index 200 ft)")
ccats = [QgsRendererCategory(0, line("120,90,60,170", 0.18), "40 ft"), QgsRendererCategory(1, line("120,90,60,230", 0.42), "200 ft index")]
contours.setRenderer(QgsCategorizedSymbolRenderer("index", ccats)); contours.setSubsetString("index = 1 OR index = 0")
cl_s = QgsPalLayerSettings(); cl_s.fieldName = "round(\"elev\")"; cl_s.isExpression = True; cl_s.enabled = True; cl_s.placement = QgsPalLayerSettings.Line
cl_f = QgsTextFormat(); cl_f.setFont(QFont("Arial", 6)); cl_f.setSize(6); cl_f.setColor(QColor(110, 80, 50)); cl_f.buffer().setEnabled(True); cl_f.buffer().setSize(0.6); cl_s.setFormat(cl_f)
from qgis.core import QgsRuleBasedLabeling
cl_root = QgsRuleBasedLabeling.Rule(None); cl_rule = QgsRuleBasedLabeling.Rule(cl_s); cl_rule.setFilterExpression("\"index\" = 1"); cl_root.appendChild(cl_rule)
contours.setLabelsEnabled(True); contours.setLabeling(QgsRuleBasedLabeling(cl_root))
units = vl(gpkg, "units", "Harvest units (demonstration)")
# sale-map convention: units filled by yarding method (light for ground-based, dark hatched for skyline)
METHOD_COLORS = {"Tractor": ((230, 159, 0), (160, 100, 0)), "Cable": ((0, 114, 178), (0, 90, 170)), "Hand Thinning": ((0, 158, 115), (0, 120, 90))}   # Okabe-Ito fill, darker outline
present = {f["method"] for f in units.getFeatures()}
ucats = [QgsRendererCategory(m, hatch(c, o), m) for m, (c, o) in METHOD_COLORS.items() if m in present]
units.setRenderer(QgsCategorizedSymbolRenderer("method", ucats)); label(units, "concat('Unit ', \"unit_id\", '\\n', \"method\")", 9)
units_plain = vl(gpkg, "units", "Harvest units"); units_plain.setRenderer(QgsCategorizedSymbolRenderer("method", [QgsRendererCategory(m, fill("0,0,0,0", ",".join(str(v) for v in o) + ",255", 0.5), m) for m, (c, o) in METHOD_COLORS.items()]))
cur = vl(gpkg, "units", "This unit (black line, white casing)"); cur.renderer().setSymbol(cased_outline())
have_cable = os.path.exists(cable)
if have_cable:
    corr = vl(cable, "corridors", "Feasible skyline corridors from selected landings (logs travel toward the landing)"); corr.setSubsetString("feasible = 1"); corr.renderer().setSymbol(line("0,114,178,220", 0.35))
    landings = vl(cable, "landings", "Selected landings on roads, this unit"); landings.setSubsetString("corridors_ok > 0")
    landings.renderer().setSymbol(QgsMarkerSymbol.createSimple({"name": "triangle", "color": "240,228,66,255", "outline_color": "0,0,0,255", "size": "2.8"}))
layers = [cur, units] + ([landings, corr] if have_cable else []) + [roads, tiger, streams, eez, rca, sections, block, contours, ycls, hill]
proj.addMapLayer(units_plain, False)
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
    return (", ".join(sorted(labs)) + ", MDB&M  |  " if labs else "") + "Plumas National Forest, Plumas County, California"
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
    m = QgsLayoutItemMap(layout); m.setKeepLayerSet(True); m.setLayers(layers if feat is not None else [units, roads, tiger, streams, eez, rca, block, ycls, hill])
    m.attemptMove(QgsLayoutPoint(8, 22, QgsUnitTypes.LayoutMillimeters)); m.attemptResize(QgsLayoutSize(300, 226, QgsUnitTypes.LayoutMillimeters)); m.setFrameEnabled(True)
    m.setCrs(CRS)
    if extent is not None:
        m.zoomToExtent(extent)
    if scale:
        m.setScale(scale)
    layout.addLayoutItem(m)
    add_label(layout, TITLE, 8, 5, 300, 9, 18, True)
    add_label(layout, SUBTITLE + f"   {trs_text(feat.geometry() if feat is not None else None)}", 8, 14, 300, 6, 8)
    # right panel
    px = 314; pw = 110
    if feat is not None:
        a = feat.attributes(); names = [f.name() for f in units.fields()]; d = dict(zip(names, a)); s = summary.get(int(d["unit_id"]), {})
        add_label(layout, f"UNIT {d['unit_id']}  -  {d['method'].upper()}", px, 22, pw, 9, 15, True)
        rows = [("Acres", f"{d['acres']:.1f}"), ("Mean slope", f"{d['slope_mean']:.0f} %  (98th pct {d['slope_max']:.0f} %)"), ("Aspect", d["aspect"]),
                ("Elevation", f"{d['elev_min']:.0f} - {d['elev_max']:.0f} ft"), ("Canopy cover", f"{d['cover_pct']:.0f} %  (66 ft window)"), ("Dominant height", f"{d['dom_ht']:.0f} ft  (95th pct CHM)"),
                ("Nearest road", "road inside unit" if d["road_ft"] < 1 else f"{d['road_ft']:,.0f} ft  (NFS or local)")]
        if s and d["method"] == "Cable":
            rows += [("", ""), ("YARDING SCREEN", ""), ("Landings selected", f"{s['landings_used']} of {s['landings']} candidates"), ("Feasible corridors", f"{int(s['corridors_feasible']):,} of {int(s['corridors']):,}  (50 ft tower)"),
                     ("With 70 ft tower", f"{int(s['corridors_feasible_70ft']):,}"), ("Unit coverage", f"{s['coverage_pct']} %"), ("Mean deflection", f"{s['mean_deflection_pct']} %"),
                     ("Downhill yarding", f"{s['downhill_share_pct']} % of corridors"), ("Longest feasible span", f"{float(s['max_feasible_span_ft']):,.0f} ft"), ("Equipment class", s["equipment"]), ("Difficulty", s["difficulty"])]
        elif s:
            rows += [("", ""), ("YARDING SCREEN", ""), ("System", "Ground-based (slope <= 35 %)"), ("Skyline check", f"{int(s['corridors_feasible']):,} feasible corridors, {float(s['coverage_pct']):.0f} % corridor coverage if cable were required")]
        y = 34
        for k, v in rows:
            if k == "":
                y += 3; continue
            add_label(layout, k, px, y, 44, 6, 9, k.isupper()); add_label(layout, v, px + 44, y, pw - 44, 6, 9); y += 6
        ly = y + 4
    else:
        add_label(layout, "OVERVIEW", px, 22, pw, 9, 15, True)
        y = 34
        add_label(layout, "Unit  Method        Gross  Net ac  Slope  Canopy  Skyline screen", px, y, pw, 6, 8, True); y += 5
        tg = tn = 0.0
        for f in units.getFeatures():
            dd = dict(zip([x.name() for x in units.fields()], f.attributes())); s = summary.get(int(dd["unit_id"]), {}); tg += dd["acres"]; tn += dd["net_acres"]
            short = {"Small yarder": "small yarder", "Medium yarder": "medium yarder", "Long-span yarder": "long-span", "Intermediate support needed": "interm. support", "No feasible corridor": "no corridor"}
            scr = (f"{float(s.get('coverage_pct', 0)):.0f} % corridor coverage, {short.get(s.get('equipment', ''), s.get('equipment', ''))}" if dd["method"] == "Cable" else "ground-based") if s else ""
            add_label(layout, f"{dd['unit_id']:<5} {dd['method']:<13} {dd['acres']:5.0f}  {dd['net_acres']:5.0f}  {dd['slope_mean']:4.0f} %  {dd['cover_pct']:4.0f} %  {scr}", px, y, pw, 5, 7); y += 4.2
        add_label(layout, f"Total {'':<13} {tg:5.0f}  {tn:5.0f}    (net = gross less stream equipment exclusion zones)", px, y + 1, pw, 5, 7, True); y += 5
        ly = y + 4
    leg = QgsLayoutItemLegend(layout); leg.setTitle("Legend"); leg.setAutoUpdateModel(False); leg.setLinkedMap(m)
    mdl = leg.model().rootGroup(); mdl.clear()
    has_sel = bool(feat is not None and summary.get(int(feat["unit_id"]), {}).get("chosen_landings", ""))
    skip = {hill, sections} | (set() if (not have_cable or has_sel) else {landings, corr})
    for l in ([x for x in layers if x not in skip] if feat is not None else [units, roads, tiger, streams, eez, rca, block, ycls]):
        node = mdl.addLayer(l)
        if l is ycls:                                            # hide the raster band-name node, keep the three classes
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, [1, 2, 3]); leg.model().refreshLayerLegend(node)
        if l is streams:                                         # drop the 'Other NHD' entry from the legend
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, [0, 1, 2]); leg.model().refreshLayerLegend(node)
    leg.setSymbolHeight(2.4); leg.setSymbolWidth(6); leg.setLineSpacing(0.4); leg.setBoxSpace(1.0)
    leg.setStyleMargin(QgsLegendStyle.Subgroup, QgsLegendStyle.Top, 1.2); leg.setStyleMargin(QgsLegendStyle.Symbol, QgsLegendStyle.Top, 0.6)
    for style, size in ((QgsLegendStyle.Title, 10), (QgsLegendStyle.Group, 8), (QgsLegendStyle.Subgroup, 8), (QgsLegendStyle.SymbolLabel, 7.5)):
        st = leg.style(style); fnt = QFont("Arial"); fnt.setPointSizeF(size); fnt.setBold(style in (QgsLegendStyle.Title, QgsLegendStyle.Subgroup)); st.setFont(fnt); leg.setStyle(style, st)
    leg.attemptMove(QgsLayoutPoint(px, ly, QgsUnitTypes.LayoutMillimeters)); leg.attemptResize(QgsLayoutSize(pw, 100, QgsUnitTypes.LayoutMillimeters)); layout.addLayoutItem(leg)
    sb = QgsLayoutItemScaleBar(layout); sb.setLinkedMap(m); sb.setStyle("Single Box"); sb.setUnits(QgsUnitTypes.DistanceFeet); sb.setUnitLabel("ft"); sb.setNumberOfSegments(2); sb.setNumberOfSegmentsLeft(0); sb.setUnitsPerSegment(1000 if scale and scale <= 12000 else 2000)
    sb.setHeight(2.5); sb.setLabelBarSpace(1); sb.attemptMove(QgsLayoutPoint(10, 250, QgsUnitTypes.LayoutMillimeters)); layout.addLayoutItem(sb)
    north = QgsLayoutItemPicture(layout); north.setPicturePath(os.path.join(QgsApplication.prefixPath(), "svg", "arrows", "NorthArrow_02.svg")); north.attemptMove(QgsLayoutPoint(290, 226, QgsUnitTypes.LayoutMillimeters)); north.attemptResize(QgsLayoutSize(14, 18, QgsUnitTypes.LayoutMillimeters)); layout.addLayoutItem(north)
    if feat is not None:
        ins = QgsLayoutItemMap(layout); ins.setKeepLayerSet(True); ins.setLayers([cur, units_plain, block, hill]); ins.setCrs(CRS); ins.attemptMove(QgsLayoutPoint(px, 230, QgsUnitTypes.LayoutMillimeters)); ins.attemptResize(QgsLayoutSize(pw, 34, QgsUnitTypes.LayoutMillimeters)); ins.zoomToExtent(block_ext.buffered(1500)); ins.setFrameEnabled(True)
        ov = QgsLayoutItemMapOverview("cur", ins); ov.setLinkedMap(m); ov.setFrameSymbol(fill("255,0,0,40", "255,0,0,255", 0.5)); ins.overviews().addOverview(ov); layout.addLayoutItem(ins)
    add_label(layout, "Sources: USGS 3DEP CA_NoCAL_Wildfires_PlumasNF 2018 (QL1); USFS EDW Activity Project Areas and Road Core; USGS NHD; BLM SMA and PLSS; Census TIGER roads. "
                      "CA State Plane Zone 2, NAD83, US ft. Currency: LiDAR flown 2018; roads, NEPA areas, ownership and hydrography as downloaded Sept 2026; NHD at 1:24,000. Units delineated by the documented rules in docs/methods.md; "
                      "not a proposal, no field verification. Wildlife, cultural and soils constraints not modeled. Colors: Okabe-Ito color-blind-safe palette; unit fills are hatched so they stay readable over the slope tints. "
                      "A georeferenced copy of this sheet (GeoPDF, output/maps/geopdf) opens in Avenza Maps with field position.",
              8, 262, 300, 14, 7)
    add_label(layout, "William Steinley  -  github.com/woodsy-will/plumas-lidar-harvest-planning", px, 266.5, pw, 6, 7, True, Qt.AlignRight)
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
for f in units.getFeatures():
    uid = f["unit_id"]; ext = f.geometry().boundingBox(); ext = ext.buffered(max(ext.width(), ext.height()) * 0.2 + 250)
    cur.setSubsetString(f"unit_id = {uid}")
    if have_cable:
        chosen = summary.get(int(uid), {}).get("chosen_landings", "").split()
        sel = " AND landing_id IN (" + ",".join(chosen) + ")" if chosen else ""
        corr.setSubsetString(f"feasible = 1 AND unit_id = {uid}{sel}"); landings.setSubsetString(f"unit_id = {uid}{sel if chosen else ' AND corridors_ok > 0'}")
    lay, m = make_layout(f"Unit {uid}", f, ext)
    # keep a readable round scale
    sc = m.scale(); sc = min(s for s in (2400, 3000, 3600, 4800, 6000, 7200, 9600, 12000, 15000, 20000) if s >= sc) if sc <= 20000 else sc
    m.setScale(sc); m.setExtent(m.extent()); export(lay, f"Unit_{uid}"); pages.append(os.path.join(OUT, f"Unit_{uid}.pdf"))
# merge
try:
    from pypdf import PdfWriter
    w = PdfWriter()
    for p in [os.path.join(OUT, "Overview.pdf")] + pages:
        w.append(p)
    w.write(os.path.join(OUT, "Unit_Map_Series.pdf")); print("merged", len(pages) + 1, "pages")
except Exception as e:
    print("merge skipped:", e)
app.exitQgis()
