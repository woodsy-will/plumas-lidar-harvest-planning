# Methods

Every number in this project is computed from public data by the scripts in `scripts/`. This note records
the rules and thresholds so a reviewer can judge them, and so the units are read as a method demonstration
rather than a proposal.

## Coordinate system and units

California State Plane Zone 2, NAD83, US survey feet (EPSG:2226). Heights in feet. USGS delivers the LiDAR
in EPSG:5070 meters; it is reprojected and scaled on the way in.

## LiDAR source (`ept_fetch.py`)

The 2018 survey is read from the USGS Entwine (EPT) copy on Amazon rather than the staged tiles, which served
at a few hundred KB/s. Every octree node whose cube intersects the AOI is downloaded at depth 8 and below;
the coarse levels above depth 8 hold about 0.5 % of the AOI's points and are omitted. Node files are plain
LAZ in EPSG:3857 with classification intact, so the content matches the tiles.

## Terrain and canopy products (`02_build_terrain.py`)

| Product | Rule |
|---|---|
| DTM, 3 ft | class 2 (ground) returns, inverse-distance weighting, 8-cell search window; small holes filled by GDAL FillNodata within 50 cells |
| DSM, 3 ft | first returns, maximum |
| CHM, 3 ft | height above the DTM of all non-noise returns, maximum, clipped to 0 to 300 ft |
| Slope, aspect, hillshade | GDAL DEMProcessing on the DTM; slope in percent |
| Canopy cover | share of CHM cells above 6.5 ft in a 66 ft square window |
| Dominant height | 95th percentile of the CHM in a 66 ft window |
| Yarding class | slope averaged over 99 ft: ground-based at or below 35 %, marginal 35 to 50 %, cable above 50 % |

The 35 % ground-based limit and the cable ground above it follow the Forest Service logging-systems
convention used on Region 5 timber sales. The 99 ft averaging keeps single benches or cut banks from
flipping a class.

## Harvest-unit delineation (`03_delineate_units.py`)

Operable ground is the intersection of:

- the Community Protection treatment block, on National Forest land;
- stream equipment exclusion zones, 100 ft each side of perennial streams and around waterbodies, 50 ft
  intermittent, 25 ft ephemeral by NHD feature code, stay inside the unit boundary as an internal
  restriction, the way layout crews draw units, and are netted out of the treatable acreage. The wider
  riparian conservation areas (300 / 150 / 100 ft, Sierra Nevada Forest Plan Amendment) are mapped on
  every sheet; treatment inside them is allowed under the project's design features;
- a stand is present: canopy cover at least 30 % and dominant height at least 40 ft;
- planning slope at or below 100 %, the practical ceiling for skyline ground. Planning slope is the
  gradient of the DTM smoothed with a 15 ft Gaussian and averaged over 99 ft, so cut banks and
  interpolation noise under dense canopy do not decide a unit;
- within 3,500 ft of a road (National Forest System roads from EDW, supplemented by Census TIGER local
  roads, which pick up the spur roads EDW omits).

Cleaning: morphological open then close with a 99 ft kernel; regions smaller than 20 ac are dropped.

Splitting: ground-based and cable ground are kept as separate regions. Regions larger than 150 ac are
split toward 80 ac pieces by k-means clustering on position, smoothed elevation and aspect, so the
boundaries between pieces fall where the ground turns, on ridges and in draws, the way a layout forester
runs a unit line. A 99 ft majority filter keeps the pieces compact. Pieces under 20 ac are merged into
their largest neighbor.

Treatment method: Hand Thinning where dominant height is under 55 ft with cover at least 50 % (a
small-diameter fuels stand); otherwise Tractor at mean slope 35 % or less, Cable above. Numbering:
100-series Tractor, 400-series Cable, 700-series Hand Thinning, west to east.

Not modeled, and stated so on the maps: wildlife protected activity centers, cultural sites, soils,
existing skid trails, and anything else that only a field visit and the project record supply.

## Cable-yarding feasibility (`04_cable_analysis.py`)

For each Cable unit, and for Tractor units as a check:

1. Candidate landings are road points within 500 ft of the unit, sampled every 200 ft along NFS and TIGER roads; a unit with no road that close is served from its nearest road points up to 2,000 ft away; on tractor units the candidate list is thinned to at most 12 landings and corridors are cast every 10 degrees rather than 5.
2. From each landing, corridors are cast every 5 degrees (10 for tractor units) across the unit to a tailhold 100 ft beyond the
   far boundary, and profiles sampled from the DTM every 10 ft.
3. Skyline geometry: tower height 50 ft (medium yarder) with a 70 ft alternative, tailhold anchor 10 ft.
   The chord runs from tower top to anchor. A corridor is feasible when the profile never rises within
   10 ft of the chord and the mid-span deflection, chord height above ground at mid-span divided by span
   length, is at least 6 %, the usual planning minimum for partial-suspension payloads.
4. Span classes for equipment: up to 1,000 ft small yarder, up to 1,800 ft medium, up to 3,000 ft
   long-span; longer spans are flagged as needing intermediate supports.
5. Unit coverage is the share of the unit within 150 ft (lateral yarding reach) of a feasible corridor from the
   landings actually selected: up to four, chosen greedily for total coverage and stopped when the next landing
   adds less than 3 % of the unit.
   Difficulty combines coverage, mean available deflection, ground slope and the downhill-yarding share.
6. Payload estimate (`04b_cable_figures.py`). For each feasible corridor the allowable load at mid-span is computed
   for a 7/8 in extra-improved plow-steel skyline (6x19 IWRC, 1.42 lb per ft, breaking strength 79.6 kips) worked at
   a safe working load of breaking strength divided by 3, 26.5 kips, the minimum safety factor the handbook
   recommends for skyline design (Lysons and Mann 1967, *Skyline tension and deflection handbook*, USFS Research
   Paper PNW-39, p. 3; rope table 1, p. 24; the same rope table is table 4-3, p. 25, of the Forest Service *Cable
   Logging Systems* guide, which refers the load-carrying calculation to PNW-39 on p. 5). The arithmetic is the
   PNW-39 single-span worksheet (p. 4; reproduced in the appendix of *Cable Logging Systems*): the upper-end
   tension caused by the cable's own weight is subtracted from the safe working load, and the remainder is
   divided by the upper-end tension per pound of load. Where the handbook reads those two tensions from catenary
   tables, this script computes them by rigid-link statics: the skyline is two straight links from the supports
   to the load at mid-span, each carrying half the cable weight (measured along the chord) at its midpoint. In
   words, the horizontal tension is the span times (twice the load plus the cable weight) divided by eight times
   the mid-span deflection; the vertical component at the upper support is that horizontal tension times (chord
   slope plus twice the deflection ratio) plus a quarter of the cable weight; the upper-end tension is their
   resultant. Solved for the load at the safe working load, this reproduces the handbook's table 2 (tension due
   to cable weight, p. 32) and table 4 (tension due to a mid-span load, carriage clamped to the skyline, p. 36)
   within 1 % for span slopes of 0 to 55 %. Limitations: the available deflection, chord to ground at mid-span,
   is taken as the loaded deflection, the planning assumption; it is optimistic wherever the ground is close to
   the chord, because the handbook's loaded deflection is the available deflection less the carriage, choker,
   log and ground clearance. The result is the gross load at the carriage and no carriage weight is subtracted.
   The links are straight, not catenaries; single span only, no intermediate supports; the clamped-carriage
   (higher-tension) case is used throughout; and on short spans the figure is what the rope would hold, which
   the yarder line pull and carriage would limit first. The estimate is reported as `payload_lb` on the route
   tables, as an annotation on the profile sheets, in Fig 7, and as `max_payload_lb` and `payload_at_best_lb`
   in `unit_summary.csv`; it is not stored in the GeoPackage. *Cable Logging Systems* (p. 87) puts the deflection
   needed to carry a payload at 8 to 10 %, so corridors passed at 6 to 8 % carry the smallest loads.

These are planning-level screens of the kind used to sort units by logging system before a field review,
not an engineered skyline design. Two definitions follow the Forest Service *Cable Logging Systems* guide
(Pacific Northwest Region, FS technology and development): external yarding distance is taken here as the
longest horizontal span among a unit's feasible corridors (landing to tailhold, 100 ft past the boundary),
and average yarding distance is 0.667 of it for a fan-shaped setting.
The same guide is the source for the direction rule reported on the sheets: downhill yarding
capability is usually a third to a half of uphill capability, and landings should be placed to avoid blind
leads and sidehill yarding. The deflection, clearance and tension relationship, and the 6 % planning
minimum, follow the *Best Practice Guidelines for Cable Logging* (New Zealand FITEC, 2000): at 6 %
deflection the loaded skyline tension is about 60 % higher than at 10 %, and below that payloads fall off
quickly.

## Map conventions and symbology

The unit sheets and overview follow the layout of a Forest Service sale area map: cutting units, the sale or
treatment block boundary, streamcourse protection areas, existing transportation with road numbers, contour
lines with labeled index contours, PLSS sections with township and range in the title block, a unit table,
north arrow, bar scale and scale statement on an 11x17 sheet. Contract clause references (B1.1, C6.42 and the
like) are omitted because there is no contract.

The symbology was reworked against published guidance and a current Forest Service example, and the choices
are these:

| Element | Choice | Basis |
|---|---|---|
| Visual hierarchy | The units are the figure: cased outlines colored by method with bold labels; everything else recedes. Overview uses pale method fills with a dashed dark outline, the cutting-unit convention. | Willamette NF LFC SBA sale area map (2025): units as the only filled features, heavy dashed sale boundary, grey base; Esri design principles on figure-ground and contrast |
| Sale boundary | Heavy black long dash | Same sale area map; a line pattern reads under any color vision |
| Relief base | Multidirectional hillshade multiplied into pale class tints once in `02c_relief_tint.py`; shadows held to 62 % luminosity, tints desaturated | Patterson (shadedrelief.com): shadows no darker than 70 %, muted colors so relief does not muddy the map; Esri: base at 30 to 50 % strength; empirical overlay study (opacity 20 to 70 % acceptable, outlines extend the range) |
| Why one composed raster | Blending translucent fills in the layout produced third colors (blue over yellow read as green) and would have forced the PDF export to raster | Jenny and Kelso 2007 on redundant variables and confusable blends; measured in this project |
| Method colors | Okabe-Ito vermillion (tractor), blue (cable), green (hand thinning); pale versions for fills, dark for lines | Okabe and Ito palette; Jenny and Kelso 2007 (dark green, brown, orange and red collapse for red-green impaired readers, so method is also carried by the label) |
| Hydrography | USGS blue; perennial solid, intermittent dash-dot, ephemeral dotted; riparian conservation areas as a pale wash; equipment exclusion zones as a fine hatch inside units | USGS topographic map symbol standard; class carried by line pattern, not hue |
| Contours | USGS brown, 40 ft with 200 ft index, held to low opacity | USGS standard (brown, index heavier); hierarchy |
| Roads | System roads as a cased dark line with the road number; local roads thin grey dash | USGS road classes; sale area map road numbers |
| Corridors and landings | Thin neutral black corridors, yellow triangle landings with black edge | Avoids a second blue family next to hydrography |
| Marginalia | Scale statement, contour interval, north reference, sheet number and date beside the bar scale | Standard map elements; sale area map title block |

## Canopy height model and pits

The CHM is the maximum height above ground of any non-noise return in each 3 ft cell. Pit-free CHM algorithms (Khosravipour et al.
2014) remove the below-canopy returns that leave single dark cells inside crowns; they are not applied here
because every downstream use of the CHM is a 66 ft window statistic (cover, 95th percentile height) or a
unit mean, which pits do not move. The 6.5 ft (2 m) cover threshold is the ASPRS boundary between low and
medium vegetation and the usual operational definition of canopy.

## Field-data review sheets (`06_review_sheets.py`)

A simulated variable-radius cruise (BAF 20, 300 ft grid) is generated inside each unit from the canopy
products, with a documented set of planted recording errors. The review sheet for each unit carries a stand
summary, a stand table by 4-inch DBH class, a stock table by species, a plot map, the QA findings and the plot
list, in the format used to hand a unit back to a crew. The workbook `cruise_data.xlsx` opens on a READ ME sheet
that states the data are simulated, then holds the plots, trees, unit summary, stand and stock tables and a sheet
of standards and assumptions in which every constant names its value, source and URL. The simulated nature of the
cruise is marked everywhere it could be mistaken for field data: every review-sheet page carries a light grey
diagonal SIMULATED DATA watermark, the cruiser code is `SIM`, the plot date field reads `simulated`, and
`qa_summary.csv` carries a `data` column with the value `simulated` on every row.

Computations and the standards they follow:

| Quantity | Method | Standard or source |
|---|---|---|
| Basal area | plot BA = trees in x BAF; tree BA = 0.005454 x DBH^2 | standard mensuration |
| Trees per acre | per-tree expansion BAF / tree BA, averaged over plots | variable-radius sampling |
| Sampling error | t(0.975, n-1) x SE of plot BA / mean, in percent | FSH 2409.12 ch. 40 sec. 41.1: 95 % confidence, t = 2 for large n |
| Stratum standard | 40 % per unit | FSH 2409.12 ch. 40 sec. 41.1(5)(b), tree-measurement sales |
| Sale-as-a-whole | stratified estimate with area weights; standard from exhibit 01 by estimated sale value (10 % above $120,000) | FSH 2409.12 ch. 40 sec. 41.1 exhibit 01; value placed at $33.63/MBF, the Region 5 FY2025 average sold value: $9,223,272.19 over 274,275.08 MBF sold, all sales, region total row of the Forest Service Cut and Sold report CUTS203R, cumulative FY2025 Q1-Q4, run 2025-12-08 (https://www.fs.usda.gov/sites/default/files/2025-q4-cut-sold-r05.pdf). The report excludes Good Neighbor sale values and warns against using it for unit values, so the placement is a demonstration |
| Plots for the standard | (t x CV / E)^2; the Region 5 practice minimum of 20 plots is reported separately | FSH 2409.12 ch. 30 |
| SDI | summation form, sum of TPA x (DBH/10)^1.605 | Reineke 1933; Shaw 2000 |
| SDI maximum | basal-area-weighted mean of species maxima: PP 365, WF 800, DF 570, SP 561, IC 576 | FVS Staff 2008 (revised 2025-09-23), Western Sierra Nevada (WS) Variant Overview, Forest Vegetation Simulator, table 3.5.1 (https://www.fs.usda.gov/sites/default/files/forest-management/fvs-ws-overview.pdf); earlier revisions of the overview listed different maxima for some species |
| Density zones and target | 35 % of maximum = lower limit of full occupancy, 60 % = onset of competition mortality; leave target 35 % expressed as BA | Long 1985; Long and Shaw 2012 |
| Cubic volume | total-stem cubic volume (CVTS, top and stump included) by species: DF eq. 3, PP eq. 5, IC eq. 19, SP eq. 20, WF eq. 23 of the PNW-FIA tarif system (CF4, CV4, tarif, CVTS; trees under 6 in by the small-tree tarif), net of recorded defect; species codes without an equation fall back to BA x total height x form factor 0.42 | PNW-FIA volume equations for California (MacLean and Berger 1976, PNW Research Note PNW-266), as tabulated in "Volume estimation for the PNW-FIA Integrated Database", reproduced by the California Air Resources Board (2011): species table p. 5 (CA column), equations pp. 9, 11, 25, 26 and 29 (https://ww2.arb.ca.gov/sites/default/files/cap-and-trade/protocols/usforest/2011/volume_equations.pdf); fallback form factor after Avery and Burkhart, Forest Measurements (5th ed., 2002) |
| Board feet | 5.02 Scribner bf per cu ft, applied to CVTS | Keegan, Morgan, Blatner and Daniels 2010, Trends in lumber processing in the western United States, Part I: Board foot Scribner volume per cubic foot of timber, Forest Prod. J. 60(2):133-139, table 2 (p. 135): California, 2000-2006, board feet Scribner per cubic foot of bole wood inside bark (the abstract rounds it to 5.03); treesearch 37833 (https://research.fs.usda.gov/treesearch/37833). Applied to total-stem cubic volume it overstates sawlog board feet somewhat |
| Biomass | green weight of wood by species: PP 45, WF 47, DF 38, SP 49, IC 45 lb per cu ft; unknown codes 45 | Miles and Smith 2009, Specific gravity and other properties of wood and bark for 156 tree species found in North America, Research Note NRS-38, table 1A (pp. 8-9), average green weight of wood on a green-volume basis, bark excluded; Douglas-fir is a single entry there (FIA code 202, not split coast/interior); treesearch 34185 (https://research.fs.usda.gov/treesearch/34185) |
| CWHR | size from QMD (3: 6 to 11 in, 4: 11 to 24, 5: over 24); density from cover (S 10 to 24 %, P 25 to 39, M 40 to 59, D 60 and over) | California Wildlife Habitat Relationships |

Tables follow publication style: title above, horizontal rules only, footnotes and sources below, units in the
headers. Skyline profiles are drawn at true scale with the vertical exaggeration stated on each panel, and
"available deflection" is labeled as such: chord-to-ground height at mid-span as a percent of horizontal span.

## Output standards, checked by measurement

The deliverables were checked against current practice for map and figure output and the check is repeatable
(the measurements below come from reading the files back with PyMuPDF, GDAL and Pillow).

| Item | Standard | This project |
|---|---|---|
| Print PDF | text and linework vector, rasters at 300 dpi, fonts embedded | unit sheets and overview: vector text (Arial embedded), 9 raster images at 300 dpi, 2.3 to 3.7 MB per unit sheet, 5.4 MB for the overview |
| Field PDF | georeferenced; Avenza reduces maps over 4 Mpx to 150 dpi and over 12 Mpx to 72 dpi on import | `output/maps/geopdf`: QGIS GeoPDF at 200 dpi (7.5 Mpx, under the 12 Mpx step); the print PDFs also carry ISO 32000 georeferencing |
| Figures | 300 dpi for publication | all cable figures, route tables and profiles at 300 dpi; corridor maps and quicklooks at 200 dpi |
| Web previews | sRGB, about 2,000 to 2,500 px long edge, JPEG quality 85 to 90 | 1,870 px map previews, 2,400 px figure previews, quality 88, 4:4:4 chroma so thin colored lines stay crisp |
| Text contrast | WCAG 2.2 AA: 4.5:1 for text, 3:1 for graphics | every text and background pair measured is 5.4:1 or better; map text on the hillshade tints 8.8:1 |
| Color vision | categories distinguishable under protan, deutan and tritan simulation | Okabe-Ito palette throughout; unit interiors are left open under a cased outline rather than filled with a translucent color, because a blue fill over the yellow marginal tint blended to a green only 9 CIE76 units from the ground-based tint; the overview, which carries no relief tint, uses opaque pale method fills; the current-unit outline is black with a white casing because red on orange collapsed to 1.7 units under protan simulation |
| Type size | 6 pt minimum, 8 pt preferred on printed maps | smallest map text 6 pt (contour elevation labels), footer and overview unit table 7 pt, legend 7.5 pt, unit panel 9 pt |
| Metadata | title and author in the document, ISO / FGDC summary for GIS data | PDF document title and author set; GeoPackage carries layer descriptions and a project metadata table |

The merged map series (about 78 MB at 300 dpi) and the GeoPDF folder are kept out of git and attached to the
release instead.

## Colors, metadata and deliverables

Every categorical color on the maps and figures (yarding method, yarding class, uphill / downhill,
difficulty, QA flags) is drawn from the Okabe-Ito color-blind-safe palette. The unit sheets and overview
are exported twice: a print PDF with vector text and 300 dpi rasters, and a georeferenced GeoPDF at 200 dpi
for Avenza Maps (QGIS rasterizes the whole sheet for GeoPDF, so the two cannot be one file). Each sheet
states the data currency (LiDAR 2018, vectors as downloaded September 2026, NHD 1:24,000), the township and
range the unit lies in, and the sources.

`02b_quicklooks.py` draws the terrain and canopy products with a title, legend or color ramp, scale bar and
north arrow. `08_package_gis.py` writes the distributable GIS deliverable, `output/gis/mohawk_west_slope.gpkg`,
with a description on every layer and a project metadata table in FGDC / ISO 19115 summary fields (title,
abstract, purpose, spatial reference, sources, accuracy, lineage, constraints), plus the four decision rasters
as tiled, compressed GeoTIFFs with overviews. `docs/data_dictionary.md` defines every layer and field.
