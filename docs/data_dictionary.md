# Data dictionary and metadata

Distributable package: `output/gis/mohawk_west_slope.gpkg` (vectors, one GeoPackage) plus four GeoTIFFs,
written by `scripts/08_package_gis.py`. The same layers exist in the working files `data/work/planning.gpkg`,
`data/work/cable.gpkg` and `data/work/cruise_plots.gpkg`. Every layer carries its description in
`gpkg_contents`. The `project_metadata` table in the package holds the summary below.

## Project metadata (`project_metadata` table: key / value summary fields, not a `gpkg_metadata` ISO record)

| Field | Value |
|---|---|
| Title | Mohawk Valley West Slope: LiDAR-based harvest-unit planning (demonstration) |
| Abstract | Harvest-unit layout, cable-yarding screen and simulated cruise for the Community Protection treatment block nearest Whitehawk Ranch, Plumas National Forest, computed from public data only |
| Purpose | Portfolio demonstration of a planning workflow. Not a Forest Service proposal; no field verification |
| Author, date | William Steinley; date = packaging date (2026-09-14 for this release) |
| Spatial reference | EPSG:2226, NAD83 / California zone 2, US survey feet; vertical datum NAVD88, meters converted to US survey feet |
| LiDAR | USGS 3DEP CA_NoCAL_Wildfires_PlumasNF_B2_2018, QL1, flown 2018, read from the USGS Entwine copy; about 650 million points over 3,948 ac |
| Vector sources | USFS EDW Activity Project Areas and Road Core; BLM Surface Management Agency and CadNSDI PLSS; USGS NHD at 1:24,000; Census TIGER roads (TIGER2024); all downloaded September 2026 |
| Accuracy | DTM at 3 ft cells from class 2 returns; planning slope from a 15 ft smoothed DTM averaged over 99 ft. Unit boundaries are model output and are not surveyed lines. NHD stream classes are unverified |
| Lineage | scripts 01 to 08 in this repository; rules and thresholds in `docs/methods.md` |
| Constraints | Public-domain inputs. Units, corridors and plots are demonstration products and must not be used for operations |

## Vector layers

### units (MultiPolygon, 24 features)

| Field | Type | Meaning |
|---|---|---|
| unit_id | int | 100-series Tractor, 400-series Cable, 700-series Hand Thinning, numbered west to east |
| method | text | Tractor, Cable or Hand Thinning (rules in methods.md) |
| acres | real | gross acres inside the boundary |
| net_acres | real | acres after the equipment exclusion zones inside the unit are removed |
| slope_mean, slope_max | real | planning slope, percent, mean and 98th percentile over the unit |
| aspect | text | dominant aspect octant (N, NE, ...) |
| elev_min, elev_max | real | DTM range, ft |
| cover_pct | real | mean canopy cover, percent, 66 ft window |
| dom_ht | real | mean dominant height (95th percentile CHM, 66 ft window), ft |
| road_ft | real | distance from the unit centroid to the nearest road, ft |

### eez_buffers, rca_buffers (MultiPolygon)

| Field | Type | Meaning |
|---|---|---|
| class | text | perennial, intermittent, ephemeral or waterbody, from the NHD FCode |
| width_ft | int | buffer width each side: EEZ 100 / 50 / 25 ft, RCA 300 / 150 / 100 ft |

### streams_aoi (MultiLineString)

| Field | Type | Meaning |
|---|---|---|
| class | text | perennial, intermittent or ephemeral |
| fcode | int | NHD feature code the class was taken from |
| name | text | GNIS name where NHD carries one |

### contours (LineString)

| Field | Type | Meaning |
|---|---|---|
| elev | real | contour elevation, ft, 40 ft interval |
| index | int | 1 on 200 ft index contours, else 0 |

### operable_mask (Polygon)

Operable ground before splitting; `v` = 1. Kept so a reviewer can see what the unit rules removed.

### landings (Point, 314 features)

| Field | Type | Meaning |
|---|---|---|
| unit_id | int | unit the landing was screened for |
| landing_id | int | index along the road within that unit's candidate set |
| elev | real | DTM elevation at the landing, ft |
| corridors_ok | int | number of feasible corridors from this landing |
| coverage_pct | real | share of the unit within 150 ft of a feasible corridor from this landing |

### corridors (LineString, 8,540 features)

| Field | Type | Meaning |
|---|---|---|
| unit_id, landing_id | int | landing the corridor was cast from |
| bearing | int | azimuth from the landing, degrees |
| span_ft | real | horizontal distance landing to tailhold |
| deflection_pct | real | mid-span chord height above ground divided by span, percent |
| min_clear_ft | real | minimum chord clearance above ground along the profile, ft |
| feasible | int | 1 when min clearance >= 10 ft and deflection >= 6 % with a 50 ft tower |
| feasible_70ft | int | the same test with a 70 ft tower |
| downhill | int | 1 when the tailhold is above the landing (logs yard downhill to the landing) |
| max_slope_pct | real | steepest ground slope along the profile |
| span_class | text | Small yarder (<= 1,000 ft), Medium (<= 1,800), Long-span (<= 3,000), Intermediate support needed |
| loaded_deflection_pct | real | largest mid-span sag of a loaded line that clears every profile point by 10 ft, divided by span, percent (PNW-39 chain method) |
| govern_x_ft | real | distance from the landing to the profile point that governs the loaded deflection, ft |
| payload_ok | int | 1 when loaded deflection >= 3 %, the minimum credited with a payload |

The payload estimate (allowable load at the governing loaded deflection for a 7/8 in skyline, methods.md item 7) is
computed in `04b_cable_figures.py` from span_ft, loaded_deflection_pct and the chord slope. It is not stored in the GeoPackage.
It appears on the route tables, the profile sheets, Fig 7 and `unit_summary.csv`.

### plots (Point, 798 features)

Simulated cruise plots. The tree records are in `output/review/cruise_data.xlsx`.

| Field | Type | Meaning |
|---|---|---|
| plot | text | unit-plot identifier |
| unit_id | int | unit |
| n_trees | int | trees counted in at BAF 20 |
| slope | int | ground slope at the plot, percent |
| flags | text | QA checks that fired, semicolon separated |

## Rasters (3 ft cells, Float32 unless noted, nodata -9999)

| File | Meaning |
|---|---|
| dtm_3ft | ground surface from class 2 returns, IDW, holes filled |
| dsm_3ft | first-return maximum surface |
| chm_3ft | height above ground of the highest return, clipped 0 to 300 ft |
| slope_pct | raw slope of the 3 ft DTM; noisy under canopy, kept for reference only |
| slope_plan_pct | planning slope: gradient of the 15 ft smoothed DTM averaged over 99 ft |
| aspect_deg | aspect, degrees from north |
| hillshade | Byte, GDAL multidirectional hillshade, z-factor 1 |
| canopy_cover_66ft | share of CHM cells above 6.5 ft in a 66 ft window, 0 to 1 |
| dom_height_66ft | 95th percentile CHM height in a 66 ft window, ft |
| yarding_class | 1 ground-based (<= 35 %), 2 marginal (35 to 50 %), 3 cable (> 50 %) |
| relief_tint | Byte RGBA, hillshade multiplied into pale yarding-class tints, the base for the unit sheets |

`output/gis` carries yarding_class, slope_plan_pct, canopy_cover_66ft and dom_height_66ft as tiled,
deflate-compressed GeoTIFFs with overviews. The full set stays in `data/work` (not in git; rebuild with
`02_build_terrain.py`).

## Quicklooks

`output/quicklooks`: hillshade, DTM, CHM, planning slope in yarding classes, yarding class, canopy cover and
dominant height, each with title, legend or color ramp, one-mile scale bar, north arrow and unit outlines,
200 dpi PNG from `02b_quicklooks.py`.

## Tabular outputs

- `output/cable/unit_summary.csv`: one row per unit from the cable screen: corridors cast and feasible,
  coverage, mean deflection, equipment class, difficulty, chosen landings, downhill share, EYD, AYD, uphill
  share, and two payload columns from `04b_cable_figures.py`. `max_payload_lb` is the largest allowable load (lb,
  carriage plus logs, 7/8 in extra-improved plow-steel skyline at a safe working load of 26.5 kips, at the
  governing loaded deflection by the PNW-39 chain method with 10 ft clearance) among the unit's feasible corridors
  with loaded deflection of at least 3 %. `payload_at_best_lb` is the same for the highest-payload corridor from
  the selected landings. Both are blank where no corridor is feasible.
- `output/review/cruise_data.xlsx`: a READ ME sheet first. Its first cell states that every plot and tree is simulated from LiDAR canopy metrics with planted
  recording errors (not field data) and lists the six data sheets. Then Plots, Trees, Unit summary, Stand tables, Stock tables and Standards and assumptions.
  Plots carry cruiser `SIM` and date `simulated`. The unit summary carries gross and net acres, net cubic volume per acre with its CV, sampling error at 95 %, stratum standard and plots needed (the FSH 2409.12 volume standard as supplemented for Region 5, 30 % per stratum for a tree-measurement sale), the same set for basal area, TPA, QMD, SDI, CWHR, sawtimber and biomass BA, biomass green
  tons per acre, CV, plots needed and the standard check. Standards and assumptions has columns item, value, source and url.
- `output/review/qa_summary.csv`: the sale-level QA table printed on the first page of `Unit_Reviews.pdf` (unit, method, acres, plots, cu ft/ac, volume CV and sampling error at 95 %, BA with its CV and error, t, stratum standard, design result on volume, share of sale volume and whether the stratum standard binds, the Region 5 20-measured-trees and 20-plot checks, QA flags, status), plus a `data` column whose value is `simulated`
  on every row.

## Note on unit slope figures

`slope_mean` and `slope_max` in the GeoPackage `units` layer are computed on the published polygon and are the figures to cite. `output/cable/unit_summary.csv` carries the `slope_mean` value that was current when the cable run started, and it can differ from the GeoPackage by up to half a percentage point. The unit sheets, review sheets and web map read the GeoPackage.
