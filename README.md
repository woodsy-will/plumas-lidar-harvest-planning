# Mohawk Valley West Slope: LiDAR-based harvest-unit planning

A self-directed rebuild, on public data only, of the harvest-planning workflows I ran as a Forester III on the
Plumas National Forest Community Protection Project: LiDAR terrain and canopy products, harvest-unit layout,
cable-yarding feasibility, an 11x17 unit map series, and field-data quality review sheets.

**Framing, stated plainly.** I did this kind of work for a contractor on federal timber sales in this
landscape. The deliverables from that work belong to the contractor and the Forest Service, so none of them
appear here. Everything in this repository was written from scratch and computed from public sources.
The harvest units are demonstration polygons delineated by the documented rules in `docs/methods.md`;
they are not a Forest Service proposal, and no field verification has been done.

## Area

The Community Protection (Central and West Slope, decision signed 2025) treatment block on National Forest
land nearest Whitehawk Ranch, Clio, California: 1,816 acres on the west slope of Mohawk Valley, buffered
300 m for terrain context. The selection rule is deterministic in `scripts/01_get_data.py`.

## Public inputs

| Layer | Source |
|---|---|
| Treatment block | USFS EDW Activity Project Areas (NEPA) |
| Ownership | BLM Surface Management Agency, USFS layer |
| Roads | USFS EDW Road Core, supplemented by Census TIGER local roads |
| Streams, waterbodies | USGS National Hydrography Dataset |
| PLSS | BLM CadNSDI |
| LiDAR | USGS 3DEP CA_NoCAL_Wildfires_PlumasNF 2018, QL1, read from the USGS Entwine copy on Amazon |

## Results

### Terrain and canopy (3 ft cells, California State Plane Zone 2, US ft)

| | |
|---|---|
| Area processed | 3,948 ac, 650 million points |
| Elevation | 4,459 to 6,177 ft |
| Planning slope, median | 22 % |
| Ground below 35 % slope | 75 % of the area; 15 % marginal; 10 % cable ground above 50 % |
| Canopy cover, mean | 79 % |
| Canopy height, 95th percentile | 105 ft |

A raw 3 ft slope surface under this canopy averages 87 %, which is interpolation noise, not terrain. The
planning slope is computed from a smoothed DTM and averaged over 99 ft; that distinction decides every
yarding class in the project.

### Harvest units

24 demonstration units on 1,621 acres inside the 1,816 acre block.

| Method | Units | Acres | Mean slope |
|---|---|---|---|
| Tractor | 18 | 1,390 | 10 to 24 % |
| Cable | 6 | 231 | 42 to 54 % |

Units are 30 to 116 acres, split along ridges and draws, with stream equipment-exclusion zones kept inside
the boundary as an internal restriction and netted out of treatable acres.

### Cable-yarding screen

8,540 corridors were cast from 940 candidate road landings. For the six cable units:

| Unit | Acres | Feasible corridors | Coverage | Equipment class | Difficulty |
|---|---|---|---|---|---|
| 401 | 30 | 0 of 68 | 0 % | none from any road within 2,000 ft | High: needs a spur road or a different system |
| 402 | 39 | 182 of 374 | 70 % | long-span yarder | Moderate |
| 403 | 34 | 124 of 551 | 52 % | long-span yarder | Moderate |
| 404 | 51 | 205 of 2,022 | 61 % | intermediate support needed | Moderate |
| 405 | 43 | 261 of 1,464 | 42 % | medium yarder | Moderate |
| 406 | 35 | 9 of 41 | 70 % | long-span yarder | Moderate |

The same screen runs on the tractor units as a check; their results are reported on the sheets as what
would happen if cable were required. Each unit also gets a profile sheet (best corridor from each selected
landing, with chord, mid-span deflection and minimum clearance drawn), a route table of distinct settings
with chord slope and yarding direction, and external and average yarding distances as the Forest Service
*Cable Logging Systems* guide defines them. Sale-level figures cover slope by unit, deflection across all
corridors, equipment class, difficulty, an equipment-selection matrix of span against chord slope, and
yarding direction by unit.

### Field-data review

A simulated BAF 20 cruise on a 300 ft grid: 798 plots, 8,722 trees, six planted recording errors. The QA
pass caught all six and raised one further flag. Each unit gets a review sheet with stand density (basal
area with sampling error, trees per acre, QMD, stand density index against the mixed-conifer maximum),
CWHR size and density class, a sawtimber versus biomass split, a demonstration leave target, a cruise
design check against the Region 5 sampling-error standard (FSH 2409.12: 18 % sawtimber, 25 % biomass, 20
plots minimum, plots needed from the CV), a plot map, and the findings a crew lead would hand back. A
sale-level QA table opens the merged review PDF; four units come up short of the 20-plot minimum.

### Standards followed

Map layout after Forest Service sale area maps: units filled by yarding method, treatment block boundary,
streamcourse protection, roads with numbers, 40 ft contours with 200 ft index, PLSS with township and
range, unit table, 11x17, as vector print PDF (300 dpi rasters) and as GeoPDF for Avenza. Okabe-Ito color-blind-safe palette
throughout. GeoPackage deliverable with layer descriptions and FGDC / ISO 19115 summary metadata
(`docs/data_dictionary.md`). Output checked against print, web, WCAG contrast and color-vision standards
by measurement (table in `docs/methods.md`). Cable screen definitions and the downhill-yarding rule from the Forest Service
*Cable Logging Systems* guide; deflection and tension relationship from the *Best Practice Guidelines for
Cable Logging* (FITEC). Stream widths from the Sierra Nevada Forest Plan Amendment. Canopy threshold at
the ASPRS 2 m vegetation boundary. Details and citations in `docs/methods.md`.

## Outputs

| Folder | Contents |
|---|---|
| `output/maps` | per-sheet print PDF (vector text, 300 dpi) and 150 dpi PNG; `geopdf/` field copies for Avenza; `Unit_Map_Series.pdf` merged (release asset, not in git) |
| `output/cable` | `unit_summary.csv`, per-unit profile sheets, route tables and corridor maps, six sale-level figures |
| `output/review` | per-unit review PDFs, `Unit_Reviews.pdf` with the sale-level QA page, `cruise_data.xlsx`, `qa_summary.csv` |
| `output/gis` | `mohawk_west_slope.gpkg` (all vector products, described and with project metadata) and four decision rasters |
| `output/quicklooks` | terrain and canopy products with legends, scale bar and unit outlines |
| `output/previews` | JPEG previews of everything above, with `INDEX.md` |
| `data/work` | GeoTIFF products, `planning.gpkg`, `cable.gpkg`, `cruise_plots.gpkg` (not in git) |

## Pipeline

| Script | Output |
|---|---|
| `01_get_data.py` | public vectors to `data/raw`; `ept_fetch.py` pulls the LiDAR nodes |
| `02_build_terrain.py` | DTM, DSM, CHM, slope, planning slope, aspect, hillshade, cover, dominant height, yarding class |
| `02b_quicklooks.py` | color quicklooks of the products |
| `03_delineate_units.py` | demonstration units, riparian and exclusion buffers, clipped streams |
| `04_cable_analysis.py` | landings, corridors, per-unit skyline feasibility |
| `04b_cable_figures.py` | profile sheets, route tables, corridor maps, all sale-level figures, EYD and AYD, from the saved corridors |
| `05_unit_maps.py` | 11x17 unit map series and overview, print PDF and GeoPDF (PyQGIS) |
| `06_review_sheets.py` | simulated cruise, QA checks, review sheets, Excel workbook |
| `07_previews.py` | JPEG previews and index |
| `08_package_gis.py` | distributable GeoPackage with metadata, packaged rasters |

Runs on QGIS 3.44's bundled Python (GDAL, PDAL, NumPy, SciPy, PyQGIS, matplotlib, ReportLab, openpyxl).
No ArcGIS required. The full run from download to previews takes about two hours on a laptop.

## What I would do differently

- Replace the NHD stream classes with a field-verified channel classification before any boundary is
  final; NHD codes many small draws as perennial here.
- Add the constraints only the project record supplies: protected activity centers, cultural sites, soils
  and existing skid trails. The units are drawn without them.
- Design the skyline corridors to actual tailhold trees and intermediate supports rather than a 100 ft
  offset past the boundary, and cost the landings.
- Build the units with a crew on the ground. The layout rules here reproduce how a layout forester reads
  terrain, not the walk that confirms it.
