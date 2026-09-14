# Mohawk Valley West Slope: LiDAR-based harvest-unit planning

Harvest-unit planning on 1,816 acres of the Community Protection treatment block on the Plumas National Forest,
west slope of Mohawk Valley, from USGS 3DEP LiDAR flown in 2018 and public vector data. Products: terrain and
canopy rasters, 24 demonstration units, a cable-yarding screen, a 25-sheet 11x17 unit map series, and field-data review
sheets for a simulated cruise. The workflow follows the harvest-unit planning I worked on as a Forester III on National Forest projects,
rebuilt here on public data.

I worked on federal timber sales of this kind for a contractor in this landscape. Those deliverables belong to
the contractor and the Forest Service and none of them appear here. Every number here was computed from public sources by the scripts in [`scripts/`](scripts/). The units are demonstration polygons drawn by the rules in
[`docs/methods.md`](docs/methods.md). They are not a Forest Service proposal. No field verification has been done.

Interactive map: https://woodsy-will.github.io/projects/plumas-lidar-harvest-planning/map/ (units, skyline corridors, landings, exclusion zones, yarding class and simulated plots, on USGS basemaps).

![Unit 404 sheet: LiDAR hillshade with yarding-class tints, cased unit outlines, stream exclusion zones, skyline corridors from four landings, legend and unit panel](output/previews/map_Unit_404.jpg)

| Overview sheet | Skyline profiles, unit 404 | Field-data review, unit 101 | Yarding class |
|---|---|---|---|
| ![Overview sheet](output/previews/map_Overview.jpg) | ![Skyline profiles](output/previews/cable_Unit_404_profiles.jpg) | ![Review sheet](output/previews/review_Unit_101_Review.jpg) | ![Yarding class](output/previews/terrain_yarding_class.jpg) |

## Area

A treatment block of the Community Protection - Central and West Slope project (Plumas National Forest,
USFS project 62873). The project has two decisions: one signed September 10, 2023 for the La Porte and Greater
Mohawk areas, and one signed July 1, 2025 for the remainder. The block used here is the one on National Forest
land nearest Whitehawk Ranch, Clio, California (T22N R12E, MDB&M): 1,816 acres on the west slope of Mohawk
Valley, buffered 300 m for terrain context. In the Forest Service EDW project-area layer, which carries one
polygon per decision, the block lies entirely inside the July 2025 decision polygon and adjoins the boundary of the
September 2023 polygon. The selection rule is written into `scripts/01_get_data.py` and picks the same block every run.

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

The raw 3 ft slope surface under this canopy averages 87 %. That is interpolation noise. Yarding class is
taken from the planning slope, a smoothed DTM averaged over 99 ft.

### Harvest units

24 demonstration units on 1,621 gross acres inside the 1,816-acre block; 1,408 net acres after the stream equipment exclusion zones.

| Method | Units | Acres | Mean slope |
|---|---|---|---|
| Tractor | 18 | 1,389 | 10 to 24 % |
| Cable | 6 | 231 | 42 to 54 % |

Acres by method are direct sums of the rounded unit values; the 1,621 total is from unrounded values.

Units run 30 to 116 acres and are split along ridges and draws. Stream equipment exclusion zones stay inside
the unit boundary as an internal restriction and are netted out of treatable acres.

### Cable-yarding screen

940 road points were sampled every 200 ft. 240 of them lie within reach of a unit and gave 314 candidate landings, from which 8,540 corridors were cast. For the six cable units:

| Unit | Acres | Feasible corridors | Coverage | Equipment class | Difficulty | Corridors with a credited payload | Allowable load, best corridor |
|---|---|---|---|---|---|---|---|
| 401 | 30 | 0 of 68 | 0 % | no feasible corridor from any landing within 2,000 ft | High: needs a spur road or a different system | 0 | none |
| 402 | 39 | 182 of 374 | 70 % | long-span yarder | Moderate | 110 | 10,830 lb |
| 403 | 34 | 124 of 551 | 52 % | long-span yarder | Moderate | 72 | 15,443 lb |
| 404 | 51 | 205 of 2,022 | 61 % | intermediate support needed | Moderate | 169 | 8,819 lb |
| 405 | 43 | 261 of 1,464 | 42 % | medium yarder | Moderate | 216 | 9,645 lb |
| 406 | 35 | 9 of 41 | 70 % | long-span yarder | Moderate | 0 | none: every feasible corridor has under 3 % loaded deflection |

A corridor is feasible when the straight chord clears the ground by 10 ft and unloaded mid-span deflection is at
least 6 %. It is credited with a payload only when the loaded line, sagging as a parabola, still clears every point of
the profile by 10 ft at a mid-span deflection of at least 3 % (PNW-39 chain method). The allowable load is the
7/8 in skyline's working load at that governing loaded deflection, for the highest-payload corridor from the selected
landings. Unit 406's corridors pass the chord test and fail the loaded-line test.

The same screen runs on the tractor units as a check. Their sheets report what would happen if cable were
required. Each unit gets a profile sheet showing the best corridor from each selected landing, with chord,
mid-span deflection and minimum clearance drawn. Where any corridor is feasible the unit also gets a route
table of distinct settings with chord slope, yarding direction, and external and average yarding distances
as the Forest Service *Cable Logging Systems* guide defines them.

Each feasible corridor carries an allowable load on a 7/8 in skyline at a safety factor of 3 at its
governing loaded deflection. That deflection is the mid-span sag of a loaded line that still clears every point of
the profile by 10 ft, the chain method of the Forest Service *Skyline Tension and Deflection Handbook* (PNW-39).
The load comes from the handbook's rigid-link statics, checked against its tables. Corridors whose loaded
deflection is under 3 % carry no payload.

Sale-level figures cover slope by unit, deflection across all corridors, equipment class, difficulty, an
equipment-selection matrix of span against chord slope, yarding direction by unit, and payload against span.

### Field-data review

A simulated BAF 20 cruise on a 300 ft grid: 798 plots, 8,722 trees, six planted recording errors. The QA
pass caught all six and raised one further flag.

Each unit gets a review sheet. It carries stand density (basal area, trees per acre, QMD, stand density index
against the mixed-conifer maximum), CWHR size and density class, a sawtimber and biomass split, a leave target
at 35 % of the basal-area-weighted FVS maximum SDI, a stand table by DBH class, a stock table by species, a
cruise design check with Student's t against the FSH 2409.12 sampling-error standards as supplemented for
Region 5 (30 % per stratum and 10 % for the sale as a whole, tree-measurement sale), a plot map, and the findings
a crew lead would hand back. Sampling error is computed on plot net cubic volume per acre, the quantity the
handbook's error standards apply to (sec. 41.1). The basal-area error is kept as a secondary figure. The
simulated plots tally every tree, so the exercise is a pre-marking stand exam with the sale-cruise error
standards applied as if the whole tallied volume were designated for cutting.

Every page carries a SIMULATED DATA watermark, the cruiser code is SIM, and the workbook opens with a READ ME
sheet saying the same.

A sale-level QA page opens the merged review PDF. 24 of 24 units meet the Region 5 stratum standard of 30 %
on volume for a tree-measurement sale (the national figure is 40 %); unit errors run 4.5 to 22.9 %, with unit
401 the highest and unit 101 at 10.4 %. The sale as a whole has a volume sampling error of 2.0 % against the
10 % standard for a tree-measurement sale valued at $250,000 or more, and meets it; the sale is placed with the
Region 5 FY2025 sold average of $33.63/MBF on 50,108 MBF over net acres, about $1.7 million. The Region 5
supplement also sets a minimum of 20 plots for an area-based cruise and at least 20 measured trees for each
major species or species group, a major species being one that makes up 10 % or more of the sale value. Four
units fall short of 20 plots; the measured-tree count by species is reported on the review sheets.

### Standards followed

Map layout follows Forest Service sale area maps: units colored by yarding method (pale fills with a dashed dark
outline on the overview, cased outlines on the unit sheets), treatment block boundary, streamcourse protection,
roads with numbers, 40 ft contours with 200 ft index, PLSS with township and range, unit table, 11x17, as
vector print PDF (300 dpi rasters) and as GeoPDF for Avenza. Symbology was reworked against a current Forest
Service sale area map, Patterson's relief-shading guidance, Jenny and Kelso's color-vision recommendations and
USGS topographic conventions (table in [`docs/methods.md`](docs/methods.md)). Okabe-Ito color-blind-safe palette throughout.

GeoPackage deliverable with layer descriptions and FGDC / ISO 19115 summary metadata ([`docs/data_dictionary.md`](docs/data_dictionary.md)).
Output was checked by measurement against print, web, WCAG contrast and color-vision standards (table in
`docs/methods.md`).

Cable screen definitions and the downhill-yarding rule are from the Forest Service *Cable Logging Systems*
guide; the deflection and tension relationship from the *Best Practice Guidelines for Cable Logging* (FITEC).
Stream widths from the Sierra Nevada Forest Plan Amendment. Canopy threshold at the ASPRS 2 m vegetation
boundary. Cruise sampling error is computed on net cubic volume per acre and tested against the FSH 2409.12
sec. 41.1 volume error standards as supplemented for the Pacific Southwest Region (R5 Supplement 2409.12-2021-4,
effective August 11, 2021): 30 % per stratum for a tree-measurement sale, where the national handbook says 40 %,
and 10 % for the sale as a whole at an estimated value of $250,000 or more, with the national exhibit 01 tiers
applying to smaller sales. The basal-area error is kept as a secondary figure. The minimums of 20 plots for an
area-based cruise and 20 measured trees per major species come from sec. 41.3 of the same supplement.
Details and citations in [`docs/methods.md`](docs/methods.md).

## Outputs

The large deliverables (the merged map series, the GeoPDFs, the individual print sheets, the 300 dpi cable
figures and the packaged rasters) are attached to the
[v1.1 release](https://github.com/woodsy-will/plumas-lidar-harvest-planning/releases/tag/v1.1) and kept
out of git. JPEG previews of everything are in [`output/previews`](output/previews).

| Folder | Contents |
|---|---|
| `output/maps` | per-sheet print PDF (vector text, 300 dpi) and 150 dpi PNG; `geopdf/` field copies for Avenza; `Unit_Map_Series.pdf` merged (release asset, not in git) |
| `output/cable` | `unit_summary.csv`, per-unit profile sheets, route tables and corridor maps, seven sale-level figures |
| `output/review` | per-unit review PDFs, `Unit_Reviews.pdf` with the sale-level QA page, `cruise_data.xlsx`, `qa_summary.csv` |
| `output/gis` | `mohawk_west_slope.gpkg` (all vector products, described and with project metadata) and four decision rasters |
| `output/quicklooks` | terrain and canopy products with legends, scale bar and unit outlines |
| `output/previews` | JPEG previews of everything above, with `INDEX.md` |
| `data/work` | GeoTIFF products, `planning.gpkg`, `cable.gpkg`, `cruise_plots.gpkg` (not in git) |

## Pipeline

| Script | Output |
|---|---|
| `01_get_data.py` | public vectors to `data/raw`, including Census TIGER county roads clipped to the area; skips any file already present; `ept_fetch.py` pulls the LiDAR nodes |
| `02_build_terrain.py` | DTM, DSM, CHM, slope, planning slope, aspect, hillshade, cover, dominant height, yarding class |
| `02b_quicklooks.py` | color quicklooks of the products |
| `02c_relief_tint.py` | pre-composed relief tint (hillshade x pale yarding-class tints) for the unit sheets |
| `03_delineate_units.py` | demonstration units, riparian and exclusion buffers, clipped streams, 40 ft contours, operable mask |
| `04_cable_analysis.py` | landings, corridors, per-unit skyline feasibility |
| `04b_cable_figures.py` | profile sheets, route tables, corridor maps, all sale-level figures, EYD and AYD, from the saved corridors |
| `05_unit_maps.py` | 11x17 unit map series and overview, print PDF and GeoPDF (PyQGIS) |
| `06_review_sheets.py` | simulated cruise, QA checks, review sheets, Excel workbook |
| `07_previews.py` | JPEG previews and index |
| `08_package_gis.py` | distributable GeoPackage with metadata, packaged rasters |
| `09_export_webmap.py` | WGS84 GeoJSON and the yarding-class overlay for the portfolio web map |

The full run from download to previews takes about two hours on a laptop. Software versions are listed below.

## How to run

From the repository root, in order, with the QGIS-bundled Python (`python-qgis-ltr.bat` on Windows):

```bat
set PY="C:\Program Files\QGIS 3.44.12\bin\python-qgis-ltr.bat"
%PY% scripts\01_get_data.py          & rem public vectors to data/raw (idempotent)
%PY% scripts\ept_fetch.py            & rem LiDAR nodes to data/raw/ept (4.3 GB), node list to data/work
%PY% scripts\02_build_terrain.py     & rem about 2 h; use --max-batches N to run in chunks
%PY% scripts\02b_quicklooks.py & %PY% scripts\02c_relief_tint.py
%PY% scripts\03_delineate_units.py
%PY% scripts\04_cable_analysis.py    & rem about 12 min
%PY% scripts\04b_cable_figures.py
%PY% scripts\05_unit_maps.py         & rem ONLY_UNITS="404 101" renders a subset
%PY% scripts\06_review_sheets.py
%PY% scripts\07_previews.py & %PY% scripts\08_package_gis.py
```

## Software

QGIS 3.44.12 (PyQGIS), GDAL 3.13, PDAL 2.10, Python 3.12, NumPy, SciPy, matplotlib, ReportLab, openpyxl,
pypdf, PyMuPDF, Pillow, all as shipped with QGIS 3.44. No ArcGIS required. Developed on Windows 11;
the scripts reference the QGIS install path and the Windows Fonts folder for Arial.

## License and citation

Code: MIT ([`LICENSE`](LICENSE)). Maps, figures, review sheets and packaged data: CC BY 4.0 ([`LICENSE-MAPS-DATA.md`](LICENSE-MAPS-DATA.md)),
which also lists the terms of each public input. Cite with [`CITATION.cff`](CITATION.cff) or as:
William Steinley (2026), *Mohawk Valley West Slope: LiDAR-based harvest-unit planning*, v1.1,
https://github.com/woodsy-will/plumas-lidar-harvest-planning. Contact: through https://woodsy-will.github.io/.

## Limitations

- The cruise is simulated. Every plot and tree is generated from the LiDAR canopy metrics with planted
  recording errors, and every review sheet, the workbook and the QA table say so. The statistics are real
  computations on made-up data.
- The cable screen is a screen. A straight chord from a 50 ft tower to a 10 ft anchor with a clearance and
  deflection test sorts corridors. The payload figure is the handbook's rigid-link planning estimate at the
  chain-clearance loaded deflection (10 ft clearance, project assumption), with no catenary, carriage weight,
  multispan or intermediate-support analysis. It ranks settings. It does not size a yarder.
- The unit rules are a demonstration method. Splitting large regions by k-means on position, elevation
  and aspect is a rule I wrote for this project to imitate how a layout forester follows ridges and draws.
  It is not an established industry procedure.
- Volumes follow published equations, with no cruise compiler behind them. Cubic volume uses the PNW-FIA tarif
  equations by species (MacLean and Berger 1976, as compiled by the California Air Resources Board), board feet
  the California Scribner ratio of 5.02 per cubic foot of bole wood (Keegan et al. 2010), and biomass the green
  densities of Miles and Smith 2009. The standards sheet in the workbook lists each constant, its source and URL.
- Inputs are taken as published. NHD stream classes drive the exclusion zones and net acres without
  field verification. Census TIGER roads can include roads that no longer exist on the ground. The LiDAR
  omits the coarsest octree levels (about 0.5 % of points).
- No field verification. The units, corridors and plots must not be used for operations.

## What I would do differently

- Replace the NHD stream classes with a field-verified channel classification before any boundary is
  final; NHD codes many small draws as perennial here.
- Add the constraints only the project record supplies: protected activity centers, cultural sites, soils
  and existing skid trails. The units are drawn without them.
- Design the skyline corridors to actual tailhold trees and intermediate supports instead of a 100 ft
  offset past the boundary, and cost the landings.
- Lay the units out with a crew on the ground. The rules here imitate how a layout forester reads
  terrain. They do not replace the walk that confirms it.
