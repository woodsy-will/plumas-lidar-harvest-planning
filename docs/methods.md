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
   far boundary (the 100 ft tailhold offset is an assumption of this project: room for a stump or deadman anchor
   outside the cut boundary), and profiles sampled from the DTM every 10 ft.
3. Skyline geometry: tower height 50 ft with a 70 ft alternative, tailhold anchor 10 ft. The tower heights are an
   assumption of this project standing for a medium and a tall swing yarder; they are not taken from a
   manufacturer's table. The chord runs from tower top to anchor. A corridor is feasible when the profile never
   rises within 10 ft of the chord (the 10 ft chord clearance is an assumption of this project; PNW-39 leaves the
   carriage, choker, log and ground clearance to the planner) and the available mid-span deflection, chord height
   above ground at mid-span divided by span length, is at least 6 %, the usual planning minimum for
   partial-suspension payloads (*Best Practice Guidelines for Cable Logging*, see below).
4. Span classes for equipment: up to 1,000 ft small yarder, up to 1,800 ft medium, up to 3,000 ft
   long-span; longer spans are flagged as needing intermediate supports. The class limits are an assumption of
   this project chosen to sort corridors into rough yarder sizes; they are not published capability ratings.
5. Unit coverage is the share of the unit within 150 ft (lateral yarding reach, an assumption of this project for
   a carriage with a slackpulling line) of a feasible corridor from the
   landings actually selected: up to four, chosen greedily for total coverage and stopped when the next landing
   adds less than 3 % of the unit.
   Difficulty combines coverage, mean available deflection, ground slope and the downhill-yarding share.
6. Loaded deflection (`04_cable_analysis.py`, `loaded_deflection()`). The available deflection of step 3 is the
   height of the empty chord above the ground at mid-span; it says nothing about the ground elsewhere. PNW-39
   (pp. 9-10) sets the allowable loaded deflection with a chain of fixed length hung between the supports after
   the clearance needed for carriage, chokers, logs and ground has been subtracted from the support heights; a
   weight standing for the carriage and load is walked along the span, the chain is let out until the loaded line
   just clears the ground at the critical point wherever that is, and the deflection is then read at mid-span.
   The script does the same search numerically: the loaded skyline is taken as a parabola below the chord (the
   shape of a uniformly loaded line, the usual planning stand-in for the catenary) and the loaded deflection is
   the largest mid-span sag for which the line stays at least 10 ft above the ground at every interior profile
   point; the 10 ft (carriage and rigging plus the leading end of a partially suspended log) is an assumption of
   this project. The tower height is already in the chord. The point that limits the sag is written as
   `govern_x_ft` (distance from the landing) next to `loaded_deflection_pct` on the corridors layer and the route
   tables, so a corridor that is deep at mid-span but tight near an end is reported at the tight point, not at
   mid-span. A corridor carries a payload only when its loaded deflection is at least 3 % (`payload_ok`); that
   threshold is an assumption of this project below which the working load is spent lifting the rope. `payload_ok`
   is separate from `feasible`, which keeps the clearance and 6 % available-deflection tests of step 3, so the
   feasible-corridor counts remain comparable with earlier runs; the summary carries both
   (`corridors_feasible`, `corridors_payload_ok`).
7. Payload estimate (`04b_cable_figures.py`). For each feasible corridor with `payload_ok`, the allowable load at
   the governing loaded deflection is computed for a 7/8 in extra-improved plow-steel skyline (6x19 IWRC, 1.42 lb
   per ft, breaking strength 79.6 kips) worked at
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
   the loaded mid-span deflection; the vertical component at the upper support is that horizontal tension times
   (chord slope plus twice the deflection ratio) plus a quarter of the cable weight; the upper-end tension is their
   resultant. Checked against the handbook: table 4 (tension due to a mid-span load, carriage clamped to the
   skyline, p. 36) agrees within about 0.4 % at 2 to 20 % deflection; table 2 (tension due to cable weight, p. 32)
   agrees within 1 % only to about 7 % deflection, then falls below the catenary value, about 4 % low at 10 % and
   about 15 % low at 30 % deflection. The table 2 error has a negligible effect on the payload because the
   cable-weight tension is small against the 26.5 kip working load where the error is large (about 2 kips at
   10 % deflection on a 1,000 ft span, under 1 kip at 30 %), and at the low deflections where that tension matters
   (about 6 kips at 3 %) the two agree within a few tenths of a percent. Corridors with loaded deflection under 3 % are given a payload of 0 and left out of
   the maximum and best-corridor figures. The best corridor of a unit, and of each landing on the profile sheets
   and route tables, is the one with the largest payload, not the largest deflection. Remaining limitations: the
   result is the gross load at the carriage and no carriage weight is subtracted; the links are straight, not
   catenaries; single span only, no intermediate supports; the clamped-carriage (higher-tension) case is used
   throughout; and on short spans the figure is what the rope would hold, which the yarder line pull and
   carriage would limit first. The estimate is reported as `Payload, lb` on the route tables, as an annotation on
   the profile sheets (which also draw the loaded line and mark the governing point), in Fig 7 (with reference
   curves at 3, 6, 8 and 10 % loaded deflection on a level chord), and as `max_payload_lb` and
   `payload_at_best_lb` in `unit_summary.csv`; it is not stored in the GeoPackage, only its inputs are.
   *Cable Logging Systems* (p. 87) puts the deflection needed to carry a payload at 8 to 10 %, so corridors with
   loaded deflections of 3 to 8 % carry the smallest loads.

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
| Method colors | Okabe-Ito vermilion (tractor), blue (cable), green (hand thinning); pale versions for fills, dark for lines | Okabe and Ito palette; Jenny and Kelso 2007 (dark green, brown, orange and red collapse for red-green impaired readers, so method is also carried by the label) |
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
| Sampling error | t(0.975, n-1) x SE of plot net cubic volume per acre / mean, in percent; plot volume = sum over the plot's tally trees of net CVTS x BAF / tree BA. The same statistic on plot BA is reported as a secondary figure ("basal area"), not tested against the standard; the volume CV runs about twice the basal-area CV | FSH 2409.12 ch. 40 sec. 41.1(5)(a) sale-as-a-whole volume error standard and 41.1(5)(b) stratum volume error standard: the standards apply to volume at 95 % confidence, t = 2 for large n |
| Stratum standard | 40 % of volume per unit | FSH 2409.12 ch. 40 sec. 41.1(5)(b), tree-measurement sales |
| Sale-as-a-whole | stratified estimate of volume per acre with gross-area weights (plots sample the gross unit), t = 2; sale MBF and value for the exhibit 01 placement use net acres (gross less stream equipment exclusion zones), with the gross-acre total also reported; standard from exhibit 01 by estimated sale value (10 % above $120,000) | FSH 2409.12 ch. 40 sec. 41.1(5)(a) and exhibit 01; value placed at $33.63/MBF, the Region 5 FY2025 average sold value: $9,223,272.19 over 274,275.08 MBF sold, all sales, region total row of the Forest Service Cut and Sold report CUTS203R, cumulative FY2025 Q1-Q4, run 2025-12-08 (https://www.fs.usda.gov/sites/default/files/2025-q4-cut-sold-r05.pdf). The report excludes Good Neighbor sale values and warns against using it for unit values, so the placement is a demonstration |
| Plots for the standard | (t x CV / E)^2 with the volume CV (the basal-area figure is also listed); the 20-plot local practice, not a handbook standard, is reported separately | FSH 2409.12 ch. 30 |
| SDI | summation form, sum of TPA x (DBH/10)^1.605 | Reineke 1933; Shaw 2000 |
| SDI maximum | basal-area-weighted mean of species maxima: PP 365, WF 800, DF 570, SP 561, IC 576 | FVS Staff 2008 (revised 2025-09-23), Western Sierra Nevada (WS) Variant Overview, Forest Vegetation Simulator, table 3.5.1 (https://www.fs.usda.gov/sites/default/files/forest-management/fvs-ws-overview.pdf); earlier revisions of the overview listed different maxima for some species |
| Density zones and target | 35 % of maximum = lower limit of full occupancy, 60 % = onset of competition mortality; leave target 35 % expressed as BA | Long 1985; Long and Shaw 2012 |
| Cubic volume | total-stem cubic volume (CVTS, top and stump included) by species: DF eq. 3, PP eq. 5, IC eq. 19, SP eq. 20, WF eq. 23 of the PNW-FIA tarif system (CF4, CV4, tarif, CVTS; trees under 6 in by the small-tree tarif), net of recorded defect; species codes without an equation fall back to BA x total height x form factor 0.42 | PNW-FIA volume equations for California (MacLean and Berger 1976, PNW Research Note PNW-266), as tabulated in "Volume estimation for the PNW-FIA Integrated Database", reproduced by the California Air Resources Board (2011): species table p. 5 (CA column), equations pp. 9, 11, 25, 26 and 29 (https://ww2.arb.ca.gov/sites/default/files/cap-and-trade/protocols/usforest/2011/volume_equations.pdf); fallback form factor after Avery and Burkhart, Forest Measurements (5th ed., 2002) |
| Exhibit 01 tiers (tree measurement) | sampling-error standard by estimated sale value: 25 % under $10,000; 20 % to $20,000; 18 % to $45,000; 16 % to $70,000; 14 % to $95,000; 12 % to $120,000; 10 % above | FSH 2409.12 ch. 40, 41.1 exhibit 01 |
| CVTS form-class bounds | the cubic form factor CF4 from each species equation is held to 0.30 to 0.40 for DF, PP, SP and WF, with a floor of 0.27 and no ceiling for incense-cedar; these bounds are printed on the CARB 2011 equation pages for each species and are applied as printed | MacLean and Berger 1976 as reproduced by CARB (2011), equation pages 9, 11, 25, 26 and 29; part of the published equations, not a guard added by this project |
| Simulated trees | per plot: BA target 60 + 180 x canopy cover with N(0, 25) noise; DBH lognormal around 0.28 x dominant height with sigma 0.35, clipped to 5 to 60 in; height from dominant height by a 0.45-power curve with N(0, 8) noise; seed 20260910 | this project; documented so the simulation is reproducible |
| Board feet | 5.02 Scribner bf per cu ft, applied to CVTS | Keegan, Morgan, Blatner and Daniels 2010, Trends in lumber processing in the western United States, Part I: Board foot Scribner volume per cubic foot of timber, Forest Prod. J. 60(2):133-139, table 2 (p. 135): California, 2000-2006, board feet Scribner per cubic foot of bole wood inside bark (the abstract rounds it to 5.03); treesearch 37833 (https://research.fs.usda.gov/treesearch/37833). The Keegan ratio is Scribner log scale per cubic foot of delivered sawlog fiber, so applying it to total-stem CVTS (top, stump and non-sawlog stems included) overstates sawlog board-foot volume; the consistent pairing would be merchantable cubic volume, which the tarif equations do not give without a merchantable-top conversion |
| Biomass | green weight of wood by species: PP 45, WF 47, DF 38, SP 49, IC 45 lb per cu ft; unknown codes 45 | Miles and Smith 2009, Specific gravity and other properties of wood and bark for 156 tree species found in North America, Research Note NRS-38, table 1A (pp. 8-9), average green weight of wood on a green-volume basis, bark excluded; Douglas-fir is a single entry there (FIA code 202, not split coast/interior); treesearch 34185 (https://research.fs.usda.gov/treesearch/34185) |
| CWHR | size from QMD (3: 6 to 11 in, 4: 11 to 24, 5: over 24); density from cover (S 10 to 24 %, P 25 to 39, M 40 to 59, D 60 and over) | California Wildlife Habitat Relationships |

Tables follow publication style: title above, horizontal rules only, footnotes and sources below, units in the
headers. Skyline profiles are drawn at true scale with the vertical exaggeration stated on each panel, and
"available deflection" is labeled as such: chord-to-ground height at mid-span as a percent of horizontal span.

## Reference documents consulted

Two public Forest Service documents were downloaded on 2026-09-10 into `data/work` (gitignored, not read by any
script) and used only as design references:

| File | Source | Used for |
|---|---|---|
| `data/work/fs_cable_logging_systems.pdf` | USDA Forest Service, *Cable Logging Systems* (Technology and Development Program), https://www.fs.usda.gov/t-d/pubs/htmlpubs/htm08512W03/documents/Cable_Logging_Systems.pdf | skyline terminology, the downhill-yarding rule, and the load-at-midspan relationships cited above |
| `data/work/ref_sale_area_map.png` | Willamette National Forest timber-sale documents: JC Reoffer sale area map, https://www.fs.usda.gov/sites/nfs/files/r06/willamette/publication/timber-sales/8.%20JC%20Reoffer%20Sale%20Area%20Map.pdf, and the LFC SBA sale area map, https://www.fs.usda.gov/sites/nfs/files/r06/willamette/publication/timber-sales/LFC_SBA_SAM.pdf | the sale-area-map layout and symbology conventions in the table above |

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
